# Massachusetts Wetlands API

OGC API - Features service for the U.S. Fish & Wildlife Service National Wetlands
Inventory (NWI) in Massachusetts, with automated data quality checks.

> Work in progress. Phase 1 (data + validation) is in place; the API, CI and
> deployment sections will be added in later phases.

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
