"""Write the data quality report as JSON (machine-readable, source of truth for
README figures) and Markdown (human-readable)."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .qa import CheckResult


def write_report(report: dict[str, Any], checks: list[CheckResult], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {**report, "checks": [asdict(c) for c in checks]}
    payload["passed"] = all(c.passed for c in checks)

    json_path = out_dir / "qa_report.json"
    json_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")

    md_path = out_dir / "qa_report.md"
    md_path.write_text(_markdown(payload))
    return json_path, md_path


def _markdown(p: dict[str, Any]) -> str:
    status = "PASSED" if p["passed"] else "FAILED"
    c = p["counts"]
    lines = [
        "# Data quality report",
        "",
        f"**Status: {status}**  ",
        f"Built: {p['built_at']}  ",
        f"Source: {p['source']['url']}  ",
        f"Input file: `{p['source']['file']}` (layer `{p['source']['layer']}`)  ",
        f"Input file SHA-256: `{p['source']['sha256']}`",
        "",
        "## Counts",
        "",
        "| Stage | Features |",
        "|---|---:|",
        f"| Read from source | {c['input']:,} |",
        f"| Exact duplicates dropped | {c['exact_duplicates_dropped']:,} |",
        f"| Geometries repaired | {c['geometries_repaired']:,} |",
        f"| Written to GeoPackage | {c.get('output', 0):,} |",
        "",
        "## Checks",
        "",
        "| Check | Result | Summary |",
        "|---|---|---|",
    ]
    for chk in p["checks"]:
        lines.append(f"| {chk['name']} | {'pass' if chk['passed'] else '**FAIL**'} | {chk['summary']} |")

    wt = next((x for x in p["checks"] if x["name"] == "wetland_types"), None)
    if wt:
        lines += ["", "## Features by wetland type", "", "| Wetland type | Features |", "|---|---:|"]
        for k, v in sorted(wt["details"]["counts"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| {k} | {v:,} |")

    ac = next((x for x in p["checks"] if x["name"] == "acres"), None)
    if ac:
        d = ac["details"]
        lines += [
            "",
            "## ACRES vs. geometry area",
            "",
            f"Tolerance: {d['relative_tolerance']:.0%} or {d['absolute_tolerance']} acres, whichever is larger.",
            "",
            (
                f"- Mismatches: {d['mismatches_total']:,} "
                f"({d['mismatches_on_state_boundary']:,} on the state boundary, "
                f"{d['mismatches_interior']:,} interior)"
            ),
            f"- Sum of stored ACRES: {d['acres_stored_total']:,.1f}",
            f"- Sum of geometry area (acres, EPSG:5070): {d['acres_geometry_total']:,.1f}",
            "",
            "Boundary mismatches are expected: NWI clips polygons to the state line but keeps the",
            "unclipped ACRES. The output keeps the published `ACRES` and adds `ACRES_GEOM`.",
        ]

    out = p.get("output")
    if out:
        lines += [
            "",
            "## Output",
            "",
            f"- File: `{out['path']}` (layer `{out['layer']}`, EPSG:{out['epsg']})",
            f"- Spatial index (R-tree) present: {out['spatial_index']}",
            f"- Attribute indexes: {', '.join(out['attribute_indexes']) or 'none'}",
            f"- Size: {out['size_bytes']:,} bytes",
        ]

    lines += ["", "## Environment", ""]
    lines += [f"- {k}: {v}" for k, v in p["versions"].items()]
    return "\n".join(lines) + "\n"
