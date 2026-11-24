"""End-to-end tests of the build: good data produces an indexed GeoPackage and
a passing report; bad data fails clearly and writes no GeoPackage."""
import json
import sqlite3
from pathlib import Path

import geopandas as gpd
import pyogrio

from wetlands.build import build


def _write_source(path: Path, wetlands: gpd.GeoDataFrame, state) -> Path:
    pyogrio.write_dataframe(wetlands, path, layer="MA_Wetlands", driver="GPKG")
    boundary = gpd.GeoDataFrame({"ST_ABBV": ["MA"]}, geometry=[state], crs=wetlands.crs)
    pyogrio.write_dataframe(boundary, path, layer="Massachusetts", driver="GPKG", append=True)
    return path


def test_build_success(tmp_path, good_gdf, state, cfg):
    src = _write_source(tmp_path / "src.gpkg", good_gdf, state)
    assert build(src, cfg) == 0

    out = Path(cfg["output"]["path"])
    info = pyogrio.read_info(out, layer="wetlands")
    assert info["features"] == 3
    assert "ACRES_GEOM" in info["fields"]
    with sqlite3.connect(out) as con:
        ext = con.execute("SELECT extension_name FROM gpkg_extensions WHERE table_name='wetlands'").fetchall()
    assert ("gpkg_rtree_index",) in ext

    report = json.loads((Path(cfg["output"]["report_dir"]) / "qa_report.json").read_text())
    assert report["passed"] is True
    assert report["counts"] == {"input": 3, "exact_duplicates_dropped": 0, "geometries_repaired": 0, "output": 3}
    assert report["output"]["spatial_index"] is True


def test_build_fails_on_bad_data(tmp_path, good_gdf, state, cfg):
    good_gdf.loc[0, "WETLAND_TYPE"] = "Not a wetland type"
    src = _write_source(tmp_path / "src.gpkg", good_gdf, state)
    assert build(src, cfg) == 1
    assert not Path(cfg["output"]["path"]).exists()

    report = json.loads((Path(cfg["output"]["report_dir"]) / "qa_report.json").read_text())
    failed = [c["name"] for c in report["checks"] if not c["passed"]]
    assert report["passed"] is False and failed == ["wetland_types"]


def test_build_fails_on_wrong_crs(tmp_path, good_gdf, state, cfg):
    src = _write_source(tmp_path / "src.gpkg", good_gdf.to_crs(3857), gpd.GeoSeries([state], crs=5070).to_crs(3857)[0])
    assert build(src, cfg) == 1
