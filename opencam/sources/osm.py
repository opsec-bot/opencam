"""OpenStreetMap source, via the Overpass API.

The base layer: global and ODbL-licensed. We ask Overpass for the three node
kinds that map to enforcement cameras and translate their tags into normalised
records. No API key, but Overpass is a shared free service, so we keep the
query tight and the timeout honest.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from ..normalize import make_record, parse_direction

# Public instance. Overridable for a mirror or a local Overpass.
DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"

# One record's worth of trust from a single OSM confirmation. DeFlock agreement
# or a municipal portal later pushes this up during dedupe.
BASE_CONFIDENCE = 0.55

_USER_AGENT = "opencam/0.1 (+https://github.com/opsec-bot/opencam)"


def _query(bbox: dict) -> str:
    s, w, n, e = bbox["south"], bbox["west"], bbox["north"], bbox["east"]
    box = f"({s},{w},{n},{e})"
    return (
        "[out:json][timeout:90];\n"
        "(\n"
        f'  node["highway"="speed_camera"]{box};\n'
        f'  node["man_made"="surveillance"]["surveillance:type"="ALPR"]{box};\n'
        f'  node["man_made"="surveillance"]["camera:type"="automated"]{box};\n'
        f'  node["enforcement"]{box};\n'
        ")\n;\nout body;"
    )


def _classify(tags: dict) -> Optional[str]:
    """Pick a camera type from OSM tags, or None if it isn't one we keep."""
    enforcement = tags.get("enforcement", "")
    surveil = tags.get("surveillance:type", "")
    operator = (tags.get("operator", "") or "").lower()

    if surveil == "ALPR" or "flock" in operator or tags.get("camera:type") == "automated":
        return "alpr"
    if tags.get("highway") == "speed_camera" or "maxspeed" in enforcement or enforcement == "average_speed":
        return "speed_camera"
    if enforcement in ("traffic_signals", "red_light") or tags.get("highway") == "traffic_signals":
        return "red_light"
    if enforcement:  # a generic enforcement node we couldn't refine
        return "speed_camera"
    return None


def _request(endpoint: str, body: str, retries: int = 3) -> dict:
    data = ("data=" + urllib.parse.quote(body)).encode("utf-8")
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        req = urllib.request.Request(
            endpoint, data=data,
            headers={"User-Agent": _USER_AGENT,
                     "Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_err = exc
            # 429/504 from Overpass mean "slow down". Back off and retry.
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Overpass request failed after {retries} tries: {last_err}")


def fetch_region(region_id: str, bbox: dict, endpoint: str = DEFAULT_ENDPOINT) -> list[dict]:
    """Return normalised OSM camera records inside bbox."""
    result = _request(endpoint, _query(bbox))
    records: list[dict] = []
    for el in result.get("elements", []):
        if el.get("type") != "node":
            continue
        tags = el.get("tags", {})
        cam_type = _classify(tags)
        if cam_type is None:
            continue
        operator = tags.get("operator") or None
        records.append(make_record(
            rid=f"osm:node/{el['id']}",
            cam_type=cam_type,
            lat=el["lat"],
            lon=el["lon"],
            source="osm",
            direction=parse_direction(tags.get("direction")),
            operator=operator,
            confidence=BASE_CONFIDENCE,
        ))
    return records
