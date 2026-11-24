"""Measure response times of a running API (median of several requests).

    python scripts/measure_latency.py --base https://<host> --out reports/live_latency.json

Times are measured from wherever this runs, so they include network time.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

REPEATS = 5
QUERIES = {
    "landing_page": ("/", {}),
    "items_default_page": ("/collections/wetlands/items", {}),
    "items_limit_1": ("/collections/wetlands/items", {"limit": 1}),
    "bbox_concord_100": ("/collections/wetlands/items", {"bbox": "-71.40,42.42,-71.30,42.50", "limit": 100}),
    "bbox_quabbin_100": ("/collections/wetlands/items", {"bbox": "-72.40,42.25,-72.20,42.45", "limit": 100}),
    "filter_lake_100": ("/collections/wetlands/items", {"WETLAND_TYPE": "Lake", "limit": 100}),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    s = requests.Session()
    results = {}
    for name, (path, params) in QUERIES.items():
        times = []
        for _ in range(REPEATS):
            t = time.perf_counter()
            r = s.get(args.base.rstrip("/") + path, params={**params, "f": "json"}, timeout=120)
            r.raise_for_status()
            times.append((time.perf_counter() - t) * 1000)
        results[name] = {"median_ms": round(statistics.median(times)), "max_ms": round(max(times))}
        print(f"{name:22} median {results[name]['median_ms']:>6} ms   max {results[name]['max_ms']:>6} ms")

    args.out.write_text(json.dumps({
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "base": args.base,
        "repeats": REPEATS,
        "results": results,
    }, indent=2) + "\n")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
