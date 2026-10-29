"""Scraped source: the long tail of governments with a website but no API.

Socrata and ArcGIS cover the portals with a real data API. Plenty of city and
county camera pages aren't on either; they're a JS frontend that fetches an
internal JSON endpoint. opencam reaches those through our own tool, sitescrape
(https://github.com/opsec-bot/sitescrape), which turns such a page into a typed
endpoint you call with `sitescrape call <site>/<name>`.

opencam stays pure Python: this adapter shells out to sitescrape only when it is
installed and a feed is configured, and no-ops otherwise, so a build without it
just skips this tier. Point sitescrape at **public government pages only** —
scraping a closed or commercial service would break the one promise that makes
opencam clean.

Set the sitescrape location with OPENCAM_SITESCRAPE_DIR, or drop the repo next to
opencam (../sitescrape). FEEDS starts empty; add one once you've captured a real
endpoint with `sitescrape build <gov-camera-url> --task "list camera locations"`.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Optional

from ..normalize import make_record, parse_direction

BASE_CONFIDENCE = 0.75  # public gov data, but via a scraped frontend, not an API


class ScrapedFeed:
    """A sitescrape endpoint mapped to opencam's schema."""

    def __init__(self, *, key: str, region: str, endpoint: str,
                 cam_type: str, input_json: str = "{}",
                 results_key: str = "results",
                 lat_field: str = "lat", lon_field: str = "lon",
                 id_field: Optional[str] = None,
                 dir_field: Optional[str] = None,
                 operator: Optional[str] = None):
        self.key = key
        self.region = region
        self.endpoint = endpoint        # sitescrape "site/name"
        self.cam_type = cam_type
        self.input_json = input_json
        self.results_key = results_key
        self.lat_field = lat_field
        self.lon_field = lon_field
        self.id_field = id_field
        self.dir_field = dir_field
        self.operator = operator


# Add a feed only after capturing the endpoint with sitescrape. Example (shape
# only, not a live endpoint):
#   ScrapedFeed(key="examplecity", region="us-xx",
#               endpoint="example.gov/cameras", cam_type="speed_camera",
#               lat_field="latitude", lon_field="longitude",
#               operator="Example City")
FEEDS: list[ScrapedFeed] = []


def _sitescrape_bin() -> Optional[str]:
    base = os.environ.get("OPENCAM_SITESCRAPE_DIR")
    candidates = []
    if base:
        candidates.append(os.path.join(base, "bin", "sitescrape.mjs"))
    # Sibling checkout next to the opencam repo.
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    candidates.append(os.path.join(os.path.dirname(here), "sitescrape", "bin", "sitescrape.mjs"))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _call(bin_path: str, feed: ScrapedFeed) -> Optional[dict]:
    try:
        proc = subprocess.run(
            ["node", bin_path, "call", feed.endpoint, feed.input_json],
            capture_output=True, text=True, timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None  # node missing or the call hung
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _rows(payload: dict, results_key: str) -> list:
    val = payload.get(results_key)
    if isinstance(val, list):
        return val
    # Some endpoints return a bare list.
    return payload if isinstance(payload, list) else []


def fetch_region(region_id: str, bbox: dict) -> list[dict]:
    """Return normalised records from every scraped feed in this region."""
    feeds = [f for f in FEEDS if f.region == region_id]
    if not feeds:
        return []
    bin_path = _sitescrape_bin()
    if not bin_path:
        return []  # sitescrape not installed: skip this tier quietly

    records: list[dict] = []
    for feed in feeds:
        payload = _call(bin_path, feed)
        if payload is None:
            continue
        for i, row in enumerate(_rows(payload, feed.results_key)):
            if not isinstance(row, dict):
                continue
            try:
                lat = float(row[feed.lat_field])
                lon = float(row[feed.lon_field])
            except (KeyError, TypeError, ValueError):
                continue
            rid = row.get(feed.id_field) if feed.id_field else i
            records.append(make_record(
                rid=f"{feed.key}:{rid}",
                cam_type=feed.cam_type,
                lat=lat,
                lon=lon,
                source=feed.key,
                direction=parse_direction(row.get(feed.dir_field)) if feed.dir_field else None,
                operator=feed.operator,
                confidence=BASE_CONFIDENCE,
            ))
    return records
