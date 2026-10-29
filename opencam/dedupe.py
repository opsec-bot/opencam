"""Collapse records that describe the same physical camera.

Sources overlap: two state bboxes share a border, OSM and DeFlock both map the
same Flock reader. Dedupe merges those into one record, unions their `sources`,
and lifts confidence when independent sources agree. This is where a multi-
source dataset earns its keep over any single feed.

Algorithm: bucket points into a coarse grid, compare only within a cell and its
neighbours, union-find the matches. O(n) in practice instead of O(n^2).
"""

from __future__ import annotations

import math
from typing import Iterable

# Two records match if they are the same (or compatible) type and closer than
# this many metres. ALPR readers sit tighter together than speed cameras, so
# the threshold is per type.
MERGE_RADIUS_M = {
    "alpr": 20.0,
    "speed_camera": 25.0,
    "red_light": 30.0,
    "combined": 25.0,
}

# If both records carry a heading, they must point within this many degrees to
# be the same camera. One without a heading never blocks a merge.
HEADING_TOLERANCE_DEG = 50.0

# How much a second independent source adds to confidence (capped at 1.0).
AGREEMENT_BONUS = 0.25

_EARTH_R = 6371008.8  # mean earth radius, metres


def _haversine_m(a: dict, b: dict) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_R * math.asin(math.sqrt(h))


def _types_compatible(t1: str, t2: str) -> bool:
    if t1 == t2:
        return True
    # A camera mapped as both a speed and a red-light unit is "combined".
    return {t1, t2} <= {"speed_camera", "red_light", "combined"}


def _heading_ok(a: dict, b: dict) -> bool:
    if "direction" not in a or "direction" not in b:
        return True
    diff = abs(a["direction"] - b["direction"]) % 360.0
    diff = min(diff, 360.0 - diff)
    return diff <= HEADING_TOLERANCE_DEG


def _match(a: dict, b: dict) -> bool:
    if not _types_compatible(a["type"], b["type"]):
        return False
    radius = max(MERGE_RADIUS_M.get(a["type"], 25.0), MERGE_RADIUS_M.get(b["type"], 25.0))
    if _haversine_m(a, b) > radius:
        return False
    return _heading_ok(a, b)


def _cell(rec: dict, size_deg: float) -> tuple[int, int]:
    return (int(rec["lat"] / size_deg), int(rec["lon"] / size_deg))


def _merge_into(base: dict, other: dict) -> dict:
    """Fold `other` into `base`, returning the merged record."""
    sources = sorted(set(base.get("sources", [])) | set(other.get("sources", [])))
    merged = dict(base)
    merged["sources"] = sources
    # Prefer a value where one record has it and the other doesn't.
    for key in ("direction", "operator", "firstSeen"):
        if key not in merged and key in other:
            merged[key] = other[key]
    # Newest verification wins.
    lv = [r.get("lastVerified") for r in (base, other) if r.get("lastVerified")]
    if lv:
        merged["lastVerified"] = max(lv)
    # Confidence: the stronger of the two, plus a bonus per extra source.
    base_conf = max(base.get("confidence", 0.5), other.get("confidence", 0.5))
    bonus = AGREEMENT_BONUS * (len(sources) - 1)
    merged["confidence"] = round(min(1.0, base_conf + bonus), 3)
    # Stable id: keep the lexicographically smallest so diffs are deterministic.
    merged["id"] = min(base["id"], other["id"])
    return merged


def dedupe(records: Iterable[dict]) -> list[dict]:
    """Merge duplicate cameras across all sources."""
    recs = list(records)
    n = len(recs)
    if n < 2:
        return recs

    # Grid cell ~ a bit larger than the biggest merge radius (30 m ~ 0.0003 deg,
    # use 0.001 deg so a match never straddles more than neighbouring cells).
    size = 0.001
    grid: dict[tuple[int, int], list[int]] = {}
    for i, r in enumerate(recs):
        grid.setdefault(_cell(r, size), []).append(i)

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    for (cx, cy), idxs in grid.items():
        # Candidates: this cell plus the 8 neighbours (dedup the index pairs).
        neigh: list[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neigh.extend(grid.get((cx + dx, cy + dy), ()))
        for i in idxs:
            for j in neigh:
                if j <= i:
                    continue
                if _match(recs[i], recs[j]):
                    union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    out: list[dict] = []
    for members in clusters.values():
        merged = recs[members[0]]
        for k in members[1:]:
            merged = _merge_into(merged, recs[k])
        out.append(merged)
    return out
