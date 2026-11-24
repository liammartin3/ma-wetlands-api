import math

import geopandas as gpd
import pytest
from shapely.geometry import box

from wetlands.qa import SQ_METERS_PER_ACRE

EPSG = 5070
ACRE_SIDE = math.sqrt(SQ_METERS_PER_ACRE)  # side of a 1-acre square, metres


def square(x: float, y: float, acres: float = 1.0):
    s = ACRE_SIDE * math.sqrt(acres)
    return box(x, y, x + s, y + s)


@pytest.fixture
def good_gdf() -> gpd.GeoDataFrame:
    """Three well-formed wetlands well inside a 10 km 'state'."""
    return gpd.GeoDataFrame(
        {
            "NWI_ID": ["a", "b", "c"],
            "ATTRIBUTE": ["PEM1E", "L1UBH", "R2UBH"],
            "WETLAND_TYPE": ["Freshwater Emergent Wetland", "Lake", "Riverine"],
            "ACRES": [1.0, 2.0, 0.5],
            "QAQC_CODE": [None, None, None],
        },
        geometry=[square(1000, 1000, 1.0), square(3000, 3000, 2.0), square(5000, 5000, 0.5)],
        crs=EPSG,
    )


@pytest.fixture
def state():
    return box(0, 0, 10_000, 10_000)


@pytest.fixture
def cfg(tmp_path):
    return {
        "source": {"url": "test://", "wetlands_layer": "MA_Wetlands", "boundary_layer": "Massachusetts"},
        "crs": {"expected_source_epsg": EPSG, "output_epsg": 4326},
        "fields": {
            "required": ["ATTRIBUTE", "WETLAND_TYPE", "ACRES", "NWI_ID"],
            "id_field": "NWI_ID",
            "attribute_pattern": "^[MERLP]",
            "wetland_types": [
                "Estuarine and Marine Deepwater", "Estuarine and Marine Wetland",
                "Freshwater Emergent Wetland", "Freshwater Forested/Shrub Wetland",
                "Freshwater Pond", "Lake", "Other", "Riverine",
            ],
        },
        "acres": {"relative_tolerance": 0.01, "absolute_tolerance": 0.01, "boundary_buffer_m": 50},
        "output": {
            "path": str(tmp_path / "out" / "wetlands.gpkg"),
            "layer": "wetlands",
            "report_dir": str(tmp_path / "reports"),
        },
    }
