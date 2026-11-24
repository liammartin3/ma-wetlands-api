"""Cleaning steps. Each returns (new_gdf, count_of_changes) so the report can
say exactly what was fixed."""
from __future__ import annotations

import geopandas as gpd
import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry


def _polygonal_part(geom: BaseGeometry) -> BaseGeometry:
    """make_valid can return a GeometryCollection (e.g. polygon + stray line);
    keep only the polygon parts so the layer stays MultiPolygon."""
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    polys: list[Polygon] = []
    for part in getattr(geom, "geoms", []):
        if isinstance(part, Polygon):
            polys.append(part)
        elif isinstance(part, MultiPolygon):
            polys.extend(part.geoms)
    return MultiPolygon(polys) if polys else Polygon()


def repair_geometries(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, int]:
    invalid = ~gdf.geometry.is_valid & gdf.geometry.notna()
    n = int(invalid.sum())
    if n == 0:
        return gdf, 0
    out = gdf.copy()
    fixed = shapely.make_valid(out.geometry[invalid].values)
    out.loc[invalid, out.geometry.name] = [_polygonal_part(g) for g in fixed]
    return out, n


def drop_exact_duplicates(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, int]:
    """Drop rows identical in every attribute AND geometry. These are safe to
    remove. Partial duplicates (same ID or same geometry, different attributes)
    are left in place for check_duplicates to fail on, since picking a winner
    would be a guess."""
    key = gdf.drop(columns=gdf.geometry.name).assign(_wkb=gdf.geometry.to_wkb())
    dup = key.duplicated()
    return gdf.loc[~dup].copy(), int(dup.sum())


def to_multipolygon(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Promote Polygons to MultiPolygons so the GeoPackage has a single type."""
    out = gdf.copy()
    is_poly = out.geometry.geom_type == "Polygon"
    out.loc[is_poly, out.geometry.name] = [MultiPolygon([g]) for g in out.geometry[is_poly]]
    return out
