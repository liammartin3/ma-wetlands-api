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


def clip_to_boundary(
    gdf: gpd.GeoDataFrame, boundary: BaseGeometry, min_clipped_area: float = 0.0
) -> tuple[gpd.GeoDataFrame, int, int, int]:
    """Keep only the part of each feature inside the boundary.

    Returns (clipped_gdf, dropped, clipped, slivers): `dropped` features had no
    area inside the boundary; `clipped` features were cut at the boundary line;
    `slivers` were cut down to less than `min_clipped_area` (CRS units squared)
    and removed, since the wetland itself lies on the other side of the line.
    Features that are small in the source data are never removed here.
    """
    inside = gdf.geometry.within(boundary)
    touching = gdf.geometry.intersects(boundary)
    edge = touching & ~inside

    cut = shapely.intersection(gdf.geometry[edge].values, boundary)
    cut = [_polygonal_part(g) for g in cut]  # drop stray lines/points from the cut

    out = gdf.loc[touching].copy()
    out.loc[edge, out.geometry.name] = cut
    area = out.geometry.area
    empty = out.geometry.is_empty | (area == 0)
    sliver = edge.loc[out.index] & ~empty & (area < min_clipped_area)
    out = out.loc[~empty & ~sliver].copy()

    dropped = len(gdf) - len(out) - int(sliver.sum())
    slivers = int(sliver.sum())
    clipped = int(edge.sum()) - int((edge.loc[empty.index] & empty).sum()) - slivers
    return out, dropped, clipped, slivers
