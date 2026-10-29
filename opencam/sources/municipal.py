"""Municipal open-data source: a city's own authoritative camera list.

This is the independent layer. OSM (and everything derived from it, including
DeFlock) is one lineage; a city publishing its own enforcement-camera dataset is
a separate, authoritative one. When a camera shows up in both, dedupe unions the
sources and lifts its confidence, which is the whole point of a multi-source set.

Most US open-data portals run Socrata, so one SODA fetcher covers many cities;
each feed is just a registry entry. Feeds are keyed to the opencam region they
belong to, so `fetch_region` only pulls a city's data when that region builds.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from ..normalize import make_record

_USER_AGENT = "opencam/0.1 (+https://github.com/opsec-bot/opencam)"

# Authoritative city data: trusted highly, but not blindly 1.0 so an independent
# OSM confirmation can still nudge it.
BASE_CONFIDENCE = 0.9

# Travel-direction codes used by most US portals, as degrees clockwise from N.
_APPROACH = {"NB": 0.0, "EB": 90.0, "SB": 180.0, "WB": 270.0,
             "NEB": 45.0, "SEB": 135.0, "SWB": 225.0, "NWB": 315.0}


class SocrataFeed:
    """One Socrata dataset mapped to opencam's schema."""

    def __init__(self, *, key: str, region: str, host: str, dataset: str,
                 cam_type: str, lat_field: str = "latitude",
                 lon_field: str = "longitude",
                 loc_object: Optional[str] = "location",
                 approach_fields: tuple[str, ...] = (),
                 date_field: Optional[str] = None,
                 operator: Optional[str] = None):
        self.key = key              # source id, e.g. "chicago_speed"
        self.region = region        # opencam region id, e.g. "us-il"
        self.host = host            # e.g. "data.cityofchicago.org"
        self.dataset = dataset      # Socrata 4x4 id, e.g. "4i42-qv3h"
        self.cam_type = cam_type
        self.lat_field = lat_field
        self.lon_field = lon_field
        self.loc_object = loc_object  # nested {latitude,longitude} field, if any
        self.approach_fields = approach_fields
        self.date_field = date_field
        self.operator = operator

    def url(self, limit: int, offset: int) -> str:
        q = urllib.parse.urlencode({"$limit": limit, "$offset": offset})
        return f"https://{self.host}/resource/{self.dataset}.json?{q}"


# Verified feeds. Add a city by probing its portal and dropping a line here.
FEEDS = [
    SocrataFeed(
        key="chicago_speed", region="us-il",
        host="data.cityofchicago.org", dataset="4i42-qv3h",
        cam_type="speed_camera",
        approach_fields=("first_approach", "second_approach"),
        date_field="go_live_date", operator="City of Chicago",
    ),
    SocrataFeed(
        key="chicago_redlight", region="us-il",
        host="data.cityofchicago.org", dataset="thvf-6diy",
        cam_type="red_light",
        approach_fields=("first_approach",),
        date_field="go_live_date", operator="City of Chicago",
    ),
    SocrataFeed(
        key="pgcounty_md_speed", region="us-md",
        host="data.princegeorgescountymd.gov", dataset="mnkf-cu5c",
        cam_type="speed_camera", loc_object="location_1",
        operator="Prince George's County, MD",
    ),
]


def _approach_to_deg(row: dict, fields: tuple[str, ...]) -> Optional[float]:
    for f in fields:
        code = (row.get(f) or "").strip().upper()
        if code in _APPROACH:
            return _APPROACH[code]
    return None


def _coord(row: dict, field: str, loc_object: Optional[str]) -> Optional[float]:
    # Portals expose the number either flat or inside a location object whose
    # key varies by dataset (`location`, `location_1`, ...).
    val = row.get(field)
    if val is None and loc_object and isinstance(row.get(loc_object), dict):
        val = row[loc_object].get(field)
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _fetch_socrata(feed: SocrataFeed, page: int = 2000) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        req = urllib.request.Request(feed.url(page, offset),
                                     headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            batch = json.loads(resp.read().decode("utf-8"))
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return rows


def fetch_region(region_id: str, bbox: dict,
                 _page: int = 2000) -> list[dict]:
    """Return normalised records from every municipal feed in this region."""
    records: list[dict] = []
    for feed in FEEDS:
        if feed.region != region_id:
            continue
        try:
            rows = _fetch_socrata(feed, _page)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            continue  # a dead portal must not sink the region
        for row in rows:
            lat = _coord(row, feed.lat_field, feed.loc_object)
            lon = _coord(row, feed.lon_field, feed.loc_object)
            if lat is None or lon is None:
                continue
            rid = row.get("id") or row.get("camera_id") or row.get("intersection") or f"{lat},{lon}"
            records.append(make_record(
                rid=f"{feed.key}:{rid}",
                cam_type=feed.cam_type,
                lat=lat,
                lon=lon,
                source=feed.key,
                direction=_approach_to_deg(row, feed.approach_fields),
                operator=feed.operator,
                first_seen=(row.get(feed.date_field) or None) if feed.date_field else None,
                confidence=BASE_CONFIDENCE,
            ))
    return records
