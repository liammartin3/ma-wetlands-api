# Massachusetts Wetlands API

OGC API - Features service for the U.S. Fish & Wildlife Service National Wetlands
Inventory (NWI) in Massachusetts, with automated data quality checks.

**Live API: https://54-211-175-202.sslip.io/** (custom domain coming)

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

NWI's "Massachusetts" download also covers a strip of the neighboring states, so
the build clips features to the Massachusetts state line from the U.S. Census
TIGER/Line boundary (state waters included) and checks that every feature is
inside it. The download script fetches that boundary too.
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

## Phase 3: deploy to AWS Lightsail

```
Internet ──443/80──> Caddy (auto HTTPS) ──> pygeoapi :80 ──> ma_wetlands.gpkg
                     └──────── Docker Compose on one Lightsail instance ────────┘
```

### Cost (from [`reports/cost_estimate.json`](reports/cost_estimate.json))

`python scripts/estimate_costs.py` reads the public AWS Price List (us-east-1, on-demand,
744-hour month):

| Option | What you get | $/month |
|---|---|---:|
| **Lightsail 2 GB (chosen)** | 2 GB RAM, 2 vCPU, 60 GB SSD, 3 TB transfer, static IP | **11.99** |
| Lightsail 1 GB | 1 GB RAM, 2 vCPU, 40 GB SSD, 2 TB transfer, static IP | 6.99 |
| EC2 t4g.small | 2 GiB RAM, 2 vCPU + 20 GB gp3 + public IPv4 | 17.82 |
| EC2 t4g.micro | 1 GiB RAM, 2 vCPU + 20 GB gp3 + public IPv4 | 11.57 |

Excluded: data transfer beyond bundle/free allowance, domain + DNS, AWS Budgets, snapshots, taxes, free-tier credits.

### Deploy

```bash
brew install hashicorp/tap/terraform
cp infra/terraform.tfvars.example infra/terraform.tfvars   # fill in; gitignored

aws sts get-caller-identity --profile liam-cli   # confirm the account ID
terraform -chdir=infra init
terraform -chdir=infra plan -out tfplan                    # review before applying
terraform -chdir=infra apply tfplan

./scripts/deploy.sh                                        # copy app + data, start Docker
API_URL=https://<ip-with-dashes>.sslip.io pytest tests/api # test the live service
```

`allowed_account_ids` in the provider makes Terraform refuse to touch any account
other than the one in `terraform.tfvars`.

### Tear down

```bash
terraform -chdir=infra destroy
```

This deletes the instance, static IP, key pair, firewall rules and budget alert.
The stack creates no snapshots, databases, or load balancers, so nothing billable
should remain; check the Lightsail console to confirm.

### Live performance

Measured with `python scripts/measure_latency.py` against the live server
(2026-11-24, 5 requests each, from a home connection;
[`reports/live_latency.json`](reports/live_latency.json)):

| Query | Median ms | Max ms |
|---|---:|---:|
| `landing_page` | 48 | 229 |
| `items_default_page` | 1,114 | 1,249 |
| `items_limit_1` | 1,129 | 1,231 |
| `bbox_concord_100` | 2,752 | 2,832 |
| `bbox_quabbin_100` | 1,606 | 1,758 |
| `filter_lake_100` | 1,564 | 1,653 |

Every items request takes over a second, even unfiltered ones. This is the known
cost of the stock `SQLiteGPKG` provider, which scans the whole table rather than
using the spatial index (see [`benchmarks/README.md`](benchmarks/README.md)).
Moving to PostGIS is the planned fix if speed becomes a priority.
