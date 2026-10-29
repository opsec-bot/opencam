"""Split deduped records into per-region packs and write the manifest.

The output layout mirrors what a consuming app expects: a small manifest that
lists every region with its bbox, byte size, SHA-256 and camera count, plus one
pack file per region. A client reads the manifest, compares hashes, and only
downloads packs that changed.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from . import SCHEMA_VERSION, __version__

OSM_ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _in_bbox(rec: dict, bbox: dict) -> bool:
    return (bbox["south"] <= rec["lat"] <= bbox["north"]
            and bbox["west"] <= rec["lon"] <= bbox["east"])


def _write_json(path: str, obj) -> tuple[int, str]:
    """Write compact JSON, return (byte size, sha256 hex)."""
    blob = json.dumps(obj, separators=(",", ":"), sort_keys=False).encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(blob)
    return len(blob), hashlib.sha256(blob).hexdigest()


def assign_regions(records: list[dict], regions: dict) -> dict[str, list[dict]]:
    """Bucket each record into the first region whose bbox contains it.

    A record may fall in overlapping bboxes (our state boxes are rectangles, so
    neighbours overlap). First match wins, which keeps a camera in exactly one
    pack and avoids double counting.
    """
    buckets: dict[str, list[dict]] = {rid: [] for rid in regions}
    for rec in records:
        for rid, meta in regions.items():
            if _in_bbox(rec, meta["bbox"]):
                buckets[rid].append(rec)
                break
    return buckets


def build_packs(records: list[dict], regions: dict, out_dir: str,
                base_url: str) -> dict:
    """Write packs + manifest to out_dir. Returns the manifest dict."""
    packs_dir = os.path.join(out_dir, "packs")
    os.makedirs(packs_dir, exist_ok=True)

    buckets = assign_regions(records, regions)
    built_at = _now_iso()
    region_entries = []

    for rid, meta in regions.items():
        recs = sorted(buckets[rid], key=lambda r: r["id"])
        if not recs:
            continue  # no cameras mapped here yet; skip the empty pack
        pack = {
            "schemaVersion": SCHEMA_VERSION,
            "region": rid,
            "builtAt": built_at,
            "cameras": recs,
        }
        fname = f"{rid}.json"
        size, digest = _write_json(os.path.join(packs_dir, fname), pack)
        region_entries.append({
            "id": rid,
            "name": meta["name"],
            "bbox": meta["bbox"],
            "packUrl": f"{base_url.rstrip('/')}/packs/{fname}",
            "packByteSize": size,
            "packSha256": digest,
            "cameraCount": len(recs),
            "builtAt": built_at,
        })

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "generator": f"opencam {__version__}",
        "generatedAt": built_at,
        "attribution": OSM_ATTRIBUTION,
        "regions": region_entries,
    }
    _write_json(os.path.join(out_dir, "manifest.json"), manifest)
    return manifest
