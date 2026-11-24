# Data quality report

**Status: PASSED**  
Built: 2026-11-24T16:35:34+00:00  
Source: https://documentst.ecosphere.fws.gov/wetlands/data/State-Downloads/MA_geopackage_wetlands.zip  
Input file: `data/raw/MA_geopackage_wetlands.gpkg` (layer `MA_Wetlands`)  
Input file SHA-256: `059a0884047262e4c900b93517b04e97013dc403b42216481b8f84d8c557b2d7`

## Counts

| Stage | Features |
|---|---:|
| Read from source | 301,032 |
| Exact duplicates dropped | 0 |
| Geometries repaired | 0 |
| Dropped: entirely outside Massachusetts | 37,115 |
| Clipped at the Massachusetts state line | 839 |
| Dropped: clip left < 1 m² sliver | 32 |
| Written to GeoPackage | 263,885 |

## Checks

| Check | Result | Summary |
|---|---|---|
| crs | pass | CRS equivalent to EPSG:5070 |
| required_fields | pass | all 4 required fields present and non-null |
| attribute_codes | pass | 0 ATTRIBUTE codes do not match '^[MERLP]' |
| wetland_types | pass | all WETLAND_TYPE values in expected set |
| geometry_validity | pass | all geometries valid polygons (0 repaired) |
| duplicates | pass | no duplicate IDs or geometries |
| acres | pass | 910 ACRES mismatches, all on the edge of the NWI download extent |
| within_state | pass | all features inside the state boundary |
| geometry_validity_after_clip | pass | all geometries valid polygons (0 repaired) |

## Features by wetland type

| Wetland type | Features |
|---|---:|
| Freshwater Forested/Shrub Wetland | 146,154 |
| Riverine | 71,967 |
| Freshwater Emergent Wetland | 43,860 |
| Freshwater Pond | 25,411 |
| Estuarine and Marine Wetland | 8,738 |
| Lake | 2,362 |
| Estuarine and Marine Deepwater | 1,353 |
| Other | 1,187 |

## ACRES vs. geometry area

Tolerance: 1% or 0.01 acres, whichever is larger.

- Mismatches: 910 (910 on the edge of the NWI download extent, 0 elsewhere)

Checked on the source geometry, before clipping. The NWI Massachusetts download
covers Massachusetts plus a border strip of neighboring states; NWI clips polygons
at the edge of that area but keeps the unclipped ACRES, so mismatches there are
expected. The output keeps the published `ACRES`; `ACRES_GEOM` is the area of the
geometry as served (after clipping to the Massachusetts state line).

## State boundary

Features are clipped to STUSPS=MA from the U.S. Census Bureau
TIGER/Line state boundaries (includes state waters): https://www2.census.gov/geo/tiger/TIGER2025/STATE/tl_2025_us_state.zip

## Output

- File: `data/build/ma_wetlands.gpkg` (layer `wetlands`, EPSG:4326)
- Spatial index (R-tree) present: True
- Attribute indexes: idx_wetlands_attribute, idx_wetlands_nwi_id, idx_wetlands_wetland_type
- Size: 438,018,048 bytes

## Environment

- python: 3.12.14
- geopandas: 1.2.0
- shapely: 2.2.0
- pyogrio: 0.13.0
- gdal: 3.12.4
- pyproj: 3.8.0
