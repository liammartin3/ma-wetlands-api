"""Unit tests for each data quality check and cleaning step."""
import geopandas as gpd
import pandas as pd
from shapely.geometry import GeometryCollection, LineString, Polygon, box

from wetlands import clean, qa

from .conftest import square


# --- CRS ---------------------------------------------------------------------
def test_crs_passes_for_expected(good_gdf):
    assert qa.check_crs(good_gdf, 5070).passed


def test_crs_fails_for_wrong_crs(good_gdf):
    assert not qa.check_crs(good_gdf.to_crs(4326), 5070).passed


def test_crs_fails_when_missing(good_gdf):
    assert not qa.check_crs(good_gdf.set_crs(None, allow_override=True), 5070).passed


# --- Fields ------------------------------------------------------------------
def test_required_fields_missing(good_gdf):
    r = qa.check_required_fields(good_gdf.drop(columns="WETLAND_TYPE"), ["ATTRIBUTE", "WETLAND_TYPE"])
    assert not r.passed and r.details["missing"] == ["WETLAND_TYPE"]


def test_required_fields_null(good_gdf):
    good_gdf.loc[0, "ATTRIBUTE"] = None
    r = qa.check_required_fields(good_gdf, ["ATTRIBUTE"])
    assert not r.passed and r.details["null_counts"] == {"ATTRIBUTE": 1}


def test_wetland_types_unexpected_value(good_gdf, cfg):
    good_gdf.loc[1, "WETLAND_TYPE"] = "Swamp"
    r = qa.check_wetland_types(good_gdf, cfg["fields"]["wetland_types"])
    assert not r.passed and r.details["unexpected"] == {"Swamp": 1}


def test_wetland_types_pass(good_gdf, cfg):
    assert qa.check_wetland_types(good_gdf, cfg["fields"]["wetland_types"]).passed


def test_attribute_codes(good_gdf):
    assert qa.check_attribute_codes(good_gdf, "^[MERLP]").passed
    good_gdf.loc[0, "ATTRIBUTE"] = "XYZ"
    r = qa.check_attribute_codes(good_gdf, "^[MERLP]")
    assert not r.passed and r.details["invalid_examples"] == ["XYZ"]


# --- Geometry ----------------------------------------------------------------
BOWTIE = Polygon([(0, 0), (100, 100), (100, 0), (0, 100), (0, 0)])  # self-intersecting


def test_invalid_geometry_fails_without_repair(good_gdf):
    good_gdf.loc[0, "geometry"] = BOWTIE
    assert not qa.check_geometries(good_gdf).passed


def test_repair_fixes_and_counts(good_gdf):
    good_gdf.loc[0, "geometry"] = BOWTIE
    fixed, n = clean.repair_geometries(good_gdf)
    assert n == 1
    r = qa.check_geometries(fixed, n)
    assert r.passed and r.details["repaired"] == 1
    assert good_gdf.geometry[0].equals(BOWTIE), "input must not be mutated"


def test_polygonal_part_drops_lines():
    gc = GeometryCollection([square(0, 0), LineString([(0, 0), (5, 5)])])
    assert clean._polygonal_part(gc).geom_type == "MultiPolygon"


def test_empty_geometry_fails(good_gdf):
    good_gdf.loc[0, "geometry"] = Polygon()
    r = qa.check_geometries(good_gdf)
    assert not r.passed and r.details["empty"] == 1


# --- Duplicates --------------------------------------------------------------
def test_exact_duplicates_dropped(good_gdf):
    doubled = gpd.GeoDataFrame(pd.concat([good_gdf, good_gdf.iloc[[0]]]), crs=good_gdf.crs)
    out, n = clean.drop_exact_duplicates(doubled)
    assert n == 1 and len(out) == 3
    assert qa.check_duplicates(out, "NWI_ID").passed


def test_duplicate_id_fails(good_gdf):
    good_gdf.loc[1, "NWI_ID"] = "a"
    r = qa.check_duplicates(good_gdf, "NWI_ID")
    assert not r.passed and r.details["duplicate_ids"] == 1


def test_duplicate_geometry_with_different_attrs_fails(good_gdf):
    good_gdf.loc[1, "geometry"] = good_gdf.geometry[0]
    _, n = clean.drop_exact_duplicates(good_gdf)
    assert n == 0  # not an exact dup, so not silently removed...
    assert not qa.check_duplicates(good_gdf, "NWI_ID").passed  # ...and the check catches it


# --- ACRES -------------------------------------------------------------------
def test_acres_match(good_gdf, state):
    r = qa.check_acres(good_gdf, 0.01, 0.01, state, 50)
    assert r.passed and r.details["mismatches_total"] == 0


def test_acres_non_positive_fails(good_gdf, state):
    good_gdf.loc[0, "ACRES"] = 0
    assert not qa.check_acres(good_gdf, 0.01, 0.01, state, 50).passed


def test_acres_interior_mismatch_fails(good_gdf, state):
    good_gdf.loc[1, "ACRES"] = 3.0  # geometry is 2 acres
    r = qa.check_acres(good_gdf, 0.01, 0.01, state, 50)
    assert not r.passed and r.details["mismatches_interior"] == 1


def test_acres_within_tolerance_passes(good_gdf, state):
    good_gdf.loc[1, "ACRES"] = 2.0 * 1.009  # 0.9% off
    assert qa.check_acres(good_gdf, 0.01, 0.01, state, 50).passed


def test_acres_boundary_mismatch_allowed(good_gdf, state):
    # Feature touching the state edge, published ACRES larger than clipped geometry
    good_gdf.loc[2, "geometry"] = square(9_990, 5_000, 0.5).intersection(state)
    r = qa.check_acres(good_gdf, 0.01, 0.01, state, 50)
    assert r.passed
    assert r.details["mismatches_on_extent_edge"] == 1


def test_acres_requires_projected_crs(good_gdf):
    import pytest

    with pytest.raises(ValueError):
        qa.acres_from_geometry(good_gdf.to_crs(4326))


# --- State boundary ------------------------------------------------------------
def test_clip_drops_outside_and_cuts_straddling(good_gdf, state):
    good_gdf.loc[0, "geometry"] = box(20_000, 20_000, 20_100, 20_100)  # entirely outside
    good_gdf.loc[2, "geometry"] = box(9_900, 5_000, 10_100, 5_100)     # half outside
    out, dropped, clipped, slivers = clean.clip_to_boundary(good_gdf, state)
    assert (dropped, clipped, slivers) == (1, 1, 0)
    assert list(out["NWI_ID"]) == ["b", "c"]
    assert out.geometry[2].area == 100 * 100  # only the inside half remains
    assert qa.check_within_boundary(out, state, 1).passed


def test_clip_drops_features_only_touching_the_line(good_gdf, state):
    good_gdf.loc[0, "geometry"] = box(10_000, 0, 10_100, 100)  # shares an edge only
    out, dropped, _, _ = clean.clip_to_boundary(good_gdf, state)
    assert dropped == 1 and "a" not in set(out["NWI_ID"])


def test_clip_drops_slivers_but_keeps_small_source_features(good_gdf, state):
    good_gdf.loc[0, "geometry"] = box(9_999.5, 100, 10_100, 101)  # clip leaves 0.5 m2
    good_gdf.loc[1, "geometry"] = box(500, 500, 500.5, 501)       # 0.5 m2 in the source
    out, dropped, clipped, slivers = clean.clip_to_boundary(good_gdf, state, min_clipped_area=1)
    assert (dropped, clipped, slivers) == (0, 0, 1)
    assert set(out["NWI_ID"]) == {"b", "c"}


def test_within_boundary_fails_for_outside_feature(good_gdf, state):
    good_gdf.loc[0, "geometry"] = box(20_000, 20_000, 20_100, 20_100)
    r = qa.check_within_boundary(good_gdf, state, 1)
    assert not r.passed and r.details["examples"] == ["a"]
