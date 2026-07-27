"""End-to-end real-data-loop test (office task #101): create a driver, log a
manual trip + an expense over the API, and confirm the daily finance summary
reflects real gross/net — not synthetic numbers.

DB-backed: it talks to the configured Postgres (the docker `db` service under
`make test`, or a local container). Skipped automatically when no DB is
reachable so the pure-logic suite still runs on a bare checkout.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.main import app
from app.models.user import User

# The trip/expense/summary all pin to this single UTC day so the test never
# straddles a midnight boundary between "now" and the local date.
DAY = date(2026, 7, 20)
TRIP_START = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def client() -> TestClient:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - infra guard
        pytest.skip(f"database not reachable: {exc}")
    return TestClient(app)


@pytest.fixture()
def driver(client: TestClient):
    """A fresh driver with a known car price + fuel economy, plus a home
    district (so a district-less quick-log still resolves one). Torn down
    afterwards (cascade removes trips/expenses/summaries)."""
    districts = client.get("/v1/districts").json()
    assert districts, "districts must be seeded for this test"
    home_district_id = districts[0]["id"]

    resp = client.post(
        "/v1/users",
        json={
            "city": "Moscow",
            "driver_profile": {
                "car_purchase_price": 1_500_000,  # → 3.0 ₽/km depreciation
                "fuel_consumption_l_per_100km": 8.0,
                "fuel_price_per_liter": 60.0,
                "home_district_id": home_district_id,
            },
        },
    )
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["id"]
    yield user_id

    session = SessionLocal()
    try:
        obj = session.get(User, uuid.UUID(user_id))
        if obj is not None:
            session.delete(obj)
            session.commit()
    finally:
        session.close()


def _summary(client: TestClient, user_id: str) -> dict:
    resp = client.get(
        "/v1/finance/daily-summary",
        params={"user_id": user_id, "summary_date": DAY.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_manual_trip_and_expense_flow_into_daily_summary(client: TestClient, driver: str):
    user_id = driver

    # Before any entry: a real, empty day.
    before = _summary(client, user_id)
    assert before["trips_count"] == 0
    assert before["gross_income"] == 0

    # 1) Quick-log a real trip with the minimal payload (price + distance only).
    trip_resp = client.post(
        "/v1/trips",
        params={"user_id": user_id},
        json={"price": 1000, "distance_km": 10, "start_time": TRIP_START.isoformat()},
    )
    assert trip_resp.status_code == 201, trip_resp.text

    after_trip = _summary(client, user_id)
    assert after_trip["trips_count"] == 1
    assert after_trip["gross_income"] == 1000.0
    # Real fuel from distance: 10 km × 8 l/100km × 60 ₽/l = 48 ₽.
    assert after_trip["fuel_cost"] == pytest.approx(48.0)
    # Real depreciation: 3.0 ₽/km × 10 km = 30 ₽ (was hard-wired 0 before).
    assert after_trip["depreciation_estimate"] == pytest.approx(30.0)
    assert after_trip["tax_estimate"] == pytest.approx(40.0)  # 4% of 1000
    net_before_expense = after_trip["net_income"]
    assert net_before_expense < after_trip["gross_income"]  # costs really deducted

    # 2) Log an expense — it must reduce net income.
    exp_resp = client.post(
        "/v1/finance/expenses",
        params={"user_id": user_id},
        json={"category": "other", "amount": 200, "expense_date": DAY.isoformat()},
    )
    assert exp_resp.status_code == 201, exp_resp.text

    after_expense = _summary(client, user_id)
    assert after_expense["other_cost"] == pytest.approx(200.0)
    assert after_expense["net_income"] == pytest.approx(net_before_expense - 200.0)

    # Net reconciles with the whole cost breakdown (real, not synthetic).
    expected_net = (
        after_expense["gross_income"]
        - after_expense["fuel_cost"]
        - after_expense["rental_cost"]
        - after_expense["wash_cost"]
        - after_expense["fines_cost"]
        - after_expense["other_cost"]
        - after_expense["tax_estimate"]
        - after_expense["depreciation_estimate"]
    )
    assert after_expense["net_income"] == pytest.approx(expected_net)


def test_zero_price_trip_rejected(client: TestClient, driver: str):
    resp = client.post(
        "/v1/trips", params={"user_id": driver}, json={"price": 0, "distance_km": 5}
    )
    assert resp.status_code == 422


def test_negative_expense_rejected(client: TestClient, driver: str):
    resp = client.post(
        "/v1/finance/expenses",
        params={"user_id": driver},
        json={"category": "wash", "amount": -10},
    )
    assert resp.status_code == 422
