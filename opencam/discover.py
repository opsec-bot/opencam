"""Find municipal camera datasets across Socrata AND ArcGIS portals, nationwide.

Hand-coding hundreds of cities doesn't scale. But US open-data portals almost
all run one of two platforms, and each has a single cross-site search API:
Socrata's cross-domain catalog and ArcGIS Hub. `discover` queries both, filters
out the noise (violation/fine/citation feeds, dashboards, obvious non-US), and
prints the *candidate* location datasets with the exact endpoint to drop into
`municipal.FEEDS` (Socrata) or `arcgis.FEEDS` (ArcGIS).

It stops at candidates on purpose: schemas differ per portal, so a human still
confirms the lat/lon fields before adding a feed. This turns "find feeds across
50 states" from weeks of hunting into a vetting queue.

    python -m opencam.discover
    python -m opencam.discover --platform arcgis --query "red light camera"
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request

_CATALOG = "https://api.us.socrata.com/api/catalog/v1"
_ARCGIS_HUB = "https://hub.arcgis.com/api/v3/datasets"
_USER_AGENT = "opencam/0.1 (+https://github.com/opsec-bot/opencam)"

# A dataset is about *locations* if its name looks like a camera list and not
# like a record of what the cameras caught.
_WANT = ("camera", "enforcement", "alpr", "automated")
_REJECT = ("violation", "citation", "fine", "offence", "offense", "ticket",
           "revenue", "performance", "count", "proposed", "metric", "stays")

# Hosts/owners outside the US that keep matching "speed camera".
_FOREIGN = (".act.gov.au", ".edmonton.ca", ".gov.au", ".ca")
# Name tokens that mark an obviously non-US ArcGIS result (owner names vary, so
# this is best-effort; the human vetting the candidate is the real filter).
_FOREIGN_TOKENS = ("ottawa", "toronto", "waterloo", "kingston", "canada",
                   "ontario", "london uk", "queensland", "nsw")


def _looks_like_locations(name: str) -> bool:
    n = name.lower()
    if any(bad in n for bad in _REJECT):
        return False
    if not any(w in n for w in _WANT):
        return False
    return "location" in n or n.endswith("cameras") or "camera locations" in n


def _is_us(domain: str) -> bool:
    return not any(domain.endswith(suf) for suf in _FOREIGN)


def discover(query: str, limit: int) -> list[dict]:
    params = urllib.parse.urlencode({"q": query, "only": "dataset", "limit": limit})
    req = urllib.request.Request(f"{_CATALOG}?{params}",
                                 headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    out = []
    for r in data.get("results", []):
        res = r.get("resource", {})
        domain = r.get("metadata", {}).get("domain", "")
        name = res.get("name", "")
        if not _is_us(domain):
            continue
        if not _looks_like_locations(name):
            continue
        out.append({"domain": domain, "dataset": res.get("id", ""), "name": name})
    return out


def discover_arcgis(query: str, limit: int) -> list[dict]:
    params = urllib.parse.urlencode({"q": query, "page[size]": limit})
    req = urllib.request.Request(f"{_ARCGIS_HUB}?{params}",
                                 headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    out = []
    for r in data.get("data", []):
        a = r.get("attributes", {})
        name = a.get("name", "")
        url = a.get("url", "") or ""
        owner = (a.get("owner", "") or "").lower()
        if "FeatureServer" not in url and "MapServer" not in url:
            continue  # need a queryable REST layer
        if not _looks_like_locations(name):
            continue
        if any(tok in name.lower() or tok in owner for tok in _FOREIGN_TOKENS):
            continue
        out.append({"domain": owner or "arcgis", "dataset": url, "name": name})
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="opencam.discover")
    p.add_argument("--query", default="speed camera locations")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--platform", choices=("socrata", "arcgis", "all"), default="all")
    args = p.parse_args(argv)

    found = {}
    if args.platform in ("socrata", "all"):
        found["Socrata (-> sources/municipal.py)"] = discover(args.query, args.limit)
    if args.platform in ("arcgis", "all"):
        found["ArcGIS (-> sources/arcgis.py)"] = discover_arcgis(args.query, args.limit)

    total = sum(len(v) for v in found.values())
    if not total:
        print("no candidate location datasets found")
        return 0

    for platform, candidates in found.items():
        if not candidates:
            continue
        print(f"\n{platform}: {len(candidates)} candidate(s) to vet")
        for c in candidates:
            print(f"  {c['domain']:30} {c['name'][:40]:40} {c['dataset']}")
    print("\nVet each (confirm it has lat/lon), then add a feed line to the named module.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
