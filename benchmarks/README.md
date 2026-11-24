# Provider comparison

pygeoapi 0.24.0 has two providers that can read a GeoPackage. This experiment
serves the same built GeoPackage three ways and checks each against GeoPandas
ground truth. Results: [`reports/provider_comparison.json`](../reports/provider_comparison.json).

| Setup | Provider |
|---|---|
| `ogr` | `OGR`, default settings (paging off) |
| `ogr_paging` | `OGR` with `source_capabilities: {paging: true}` |
| `sqlite` | `SQLiteGPKG` |

## What we found

- **`OGR`, paging off:** `offset` is ignored, so every page returns the same features.
- **`OGR`, paging on:** paging through a bbox result returns duplicates and misses
  features. Cause (from the provider source): `offset=0` reads the layer directly
  (R-tree order) while `offset>0` runs `SELECT ... LIMIT/OFFSET` (row-id order), so
  page 1 overlaps later pages. GDAL itself pages correctly when every page uses
  the same SQL path.
- **`SQLiteGPKG`:** correct on every test, but slower: its bbox filter
  (`Intersects(geom, BuildMbr(...))` on a SpatiaLite virtual table) doesn't use the
  GeoPackage R-tree, so each query scans the table. It also needs the GeoPackage
  to be **writable** (SpatiaLite's `AutoGPKGStart()` returns 0 on a read-only file).

**Decision:** stock `SQLiteGPKG`. Correct results with no custom code beat speed
for this project; the next step for scale would be PostGIS (see main README).

## Re-run

```bash
mkdir -p data/bench && cp data/build/ma_wetlands.gpkg data/bench/
docker run -d --name wl-bench -p 5001:80 \
  -e PYGEOAPI_SERVER_URL=http://localhost:5001 \
  -v "$PWD/benchmarks/providers.config.yml:/pygeoapi/local.config.yml:ro" \
  -v "$PWD/data/build:/data:ro" -v "$PWD/data/bench:/data-rw" \
  geopython/pygeoapi:0.24.0
python benchmarks/compare_providers.py --base http://localhost:5001
docker rm -f wl-bench
```

Latencies are from a laptop via Docker; compare them relative to each other.
