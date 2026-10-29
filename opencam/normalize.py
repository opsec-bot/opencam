"""The common camera record and helpers every source normalises to.

A record is a plain dict so it serialises straight to JSON. One schema for all
sources means dedupe and the pack builder never care where a camera came from.
"""

from __future__ import annotations

from typing import Optional

# The camera kinds we model. Sources map their own tags onto these.
TYPES = ("speed_camera", "red_light", "alpr", "combined")

# Fallback cone geometry per type, used only when a source gives no direction
# detail. Degrees of field of view and metres of range. These match the values
# CorsaView draws with, so a consumer gets sensible cones out of the box.
CONE_DEFAULTS = {
    "speed_camera": {"fov_deg": 28, "range_m": 90},
    "red_light": {"fov_deg": 28, "range_m": 60},
    "alpr": {"fov_deg": 50, "range_m": 60},
    "combined": {"fov_deg": 40, "range_m": 75},
}

# 16-point compass to degrees, for OSM `direction` tags written as N/NE/...
_COMPASS = {
    "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5,
    "SE": 135, "SSE": 157.5, "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
    "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
}


def parse_direction(value: Optional[str]) -> Optional[float]:
    """Turn an OSM direction tag into degrees, or None if it isn't usable.

    The tag is either a number (degrees clockwise from north) or a compass
    point like `SE`. Anything else (a range, a street name) is dropped.
    """
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if text in _COMPASS:
        return _COMPASS[text]
    try:
        deg = float(text)
    except ValueError:
        return None
    return deg % 360.0


def make_record(
    *,
    rid: str,
    cam_type: str,
    lat: float,
    lon: float,
    source: str,
    direction: Optional[float] = None,
    operator: Optional[str] = None,
    first_seen: Optional[str] = None,
    last_verified: Optional[str] = None,
    confidence: float = 0.5,
) -> dict:
    """Build one normalised record with a stable field order."""
    if cam_type not in TYPES:
        cam_type = "speed_camera"
    rec = {
        "id": rid,
        "type": cam_type,
        "lat": round(float(lat), 6),
        "lon": round(float(lon), 6),
        "sources": [source],
        "confidence": round(float(confidence), 3),
    }
    if direction is not None:
        rec["direction"] = round(float(direction) % 360.0, 1)
    if operator:
        rec["operator"] = operator
    if first_seen:
        rec["firstSeen"] = first_seen
    if last_verified:
        rec["lastVerified"] = last_verified
    return rec
