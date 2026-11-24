"""OGC API - Features behaviour of the running service."""
from urllib.parse import quote

import requests
from shapely.geometry import box, shape

from .conftest import get_json

COLL = "wetlands"
# Small bbox inside the CI fixture area (Concord), so tests work on the
# fixture and on the full statewide data.
BBOX = (-71.36, 42.44, -71.34, 42.46)
MA_LON = (-74.0, -69.0)
MA_LAT = (41.0, 43.2)

CONF_CORE = "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core"
CONF_GEOJSON = "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson"


def page_all(api: str, **params) -> list[dict]:
    """Follow offset paging until a short page; returns all features."""
    feats, offset, limit = [], 0, 100
    while True:
        fc = get_json(f"{api}/collections/{COLL}/items", limit=limit, offset=offset, **params)
        feats += fc["features"]
        if len(fc["features"]) < limit:
            return feats
        offset += limit


# --- Discovery -----------------------------------------------------------------
def test_landing_page_links(api):
    rels = {link["rel"] for link in get_json(f"{api}/")["links"]}
    assert {"service-desc", "conformance", "data"} <= rels


def test_openapi_document(api):
    doc = get_json(f"{api}/openapi")
    assert doc["openapi"].startswith("3.")
    assert f"/collections/{COLL}/items" in doc["paths"]


def test_conformance(api):
    classes = get_json(f"{api}/conformance")["conformsTo"]
    assert CONF_CORE in classes and CONF_GEOJSON in classes


def test_collection_listed(api):
    ids = [c["id"] for c in get_json(f"{api}/collections")["collections"]]
    assert COLL in ids


def test_queryables_include_wetland_type(api):
    props = get_json(f"{api}/collections/{COLL}/queryables")["properties"]
    assert {"WETLAND_TYPE", "ATTRIBUTE", "ACRES"} <= set(props)


# --- Items -----------------------------------------------------------------------
def test_items_are_valid_geojson(api):
    fc = get_json(f"{api}/collections/{COLL}/items", limit=20)
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 20
    for f in fc["features"]:
        assert f["type"] == "Feature" and f["id"]
        geom = shape(f["geometry"])
        assert geom.geom_type in ("Polygon", "MultiPolygon") and geom.is_valid
        # CRS84 axis order: lon, lat (catches swapped axes)
        minx, miny, maxx, maxy = geom.bounds
        assert MA_LON[0] < minx <= maxx < MA_LON[1]
        assert MA_LAT[0] < miny <= maxy < MA_LAT[1]
        assert {"WETLAND_TYPE", "ATTRIBUTE", "ACRES", "ACRES_GEOM"} <= set(f["properties"])


def test_default_and_max_page_size(api):
    assert len(get_json(f"{api}/collections/{COLL}/items")["features"]) == 10
    assert len(get_json(f"{api}/collections/{COLL}/items", limit=100_000)["features"]) <= 500


def test_number_matched_equals_total(api, truth):
    fc = get_json(f"{api}/collections/{COLL}/items", limit=1)
    assert fc["numberMatched"] == len(truth)


def test_get_single_item(api, truth):
    fid = truth["NWI_ID"].iloc[0]
    f = get_json(f"{api}/collections/{COLL}/items/{quote(fid, safe='')}")
    assert f["id"] == fid and f["properties"]["WETLAND_TYPE"] == truth["WETLAND_TYPE"].iloc[0]


def test_unknown_item_is_404(api):
    r = requests.get(f"{api}/collections/{COLL}/items/does-not-exist", params={"f": "json"}, timeout=30)
    assert r.status_code == 404


# --- Queries -----------------------------------------------------------------------
def test_bbox_query_matches_ground_truth(api, truth):
    expected = set(truth.loc[truth.intersects(box(*BBOX)), "NWI_ID"])
    assert expected, "test bbox should contain features"
    got = page_all(api, bbox=",".join(map(str, BBOX)))
    ids = [f["id"] for f in got]
    assert len(ids) == len(set(ids)), "paging returned duplicates"
    assert set(ids) == expected


def test_attribute_filter(api, truth):
    expected = int((truth["WETLAND_TYPE"] == "Lake").sum())
    fc = get_json(f"{api}/collections/{COLL}/items", WETLAND_TYPE="Lake", limit=100)
    assert fc["numberMatched"] == expected
    assert fc["features"] and all(f["properties"]["WETLAND_TYPE"] == "Lake" for f in fc["features"])


def test_bbox_and_attribute_filter(api, truth):
    sel = truth.intersects(box(*BBOX)) & (truth["WETLAND_TYPE"] == "Freshwater Emergent Wetland")
    got = page_all(api, bbox=",".join(map(str, BBOX)), WETLAND_TYPE="Freshwater Emergent Wetland")
    assert {f["id"] for f in got} == set(truth.loc[sel, "NWI_ID"])


def test_invalid_bbox_is_400(api):
    r = requests.get(f"{api}/collections/{COLL}/items", params={"bbox": "1,2,3", "f": "json"}, timeout=30)
    assert r.status_code == 400
