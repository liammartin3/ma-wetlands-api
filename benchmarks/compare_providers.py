"""Compare pygeoapi feature providers on the real GeoPackage: correctness
(against GeoPandas ground truth) and latency.

    docker compose -f benchmarks/docker-compose.yml up -d   # see benchmarks/README.md
    python benchmarks/compare_providers.py --base http://localhost:5001

Writes reports/provider_comparison.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

COLLECTIONS = ["ogr", "ogr_paging", "sqlite"]
GPKG = Path("data/build/ma_wetlands.gpkg")

# Concord-area bbox (~1.2k features: many pages) and a larger Quabbin-area bbox
BBOX_SMALL = (-71.40, 42.42, -71.30, 42.50)
BBOX_LARGE = (-72.40, 42.25, -72.20, 42.45)
PAGE = 50
REPEATS = 5


def get(base: str, coll: str, **params) -> tuple[dict, float]:
    params.setdefault("f", "json")
    url = f"{base}/collections/{coll}/items?{urllib.parse.urlencode(params)}"
    t = time.perf_counter()
    with urllib.request.urlopen(url, timeout=120) as r:
        body = json.load(r)
    return body, (time.perf_counter() - t) * 1000


def ids(fc: dict) -> list[str]:
    return [f["id"] for f in fc["features"]]


def median_ms(base, coll, **params) -> float:
    return round(statistics.median(get(base, coll, **params)[1] for _ in range(REPEATS)), 1)


def page_all(base, coll, max_pages, **params) -> list[str]:
    out: list[str] = []
    for p in range(max_pages):
        fc, _ = get(base, coll, limit=PAGE, offset=p * PAGE, **params)
        out += ids(fc)
        if len(fc["features"]) < PAGE:
            break
    return out


def evaluate(base: str, coll: str, truth: dict) -> dict:
    r: dict = {}
    bb = ",".join(map(str, BBOX_SMALL))

    # 1. bbox page 1: every returned feature must really intersect the bbox
    first = ids(get(base, coll, bbox=bb, limit=PAGE)[0])
    r["bbox_page1_all_correct"] = set(first) <= truth["small"]

    # 2. Page through the whole bbox result; must equal ground truth, no repeats
    max_pages = len(truth["small"]) // PAGE + 3
    paged = page_all(base, coll, max_pages, bbox=bb)
    r["bbox_paged_count"] = len(paged)
    r["bbox_truth_count"] = len(truth["small"])
    r["bbox_paged_unique"] = len(set(paged))
    r["bbox_paged_wrong"] = len(set(paged) - truth["small"])
    r["bbox_paging_correct"] = set(paged) == truth["small"] and len(paged) == len(set(paged))

    # 3. Unfiltered paging: page 2 must differ from page 1
    p1 = ids(get(base, coll, limit=10, offset=0)[0])
    p2 = ids(get(base, coll, limit=10, offset=10)[0])
    r["offset_changes_page"] = bool(p2) and set(p1).isdisjoint(p2)

    # 4. Attribute filter
    lakes = get(base, coll, WETLAND_TYPE="Lake", limit=100)[0]["features"]
    r["attribute_filter_correct"] = bool(lakes) and all(f["properties"]["WETLAND_TYPE"] == "Lake" for f in lakes)

    # 5. Latency (median of REPEATS, milliseconds, limit=100)
    r["ms_bbox_small"] = median_ms(base, coll, bbox=bb, limit=100)
    r["ms_bbox_large"] = median_ms(base, coll, bbox=",".join(map(str, BBOX_LARGE)), limit=100)
    r["ms_attribute_filter"] = median_ms(base, coll, WETLAND_TYPE="Lake", limit=100)
    r["ms_bbox_page_20"] = median_ms(base, coll, bbox=bb, limit=PAGE, offset=PAGE * 19)
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5001")
    ap.add_argument("--out", type=Path, default=Path("reports/provider_comparison.json"))
    args = ap.parse_args()

    gdf = gpd.read_file(GPKG, columns=["NWI_ID"])
    truth = {"small": set(gdf.loc[gdf.intersects(box(*BBOX_SMALL)), "NWI_ID"])}

    results = {c: evaluate(args.base, c, truth) for c in COLLECTIONS}
    payload = {
        "bbox_small": BBOX_SMALL,
        "bbox_large": BBOX_LARGE,
        "page_size": PAGE,
        "repeats": REPEATS,
        "note": "Latencies measured on the developer machine via Docker; compare relatively, not absolutely.",
        "results": results,
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n")

    keys = list(next(iter(results.values())).keys())
    print(f"{'':28}" + "".join(f"{c:>14}" for c in COLLECTIONS))
    for k in keys:
        print(f"{k:28}" + "".join(f"{results[c][k]!s:>14}" for c in COLLECTIONS))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
