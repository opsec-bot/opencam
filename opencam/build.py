"""Orchestrator CLI: fetch every source for every region, dedupe, write packs.

    python -m opencam.build --out dist
    python -m opencam.build --out dist --regions us-ca us-tx
    python -m opencam.build --out dist --base-url https://opsec-bot.github.io/opencam

Kept deliberately linear so a CI log reads top to bottom: per region, per
source, how many records, then the global dedupe and pack counts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import __version__
from .dedupe import dedupe
from .packs import build_packs
from .sources import osm

# Source registry. Each value is a fetch_region(region_id, bbox) callable.
# Adding DeFlock / municipal portals later is one entry each.
SOURCES = {
    "osm": osm.fetch_region,
}

_REGIONS_PATH = os.path.join(os.path.dirname(__file__), "regions.json")


def load_regions() -> dict:
    with open(_REGIONS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="opencam.build", description="Build camera packs.")
    p.add_argument("--out", default="dist", help="output directory (default: dist)")
    p.add_argument("--regions", nargs="*", help="region ids to build (default: all)")
    p.add_argument("--sources", nargs="*", default=list(SOURCES),
                   help=f"sources to pull (default: {' '.join(SOURCES)})")
    p.add_argument("--base-url", default=".",
                   help="URL the manifest should point packs at")
    p.add_argument("--sleep", type=float, default=2.0,
                   help="seconds to pause between fetches, to be kind to Overpass")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    all_regions = load_regions()

    if args.regions:
        unknown = [r for r in args.regions if r not in all_regions]
        if unknown:
            print(f"unknown regions: {', '.join(unknown)}", file=sys.stderr)
            return 2
        regions = {r: all_regions[r] for r in args.regions}
    else:
        regions = all_regions

    bad_src = [s for s in args.sources if s not in SOURCES]
    if bad_src:
        print(f"unknown sources: {', '.join(bad_src)}", file=sys.stderr)
        return 2

    print(f"opencam {__version__}: {len(regions)} region(s), "
          f"sources: {', '.join(args.sources)}")

    collected: list[dict] = []
    for rid, meta in regions.items():
        for sname in args.sources:
            fetch = SOURCES[sname]
            try:
                recs = fetch(rid, meta["bbox"])
            except Exception as exc:  # one source/region failing must not sink the run
                print(f"  {rid} [{sname}] FAILED: {exc}", file=sys.stderr)
                continue
            print(f"  {rid} [{sname}]: {len(recs)} records")
            collected.extend(recs)
            if args.sleep:
                time.sleep(args.sleep)

    print(f"collected {len(collected)} raw records; deduping...")
    merged = dedupe(collected)
    print(f"{len(merged)} unique cameras after dedupe "
          f"({len(collected) - len(merged)} merged)")

    manifest = build_packs(merged, regions, args.out, args.base_url)
    kept = len(manifest["regions"])
    total = sum(r["cameraCount"] for r in manifest["regions"])
    print(f"wrote {kept} pack(s), {total} cameras, manifest at "
          f"{os.path.join(args.out, 'manifest.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
