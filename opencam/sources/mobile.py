"""Mobile ALPR source: the layer OpenStreetMap structurally can't hold.

Trailer-mounted and construction-zone Flock readers move, so nobody maps them in
OSM, and the CorsaView dev confirmed they're the gap. opencam fills it with a
community-maintained list (`data/mobile_lprs.json`) where every entry carries a
`lastVerified` date and a time-to-live. Past its TTL an entry is dropped, so a
unit that has moved on stops alerting instead of becoming permanent noise. That
expiry is also why this layer updates faster than any OSM-derived feed.

opencam ships the mechanism and schema, not the data: entries come from real
reports. The file starts empty.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Optional

from ..normalize import make_record, parse_direction

_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "mobile_lprs.json")

# Days a report stays live if it doesn't set its own `ttlDays`. Mobile units
# rarely sit for more than a few weeks, so this is deliberately short.
DEFAULT_TTL_DAYS = 45

# Confidence of a fresh crowdsourced report, before any time decay or
# cross-source agreement.
BASE_CONFIDENCE = 0.5
# A report never decays below this while it is still within its TTL.
MIN_CONFIDENCE = 0.3


def _today() -> _dt.date:
    return _dt.datetime.now(_dt.timezone.utc).date()


def _age_days(last_verified: str, today: _dt.date) -> Optional[int]:
    try:
        d = _dt.date.fromisoformat(last_verified[:10])
    except (ValueError, TypeError):
        return None
    return (today - d).days


def _load() -> list[dict]:
    try:
        with open(os.path.normpath(_DATA_PATH), encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else data.get("cameras", [])


def _in_bbox(lat: float, lon: float, bbox: dict) -> bool:
    return (bbox["south"] <= lat <= bbox["north"]
            and bbox["west"] <= lon <= bbox["east"])


def fetch_region(region_id: str, bbox: dict) -> list[dict]:
    """Return live (non-expired) mobile ALPR reports inside bbox."""
    today = _today()
    out: list[dict] = []
    for entry in _load():
        try:
            lat = float(entry["lat"])
            lon = float(entry["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not _in_bbox(lat, lon, bbox):
            continue

        last_verified = entry.get("lastVerified", "")
        ttl = int(entry.get("ttlDays", DEFAULT_TTL_DAYS))
        age = _age_days(last_verified, today)
        if age is None or age < 0 or age > ttl:
            continue  # undated or expired: drop it

        # Linear decay across the TTL window so a stale-but-live report is
        # trusted less than a fresh one.
        decay = 1.0 - (age / ttl if ttl else 0.0)
        confidence = max(MIN_CONFIDENCE, round(BASE_CONFIDENCE * decay, 3))

        rid = entry.get("id") or f"{lat:.6f},{lon:.6f}"
        out.append(make_record(
            rid=f"mobile:{rid}",
            cam_type="alpr",
            lat=lat,
            lon=lon,
            source="mobile",
            direction=parse_direction(entry.get("direction")),
            operator=entry.get("operator"),
            last_verified=last_verified or None,
            confidence=confidence,
        ))
    return out
