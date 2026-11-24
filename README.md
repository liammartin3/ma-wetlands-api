# Massachusetts Wetlands API

OGC API - Features service for the U.S. Fish & Wildlife Service National Wetlands
Inventory (NWI) in Massachusetts, with automated data quality checks.

> Work in progress. Phases 1 (data + validation) and 2 (API, tests, CI) are in
> place; deployment will be added in Phase 3.

## Phase 1: build the data

Requires Python 3.11+.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

./scripts/download.sh              # NWI MA GeoPackage -> data/raw/
python -m wetlands.build           # QA checks -> data/build/ma_wetlands.gpkg
pytest                             # unit + end-to-end tests (synthetic data)
```

The build exits non-zero and writes no GeoPackage if any check fails.
Every build writes [`reports/qa_report.md`](reports/qa_report.md) and
[`reports/qa_report.json`](reports/qa_report.json). Expected values and tolerances
live in [`config/qa.yml`](config/qa.yml).

## Phase 2: run the API

Requires Docker.

```bash
docker compose up -d --wait        # pygeoapi 0.24.0 -> http://localhost:5050
pytest                             # now also runs tests/api against the live server
docker compose down
```

Port 5050 is used because macOS AirPlay Receiver occupies 5000.

Try it:

- Landing page: http://localhost:5050/
- Items as GeoJSON: http://localhost:5050/collections/wetlands/items?f=json
- Bbox: http://localhost:5050/collections/wetlands/items?bbox=-71.40,42.42,-71.30,42.50
- Filter by type: http://localhost:5050/collections/wetlands/items?WETLAND_TYPE=Lake
- OpenAPI / Swagger UI: http://localhost:5050/openapi

CI (`.github/workflows/ci.yml`) runs lint and unit tests, then starts the
service on a 2 MB sample GeoPackage (`tests/fixtures/`, made by
`scripts/make_fixture.py`) and runs the API tests.

Which pygeoapi provider, and why: see [`benchmarks/README.md`](benchmarks/README.md).
