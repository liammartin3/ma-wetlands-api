# Data quality report

**Status: PASSED**  
Built: 2026-11-23T21:41:29+00:00  
Source: https://documentst.ecosphere.fws.gov/wetlands/data/State-Downloads/MA_geopackage_wetlands.zip  
Input file: `data/raw/MA_geopackage_wetlands.gpkg` (layer `MA_Wetlands`)  
Input file SHA-256: `059a0884047262e4c900b93517b04e97013dc403b42216481b8f84d8c557b2d7`

## Counts

| Stage | Features |
|---|---:|
| Read from source | 301,032 |
| Exact duplicates dropped | 0 |
| Geometries repaired | 0 |
| Written to GeoPackage | 301,032 |

## Checks

| Check | Result | Summary |
|---|---|---|
| crs | pass | CRS equivalent to EPSG:5070 |
| required_fields | pass | all 4 required fields present and non-null |
| attribute_codes | pass | 0 ATTRIBUTE codes do not match '^[MERLP]' |
| wetland_types | pass | all WETLAND_TYPE values in expected set |
| geometry_validity | pass | all geometries valid polygons (0 repaired) |
| duplicates | pass | no duplicate IDs or geometries |
| acres | pass | 910 ACRES mismatches, all on the state boundary |

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

- Mismatches: 910 (910 on the state boundary, 0 interior)
- Sum of stored ACRES: 4,386,788.0
- Sum of geometry area (acres, EPSG:5070): 2,544,198.7

Boundary mismatches are expected: NWI clips polygons to the state line but keeps the
unclipped ACRES. The output keeps the published `ACRES` and adds `ACRES_GEOM`.

## Output

- File: `data/build/ma_wetlands.gpkg` (layer `wetlands`, EPSG:4326)
- Spatial index (R-tree) present: True
- Attribute indexes: idx_wetlands_attribute, idx_wetlands_nwi_id, idx_wetlands_wetland_type
- Size: 502,816,768 bytes

## Environment

- python: 3.12.14
- geopandas: 1.2.0
- shapely: 2.2.0
- pyogrio: 0.13.0
- gdal: 3.12.4
- pyproj: 3.8.0
