"""Find municipal camera datasets across every Socrata portal, nationwide.

Hand-coding hundreds of cities doesn't scale. But most US open-data portals run
Socrata, and Socrata has one cross-domain catalog API that searches them all. So
`discover` queries that catalog, filters out the noise (violation/fine/citation
feeds, performance dashboards, non-US domains), and prints the *candidate*
location datasets with the exact `host` and `dataset` id to drop into
`municipal.FEEDS`.

It stops at candidates on purpose: schemas differ per portal, so a human still
confirms the lat/lon fields before adding a feed. This turns "find feeds across
50 states" from weeks of hunting into a vetting queue.

    python -m opencam.discover
    python -m opencam.discover --query "red light camera" --limit 60
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request

_CATALOG = "https://api.us.socrata.com/api/catalog/v1"
_USER_AGENT = "opencam/0.1 (+https://github.com/opsec-bot/opencam)"

# A dataset is about *locations* if its name looks like a camera list and not
# like a record of what the cameras caught.
_WANT = ("camera", "enforcement", "alpr", "automated")
_REJECT = ("violation", "citation", "fine", "offence", "offense", "ticket",
           "revenue", "performance", "count", "proposed", "metric", "stays")

# Socrata hosts outside the US that keep matching "speed camera".
_FOREIGN = (".act.gov.au", ".edmonton.ca", ".gov.au", ".ca")


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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="opencam.discover")
    p.add_argument("--query", default="speed camera locations")
    p.add_argument("--limit", type=int, default=40)
    args = p.parse_args(argv)

    candidates = discover(args.query, args.limit)
    if not candidates:
        print("no candidate location datasets found")
        return 0

    print(f"{len(candidates)} candidate location dataset(s) to vet:\n")
    for c in candidates:
        print(f"  {c['domain']:34} {c['dataset']}  {c['name']}")
    print("\nVet each (confirm it has lat/lon), then add a SocrataFeed line to "
          "opencam/sources/municipal.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
