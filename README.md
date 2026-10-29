# opencam

Open, multi-source traffic-enforcement camera data. Public data, public code.

opencam pulls speed, red-light and ALPR/Flock camera locations from open
sources, merges duplicates across them, and publishes small per-region packs
with a hash-verified manifest. Any app can point at the manifest and render a
fresh, deduped camera layer without scraping anyone or paying for a feed.

## Why

Most apps that show enforcement cameras either ship a dataset that goes stale
in months or scrape a closed feed. opencam is the upstream instead: rebuilt on a
schedule, multi-source, with provenance on every record.

## Data sources

| Source | Covers | License |
| --- | --- | --- |
| OpenStreetMap (Overpass) | speed, red-light, ALPR worldwide | ODbL |
| DeFlock *(planned)* | Flock / ALPR, crowd-sourced | ODbL |
| US municipal open-data portals *(planned)* | authoritative fixed cameras | varies, open |

Nothing here is scraped from a closed service. See
[`ATTRIBUTION.md`](ATTRIBUTION.md).

## Output

- `manifest.json` — lists every region with its bbox, pack URL, byte size,
  SHA-256 and camera count.
- `packs/<region>.json` — the cameras for one region.

Record shape is in [`schema.json`](schema.json). Example camera:

```json
{
  "id": "osm:node/123456",
  "type": "alpr",
  "lat": 32.7767,
  "lon": -96.797,
  "direction": 270,
  "operator": "Flock Safety",
  "sources": ["osm", "deflock"],
  "lastVerified": "2026-10-20",
  "confidence": 0.8
}
```

## Build it yourself

No dependencies beyond the Python 3.10+ standard library.

```bash
# one state, written to ./dist
python -m opencam.build --out dist --regions us-tx

# everything, with the public manifest URL baked in
python -m opencam.build --out dist --base-url https://opsec-bot.github.io/opencam
```

A GitHub Actions workflow rebuilds the full dataset weekly and publishes it to
GitHub Pages, so the hosted manifest stays fresh.

## Consuming the data

Read `manifest.json`, keep the `packSha256` for each region you cache, and only
re-download a pack when its hash changes. `confidence` lets you hide thin
single-source records if you want a stricter map.

## License

- Code: MIT (see [`LICENSE`](LICENSE)).
- Data: ODbL, because it is derived from OpenStreetMap. Keep the attribution.
