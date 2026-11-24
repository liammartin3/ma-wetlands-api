"""API test setup.

Tests run against a live server (docker compose up -d). Set API_URL to point
elsewhere and DATA_FILE to the GeoPackage that server is serving; the tests
compare API answers with GeoPandas queries on that same file.

If the server is down the tests are skipped, unless REQUIRE_API=1 (CI), in
which case they fail.
"""
import os
from pathlib import Path

import geopandas as gpd
import pytest
import requests

API_URL = os.environ.get("API_URL", "http://localhost:5050").rstrip("/")
DATA_FILE = Path(os.environ.get("DATA_FILE", "data/build/ma_wetlands.gpkg"))


@pytest.fixture(scope="session")
def api() -> str:
    try:
        requests.get(f"{API_URL}/conformance", params={"f": "json"}, timeout=5).raise_for_status()
    except requests.RequestException as e:
        msg = f"API not reachable at {API_URL} ({e}). Start it with: docker compose up -d"
        if os.environ.get("REQUIRE_API") == "1":
            pytest.fail(msg)
        pytest.skip(msg)
    return API_URL


@pytest.fixture(scope="session")
def truth() -> gpd.GeoDataFrame:
    """The served data, read directly, as ground truth."""
    if not DATA_FILE.exists():
        msg = f"{DATA_FILE} not found (set DATA_FILE)"
        if os.environ.get("REQUIRE_API") == "1":
            pytest.fail(msg)  # in CI a skip would look like a pass
        pytest.skip(msg)
    return gpd.read_file(DATA_FILE, layer="wetlands")


def get_json(url: str, **params) -> dict:
    params.setdefault("f", "json")
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()
