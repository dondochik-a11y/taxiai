from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.metro import MetroIncident


class MockMetroProvider:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_active_incidents(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        stmt = select(MetroIncident).where(
            MetroIncident.started_at <= now,
            or_(MetroIncident.resolved_at.is_(None), MetroIncident.resolved_at >= now),
        )
        rows = self.db.execute(stmt).scalars().all()
        return [
            {
                "line_name": r.line_name,
                "station_name": r.station_name,
                "incident_type": r.incident_type,
                "started_at": r.started_at,
                "resolved_at": r.resolved_at,
                "description": r.description,
            }
            for r in rows
        ]
