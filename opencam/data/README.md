# Community data

## `mobile_lprs.json` — mobile ALPR reports

Trailer-mounted and construction-zone license-plate readers move, so they are
never in OpenStreetMap. This file is opencam's layer for them. It ships empty;
entries come from real reports and **expire** so a unit that has moved on stops
alerting.

Each entry:

```json
{
  "lat": 38.9000,
  "lon": -77.0300,
  "operator": "Flock Safety",
  "direction": "NB",
  "lastVerified": "2026-10-29",
  "ttlDays": 45,
  "id": "optional-stable-id"
}
```

| Field | Required | Meaning |
|-------|:--------:|---------|
| `lat`, `lon` | yes | Decimal degrees. |
| `lastVerified` | yes | ISO date the unit was last confirmed here. Entries older than `ttlDays` are dropped at build time. |
| `ttlDays` | no | How long the report stays live (default 45). Shorter for a unit you expect to move soon. |
| `operator` | no | e.g. `Flock Safety`, `Motorola`. |
| `direction` | no | Compass point (`NB`/`SE`/...) or degrees the reader faces. |
| `id` | no | Stable id; otherwise derived from the coordinates. |

Confidence starts at 0.5 and decays linearly to its floor as the entry ages
toward its TTL, and rises if an independent source (OSM, a city feed) confirms
the same spot. Submit entries by PR.
