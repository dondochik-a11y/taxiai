"""Geocoding via PostGIS point-in-polygon. This is real logic (not a network
call), so it stays the same in live mode too — only routing (get_route) would
ever need a real Yandex Maps key.
"""
from geoalchemy2.functions import ST_Contains, ST_MakePoint, ST_SetSRID
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.district import District


class MockMapsProvider:
    def __init__(self, db: Session) -> None:
        self.db = db

    def geocode(self, lat: float, lng: float) -> int | None:
        point = ST_SetSRID(ST_MakePoint(lng, lat), 4326)
        stmt = select(District.id).where(ST_Contains(District.geom, point)).limit(1)
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is not None:
            return result
        # Fallback: nearest centroid, in case the point falls outside every
        # placeholder polygon (they're small squares, not real boundaries).
        districts = self.db.execute(select(District)).scalars().all()
        if not districts:
            return None
        nearest = min(
            districts,
            key=lambda d: (float(d.centroid_lat) - lat) ** 2 + (float(d.centroid_lng) - lng) ** 2,
        )
        return nearest.id
