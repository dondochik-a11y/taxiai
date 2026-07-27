"""Geocoding honesty checks for the real district boundaries (migration 0009).

Two layers:
  * Data-contract tests (always run, DB-free): a known real coordinate falls
    inside exactly the expected district polygon in the shipped GeoJSON, and the
    file covers our 125 official districts with valid geometry.
  * Integration test (skipped unless a PostGIS DB is reachable): the same
    coordinate resolves to the expected district through the *actual*
    MockMapsProvider point-in-polygon path (ST_Contains). Runs under `make test`,
    which executes pytest inside the api container against the migrated DB.
"""
import json
from pathlib import Path

import pytest
from shapely.geometry import Point, shape

_GEOJSON = Path(__file__).resolve().parents[1] / "app" / "data" / "moscow_districts.geojson"

# (label, lat, lng, expected district) — well-known Moscow landmarks, each of
# which falls inside exactly one real district (verified against the source).
KNOWN_POINTS = [
    ("Красная площадь", 55.7539, 37.6208, "Тверской"),
    ("Лужники", 55.7158, 37.5535, "Хамовники"),
    ("ВДНХ", 55.8300, 37.6330, "Останкинский"),
    ("Сокольники", 55.7940, 37.6770, "Сокольники"),
    ("МГУ", 55.7033, 37.5308, "Раменки"),
]


@pytest.fixture(scope="module")
def polygons():
    data = json.loads(_GEOJSON.read_text(encoding="utf-8"))
    return [(f["properties"]["name"], shape(f["geometry"])) for f in data["features"]]


def test_geojson_covers_all_official_districts(polygons):
    assert len(polygons) == 125


def test_all_polygons_valid(polygons):
    invalid = [name for name, geom in polygons if not geom.is_valid]
    assert not invalid, f"invalid geometries: {invalid}"


@pytest.mark.parametrize("label,lat,lng,expected", KNOWN_POINTS)
def test_known_point_falls_in_expected_district(polygons, label, lat, lng, expected):
    p = Point(lng, lat)
    hits = [name for name, geom in polygons if geom.contains(p)]
    assert hits == [expected], f"{label}: expected [{expected}], got {hits}"


# --- Integration: exercise the real ST_Contains geocoding path if a DB exists ---

def _db_session_or_skip():
    try:
        from sqlalchemy import text

        from app.db.session import SessionLocal

        db = SessionLocal()
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any connect/driver error means "no DB"
        pytest.skip(f"no PostGIS DB reachable: {exc}")
    return db


@pytest.mark.parametrize("label,lat,lng,expected", KNOWN_POINTS)
def test_geocode_via_point_in_polygon(label, lat, lng, expected):
    from app.models.district import District
    from app.providers.mock.maps_mock import MockMapsProvider

    db = _db_session_or_skip()
    try:
        district_id = MockMapsProvider(db).geocode(lat, lng)
        assert district_id is not None
        name = db.get(District, district_id).name
        assert name == expected, f"{label}: expected {expected}, got {name}"
    finally:
        db.close()
