from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.district import District
from app.models.traffic import TrafficObservation


class MockTrafficProvider:
    """Reads the synthetic traffic history the generator populates — no
    network call, mock mode is fully self-consistent with the rest of the
    synthetic data."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_current(self, lat: float, lng: float) -> dict:
        districts = self.db.execute(select(District)).scalars().all()
        if not districts:
            return {"congestion_level": 0.0, "avg_speed_kmh": None}
        nearest = min(
            districts, key=lambda d: (float(d.centroid_lat) - lat) ** 2 + (float(d.centroid_lng) - lng) ** 2
        )
        row = (
            self.db.execute(
                select(TrafficObservation)
                .where(TrafficObservation.district_id == nearest.id)
                .order_by(TrafficObservation.observed_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if row is None:
            return {"congestion_level": 0.0, "avg_speed_kmh": None}
        return {
            "congestion_level": float(row.congestion_level),
            "avg_speed_kmh": float(row.avg_speed_kmh) if row.avg_speed_kmh is not None else None,
        }
