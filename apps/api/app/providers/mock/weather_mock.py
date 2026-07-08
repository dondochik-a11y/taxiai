from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.weather import WeatherObservation


class MockWeatherProvider:
    """Reads the synthetic weather history the generator populates — no network
    call, mock mode is fully self-consistent with the rest of the synthetic data."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_current(self, district_id: int | None = None) -> dict:
        stmt = select(WeatherObservation).order_by(WeatherObservation.observed_at.desc()).limit(1)
        row = self.db.execute(stmt).scalars().first()
        if row is None:
            return {
                "observed_at": None,
                "temperature_c": None,
                "precipitation_type": "none",
                "precipitation_mm": 0,
                "wind_speed_ms": 0,
                "condition_text": "unknown",
            }
        return {
            "observed_at": row.observed_at,
            "temperature_c": float(row.temperature_c),
            "precipitation_type": row.precipitation_type,
            "precipitation_mm": float(row.precipitation_mm),
            "wind_speed_ms": float(row.wind_speed_ms),
            "condition_text": row.condition_text,
        }
