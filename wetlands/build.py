"""Build the served GeoPackage from the raw NWI download.

    python -m wetlands.build --input data/raw/MA_geopackage_wetlands.gpkg

Pipeline: read -> clean -> QA checks -> (fail, or) write GeoPackage with
spatial index -> verify output -> write QA report. The report is written
even when checks fail, so you can see why.
"""
from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pyogrio
import pyproj
import shapely
import yaml

from . import clean, qa
from .report import write_report

ATTRIBUTE_INDEXES = ["WETLAND_TYPE", "ATTRIBUTE", "NWI_ID"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_checks(gdf: gpd.GeoDataFrame, cfg: dict, extent, repaired: int) -> list[qa.CheckResult]:
    f, a = cfg["fields"], cfg["acres"]
    results = [
        qa.check_crs(gdf, cfg["crs"]["expected_source_epsg"]),
        qa.check_required_fields(gdf, f["required"]),
    ]
    if not results[-1].passed:
        return results  # later checks depend on these fields
    results += [
        qa.check_attribute_codes(gdf, f["attribute_pattern"]),
        qa.check_wetland_types(gdf, f["wetland_types"]),
        qa.check_geometries(gdf, repaired),
        qa.check_duplicates(gdf, f["id_field"]),
    ]
    if results[0].passed:  # area check needs the equal-area CRS
        results.append(
            qa.check_acres(gdf, a["relative_tolerance"], a["absolute_tolerance"], extent, a["extent_buffer_m"])
        )
    return results


def load_state_boundary(cfg: dict, crs) -> shapely.Geometry:
    sb = cfg["state_boundary"]
    states = gpd.read_file(sb["path"], engine="pyogrio")
    state = states[states[sb["field"]] == sb["value"]]
    if len(state) != 1:
        raise RuntimeError(f"expected 1 boundary with {sb['field']}={sb['value']}, found {len(state)}")
    geom = state.to_crs(crs).union_all()
    shapely.prepare(geom)
    return geom


def write_gpkg(gdf: gpd.GeoDataFrame, path: Path, layer: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.gpkg")
    tmp.unlink(missing_ok=True)
    pyogrio.write_dataframe(gdf, tmp, layer=layer, driver="GPKG", layer_options={"SPATIAL_INDEX": "YES"})
    with sqlite3.connect(tmp) as con:
        for col in ATTRIBUTE_INDEXES:
            con.execute(f'CREATE INDEX "idx_{layer}_{col.lower()}" ON "{layer}" ("{col}")')
        con.execute("ANALYZE")
    tmp.replace(path)  # atomic: a failed build never leaves a half-written file


def verify_gpkg(path: Path, layer: str, expected_count: int, expected_epsg: int) -> dict:
    """Re-open the written file and confirm it is what we meant to write."""
    info = pyogrio.read_info(path, layer=layer)
    with sqlite3.connect(path) as con:
        rtree = con.execute(
            "SELECT count(*) FROM gpkg_extensions WHERE table_name=? AND extension_name='gpkg_rtree_index'",
            (layer,),
        ).fetchone()[0] > 0
        geom_col = con.execute(
            "SELECT column_name FROM gpkg_geometry_columns WHERE table_name=?", (layer,)
        ).fetchone()[0]
        rtree_rows = con.execute(f'SELECT count(*) FROM "rtree_{layer}_{geom_col}"').fetchone()[0] if rtree else 0
        idx = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?", (layer,))]
    problems = []
    if info["features"] != expected_count:
        problems.append(f"feature count {info['features']} != {expected_count}")
    if not rtree or rtree_rows != expected_count:
        problems.append(f"spatial index missing or incomplete ({rtree_rows} rows)")
    if not pyproj.CRS(info["crs"]).equals(pyproj.CRS.from_epsg(expected_epsg), ignore_axis_order=True):
        problems.append(f"output CRS {info['crs']} != EPSG:{expected_epsg}")
    if problems:
        raise RuntimeError("Output verification failed: " + "; ".join(problems))
    return {
        "path": str(path),
        "layer": layer,
        "epsg": expected_epsg,
        "features": info["features"],
        "spatial_index": rtree,
        "attribute_indexes": sorted(i for i in idx if i.startswith("idx_")),
        "size_bytes": path.stat().st_size,
    }


def build(input_path: Path, cfg: dict) -> int:
    t0 = time.time()
    src, out_cfg = cfg["source"], cfg["output"]
    report = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": {"url": src["url"], "file": str(input_path), "sha256": sha256(input_path),
                   "layer": src["wetlands_layer"]},
        "versions": {
            "python": sys.version.split()[0], "geopandas": gpd.__version__, "shapely": shapely.__version__,
            "pyogrio": pyogrio.__version__, "gdal": pyogrio.__gdal_version_string__, "pyproj": pyproj.__version__,
        },
        "counts": {},
    }

    gdf = gpd.read_file(input_path, layer=src["wetlands_layer"], engine="pyogrio")
    extent = gpd.read_file(input_path, layer=src["nwi_extent_layer"], engine="pyogrio")
    extent = extent.to_crs(gdf.crs).union_all() if gdf.crs else None
    report["counts"]["input"] = len(gdf)
    report["state_boundary"] = {k: cfg["state_boundary"][k] for k in ("url", "field", "value")}

    # Cleaning (each step reports what it changed)
    gdf = gdf.rename_geometry("geom")
    gdf, n_dupes = clean.drop_exact_duplicates(gdf)
    gdf, n_repaired = clean.repair_geometries(gdf)
    report["counts"]["exact_duplicates_dropped"] = n_dupes
    report["counts"]["geometries_repaired"] = n_repaired

    checks = run_checks(gdf, cfg, extent, n_repaired)

    # Clip to the authoritative state line, then check the result.
    if all(c.passed for c in checks):
        state = load_state_boundary(cfg, gdf.crs)
        gdf, n_outside, n_clipped, n_slivers = clean.clip_to_boundary(
            gdf, state, cfg["state_boundary"]["min_clipped_area_m2"]
        )
        report["counts"]["outside_state_dropped"] = n_outside
        report["counts"]["clipped_at_state_line"] = n_clipped
        report["counts"]["clip_slivers_dropped"] = n_slivers
        checks += [
            qa.check_within_boundary(gdf, state, cfg["state_boundary"]["tolerance_m"]),
            qa.check_geometries(gdf, n_repaired),
        ]
        checks[-1].name = "geometry_validity_after_clip"

    for c in checks:
        print(f"[{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.summary}")

    if not all(c.passed for c in checks):
        json_path, _ = write_report(report, checks, Path(out_cfg["report_dir"]))
        print(f"\nBuild FAILED. GeoPackage not written. See {json_path}", file=sys.stderr)
        return 1

    # Transform for serving
    gdf["ACRES_GEOM"] = qa.acres_from_geometry(gdf).round(4)
    gdf = clean.to_multipolygon(gdf).to_crs(epsg=cfg["crs"]["output_epsg"])
    keep = ["NWI_ID", "ATTRIBUTE", "WETLAND_TYPE", "ACRES", "ACRES_GEOM", "QAQC_CODE", "geom"]
    gdf = gdf[keep]

    out_path = Path(out_cfg["path"])
    write_gpkg(gdf, out_path, out_cfg["layer"])
    report["output"] = verify_gpkg(out_path, out_cfg["layer"], len(gdf), cfg["crs"]["output_epsg"])
    report["counts"]["output"] = len(gdf)
    report["build_seconds"] = round(time.time() - t0, 1)

    json_path, md_path = write_report(report, checks, Path(out_cfg["report_dir"]))
    print(f"\nBuild PASSED: {len(gdf):,} features -> {out_path}\nReport: {md_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", type=Path, default=Path("data/raw/MA_geopackage_wetlands.gpkg"))
    ap.add_argument("--config", type=Path, default=Path("config/qa.yml"))
    args = ap.parse_args(argv)
    cfg = yaml.safe_load(args.config.read_text())
    try:
        return build(args.input, cfg)
    except Exception as e:  # noqa: BLE001 - top-level: clear message + non-zero exit
        print(f"Build ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
