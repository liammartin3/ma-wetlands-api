"""Data quality checks.

Each check is a pure function that takes a GeoDataFrame (plus config values)
and returns a CheckResult. Checks never mutate their input; fixes live in
clean.py so that "what was wrong" and "what we changed" stay separate in the
report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import geopandas as gpd
import pyproj
from shapely.geometry.base import BaseGeometry

SQ_METERS_PER_ACRE = 4046.8564224  # exact, international acre


@dataclass
class CheckResult:
    name: str
    passed: bool
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


class QAFailure(Exception):
    """Raised when one or more checks fail."""

    def __init__(self, results: list[CheckResult]):
        self.results = results
        failed = [r for r in results if not r.passed]
        msg = "; ".join(f"{r.name}: {r.summary}" for r in failed)
        super().__init__(f"{len(failed)} data quality check(s) failed: {msg}")


def check_crs(gdf: gpd.GeoDataFrame, expected_epsg: int) -> CheckResult:
    expected = pyproj.CRS.from_epsg(expected_epsg)
    if gdf.crs is None:
        return CheckResult("crs", False, "no CRS defined", {"expected": f"EPSG:{expected_epsg}"})
    ok = gdf.crs.equals(expected, ignore_axis_order=True)
    return CheckResult(
        "crs",
        ok,
        f"CRS equivalent to EPSG:{expected_epsg}" if ok else f"CRS is not EPSG:{expected_epsg}",
        {"expected": f"EPSG:{expected_epsg}", "found": gdf.crs.name},
    )


def check_required_fields(gdf: gpd.GeoDataFrame, required: list[str]) -> CheckResult:
    missing = [f for f in required if f not in gdf.columns]
    nulls = {f: int(gdf[f].isna().sum()) for f in required if f in gdf.columns}
    nulls = {f: n for f, n in nulls.items() if n}
    ok = not missing and not nulls
    if ok:
        summary = f"all {len(required)} required fields present and non-null"
    else:
        summary = f"missing fields {missing}, null counts {nulls}"
    return CheckResult("required_fields", ok, summary, {"missing": missing, "null_counts": nulls})


def check_attribute_codes(gdf: gpd.GeoDataFrame, pattern: str) -> CheckResult:
    rx = re.compile(pattern)
    codes = gdf["ATTRIBUTE"].astype("string").fillna("")
    bad = codes[~codes.map(lambda c: bool(rx.match(c)))]
    return CheckResult(
        "attribute_codes",
        bad.empty,
        f"{len(bad)} ATTRIBUTE codes do not match {pattern!r}",
        {
            "pattern": pattern,
            "distinct_codes": int(codes.nunique()),
            "invalid_count": len(bad),
            "invalid_examples": sorted(bad.unique().tolist())[:20],
        },
    )


def check_wetland_types(gdf: gpd.GeoDataFrame, allowed: list[str]) -> CheckResult:
    counts = gdf["WETLAND_TYPE"].value_counts(dropna=False)
    unexpected = {str(k): int(v) for k, v in counts.items() if k not in set(allowed)}
    return CheckResult(
        "wetland_types",
        not unexpected,
        "all WETLAND_TYPE values in expected set"
        if not unexpected
        else f"{sum(unexpected.values())} features have unexpected WETLAND_TYPE values",
        {
            "counts": {str(k): int(v) for k, v in counts.items()},
            "unexpected": unexpected,
        },
    )


def check_geometries(gdf: gpd.GeoDataFrame, repaired_count: int = 0) -> CheckResult:
    geoms = gdf.geometry
    null = int(geoms.isna().sum())
    empty = int(geoms.is_empty.sum())
    invalid = int((~geoms.is_valid).sum())
    non_polygon = int((~geoms.geom_type.isin(["Polygon", "MultiPolygon"])).sum())
    ok = null == empty == invalid == non_polygon == 0
    return CheckResult(
        "geometry_validity",
        ok,
        f"all geometries valid polygons ({repaired_count} repaired)"
        if ok
        else f"null={null} empty={empty} invalid={invalid} non_polygon={non_polygon}",
        {
            "repaired": repaired_count,
            "null": null,
            "empty": empty,
            "invalid": invalid,
            "non_polygon": non_polygon,
        },
    )


def check_duplicates(gdf: gpd.GeoDataFrame, id_field: str) -> CheckResult:
    dup_ids = int(gdf[id_field].duplicated().sum())
    dup_geoms = int(gdf.geometry.to_wkb().duplicated().sum())
    ok = dup_ids == 0 and dup_geoms == 0
    return CheckResult(
        "duplicates",
        ok,
        "no duplicate IDs or geometries"
        if ok
        else f"{dup_ids} duplicate {id_field} values, {dup_geoms} duplicate geometries",
        {"duplicate_ids": dup_ids, "duplicate_geometries": dup_geoms},
    )


def acres_from_geometry(gdf: gpd.GeoDataFrame) -> gpd.pd.Series:
    """Area in acres. Caller must supply an equal-area projected CRS."""
    if gdf.crs is None or not gdf.crs.is_projected:
        raise ValueError("acres_from_geometry needs a projected (equal-area) CRS")
    return gdf.geometry.area / SQ_METERS_PER_ACRE


def check_acres(
    gdf: gpd.GeoDataFrame,
    rel_tol: float,
    abs_tol: float,
    extent: BaseGeometry | None = None,
    extent_buffer_m: float = 0.0,
) -> CheckResult:
    """ACRES must be positive and match geometry area within tolerance.

    Run on the source geometry, before clipping to the state. Mismatches are
    tolerated only for features on the edge of NWI's download extent: NWI clips
    polygons to that extent (Massachusetts plus a border buffer) but keeps the
    unclipped ACRES value.
    """
    acres = gdf["ACRES"]
    non_positive = int((acres <= 0).sum())

    calc = acres_from_geometry(gdf)
    diff = (calc - acres).abs()
    matches = (diff <= abs_tol) | (diff <= rel_tol * acres.abs())
    mismatch = ~matches

    if extent is not None:
        on_edge = ~gdf.geometry.within(extent.buffer(-extent_buffer_m))
    else:
        on_edge = gpd.pd.Series(False, index=gdf.index)

    edge_mismatch = mismatch & on_edge
    interior_mismatch = mismatch & ~on_edge
    examples = (
        gdf.loc[interior_mismatch, ["NWI_ID", "ACRES"]]
        .assign(acres_geom=calc[interior_mismatch].round(4))
        .head(20)
        .to_dict("records")
    )
    ok = non_positive == 0 and int(interior_mismatch.sum()) == 0
    return CheckResult(
        "acres",
        ok,
        f"{int(mismatch.sum())} ACRES mismatches, all on the edge of the NWI download extent"
        if ok
        else f"{non_positive} non-positive ACRES, {int(interior_mismatch.sum())} mismatches away from the extent edge",
        {
            "relative_tolerance": rel_tol,
            "absolute_tolerance": abs_tol,
            "non_positive": non_positive,
            "mismatches_total": int(mismatch.sum()),
            "mismatches_on_extent_edge": int(edge_mismatch.sum()),
            "mismatches_interior": int(interior_mismatch.sum()),
            "interior_mismatch_examples": examples,
        },
    )


def check_within_boundary(gdf: gpd.GeoDataFrame, boundary: BaseGeometry, tolerance_m: float) -> CheckResult:
    """Every feature must lie inside the state boundary (an independent,
    authoritative boundary, not the source's own extent layer). A small
    tolerance absorbs floating-point noise along clipped edges."""
    outside = ~gdf.geometry.within(boundary.buffer(tolerance_m))
    n = int(outside.sum())
    return CheckResult(
        "within_state",
        n == 0,
        "all features inside the state boundary" if n == 0 else f"{n} features extend outside the state boundary",
        {"outside": n, "tolerance_m": tolerance_m, "examples": gdf.loc[outside, "NWI_ID"].head(20).tolist()},
    )
