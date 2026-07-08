from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.airport import AirportFlight


class MockFlightsProvider:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_upcoming_flights(self, airport_code: str, since: datetime) -> list[dict]:
        stmt = (
            select(AirportFlight)
            .where(AirportFlight.airport_code == airport_code, AirportFlight.scheduled_time >= since)
            .order_by(AirportFlight.scheduled_time)
            .limit(50)
        )
        rows = self.db.execute(stmt).scalars().all()
        return [
            {
                "scheduled_time": r.scheduled_time,
                "actual_time": r.actual_time,
                "direction": r.direction,
                "status": r.status,
                "delay_minutes": r.delay_minutes,
            }
            for r in rows
        ]
