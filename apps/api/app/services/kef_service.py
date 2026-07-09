"""Ingest surge-coefficient readings lifted from driver kef-radar screenshots.

Writes raw rows into kef_observations. Geo is best-effort: if a reading carries
no district_id but an area_hint (an OCR'd map label), we try a case-insensitive
match against district names — anything unmatched is stored district-less rather
than guessed, so downstream ETL can decide what to trust.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.district import District
from app.models.enums import DataSource
from app.models.kef_observation import KefObservation
from app.schemas.kef import KefIngestIn


def _resolve_district_id(db: Session, area_hint: str | None) -> int | None:
    if not area_hint:
        return None
    name = area_hint.strip()
    if not name:
        return None
    row = (
        db.query(District.id)
        .filter(func.lower(District.name) == name.lower())
        .first()
    )
    return row[0] if row else None


def ingest(db: Session, payload: KefIngestIn) -> tuple[int, int]:
    """Store every reading. Returns (stored, resolved_districts)."""
    observed_at = payload.observed_at or datetime.now(timezone.utc)
    stored = 0
    resolved = 0

    for r in payload.readings:
        district_id = r.district_id or _resolve_district_id(db, r.area_hint)
        if district_id is not None:
            resolved += 1
        db.add(
            KefObservation(
                observed_at=observed_at,
                kef_min=r.kef_min,
                kef_max=r.kef_max if r.kef_max is not None else r.kef_min,
                tariff_class=r.tariff_class,
                district_id=district_id,
                area_hint=r.area_hint,
                lat=r.lat,
                lng=r.lng,
                user_id=payload.user_id,
                raw_text=payload.raw_text,
                source=DataSource.RADAR,
            )
        )
        stored += 1

    db.commit()
    return stored, resolved
