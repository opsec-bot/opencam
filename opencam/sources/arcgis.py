"""ArcGIS open-data source: the other half of US municipal/state portals.

Cities and states that don't run Socrata almost always run ArcGIS, exposing data
through a FeatureServer REST layer. One GeoJSON query covers them all, so, like
`municipal`, each government feed is a single registry entry. This is an
independent lineage from OSM, so dedupe cross-validates against it.

FeatureServer query used:
    <layer-url>/query?where=1=1&outFields=*&f=geojson&resultOffset=N&resultRecordCount=M
GeoJSON gives Point geometry as [lon, lat]; properties carry the rest.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from ..normalize import make_record, parse_direction

_USER_AGENT = "opencam/0.1 (+https://github.com/opsec-bot/opencam)"
BASE_CONFIDENCE = 0.9
_PAGE = 1000

# Travel-direction codes often embedded in a location string ("... Ave SB").
_APPROACH = {"NB": 0.0, "EB": 90.0, "SB": 180.0, "WB": 270.0,
             "NEB": 45.0, "SEB": 135.0, "SWB": 225.0, "NWB": 315.0}
_APPROACH_RE = re.compile(r"\b(NEB|NWB|SEB|SWB|NB|SB|EB|WB)\b")


class ArcGISFeed:
    """One ArcGIS FeatureServer layer mapped to opencam's schema."""

    def __init__(self, *, key: str, region: str, url: str, cam_type: str,
                 id_field: Optional[str] = None,
                 dir_field: Optional[str] = None,
                 dir_in_field: Optional[str] = None,
                 date_field: Optional[str] = None,
                 operator: Optional[str] = None):
        self.key = key
        self.region = region
        self.url = url.rstrip("/")   # ".../FeatureServer/0"
        self.cam_type = cam_type
        self.id_field = id_field
        self.dir_field = dir_field        # property holding a direction outright
        self.dir_in_field = dir_in_field  # text property with a trailing NB/SB/...
        self.date_field = date_field
        self.operator = operator

    def query_url(self, offset: int) -> str:
        q = urllib.parse.urlencode({
            "where": "1=1", "outFields": "*", "f": "geojson",
            "resultOffset": offset, "resultRecordCount": _PAGE,
        })
        return f"{self.url}/query?{q}"


# Verified feeds (US state/city FeatureServers).
FEEDS = [
    ArcGISFeed(
        key="md_safezones", region="us-md",
        url="https://services.arcgis.com/njFNhDsUCentVYJW/arcgis/rest/services/Maryland_Safe_Zones/FeatureServer/0",
        cam_type="speed_camera", id_field="LOCATIONHISTORICID",
        date_field="CREATIONDATE", operator="Maryland (statewide)",
    ),
    ArcGISFeed(
        key="baltimore_redlight", region="us-md",
        url="https://services3.arcgis.com/ZTvQ9NuONePFYofE/arcgis/rest/services/Baltimore_ATVES_Red_Light_Camera/FeatureServer/0",
        cam_type="red_light", id_field="CamID", dir_in_field="Location",
        operator="Baltimore City",
    ),
    ArcGISFeed(
        key="baltimore_speed_portable", region="us-md",
        url="https://services3.arcgis.com/ZTvQ9NuONePFYofE/arcgis/rest/services/ATVES_Speed_Cameras_Portable/FeatureServer/1",
        cam_type="speed_camera", dir_in_field="Location",
        operator="Baltimore City",
    ),
]


def _direction(props: dict, feed: ArcGISFeed) -> Optional[float]:
    if feed.dir_field and props.get(feed.dir_field) is not None:
        return parse_direction(str(props[feed.dir_field]))
    if feed.dir_in_field:
        text = (props.get(feed.dir_in_field) or "").upper()
        m = _APPROACH_RE.search(text)
        if m:
            return _APPROACH[m.group(1)]
    return None


def _fetch(feed: ArcGISFeed) -> list[dict]:
    features: list[dict] = []
    offset = 0
    while True:
        req = urllib.request.Request(feed.query_url(offset),
                                     headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        batch = doc.get("features", [])
        if not batch:
            break
        features.extend(batch)
        if len(batch) < _PAGE and not doc.get("exceededTransferLimit"):
            break
        offset += len(batch)
    return features


def fetch_region(region_id: str, bbox: dict) -> list[dict]:
    """Return normalised records from every ArcGIS feed in this region."""
    records: list[dict] = []
    for feed in FEEDS:
        if feed.region != region_id:
            continue
        try:
            features = _fetch(feed)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue
        for i, feat in enumerate(features):
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") or []
            if len(coords) < 2:
                continue
            lon, lat = coords[0], coords[1]
            props = feat.get("properties", {})
            raw_id = props.get(feed.id_field) if feed.id_field else feat.get("id", i)
            records.append(make_record(
                rid=f"{feed.key}:{raw_id}",
                cam_type=feed.cam_type,
                lat=lat,
                lon=lon,
                source=feed.key,
                direction=_direction(props, feed),
                operator=feed.operator,
                first_seen=(str(props[feed.date_field])[:10]
                            if feed.date_field and props.get(feed.date_field) else None),
                confidence=BASE_CONFIDENCE,
            ))
    return records
