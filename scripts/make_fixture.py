"""Clip the built GeoPackage to a small area for CI API tests.

    python scripts/make_fixture.py

Reads data/build/ma_wetlands.gpkg (output of wetlands.build, so already
validated) and writes tests/fixtures/ma_wetlands_sample.gpkg with the same
layer name, schema and spatial index.
"""
from pathlib import Path

import pyogrio

SRC = Path("data/build/ma_wetlands.gpkg")
DST = Path("tests/fixtures/ma_wetlands_sample.gpkg")
LAYER = "wetlands"
BBOX = (-71.40, 42.42, -71.30, 42.50)  # Concord area: mix of wetland types


def main() -> None:
    gdf = pyogrio.read_dataframe(SRC, layer=LAYER, bbox=BBOX)
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.unlink(missing_ok=True)
    pyogrio.write_dataframe(gdf, DST, layer=LAYER, driver="GPKG", layer_options={"SPATIAL_INDEX": "YES"})
    print(f"{len(gdf)} features -> {DST} ({DST.stat().st_size:,} bytes)")
    print(gdf["WETLAND_TYPE"].value_counts().to_string())


if __name__ == "__main__":
    main()
