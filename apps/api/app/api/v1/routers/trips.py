import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ai_analysis import AiTripAnalysis
from app.models.district import District
from app.models.enums import DataSource
from app.models.trip import Trip
from app.models.user import DriverProfile
from app.providers.base import LLMProvider
from app.providers.factory import get_llm_provider
from app.schemas.trip import AiTripAnalysisOut, TripCreate, TripOut
from app.services.ai_analysis_service import analyze_trip
from app.services.manual_entry import normalize_manual_trip

router = APIRouter(prefix="/trips", tags=["trips"])


def _default_district_id(db: Session, user_id: uuid.UUID) -> int | None:
    """District to attach to a quick-logged trip that didn't specify one:
    the driver's home district, else the lowest-id seeded district. Keeps the
    trip's AI post-mortem (which needs a district) working."""
    profile = db.execute(
        select(DriverProfile).where(DriverProfile.user_id == user_id)
    ).scalar_one_or_none()
    if profile and profile.home_district_id:
        return profile.home_district_id
    return db.execute(select(District.id).order_by(District.id)).scalars().first()


@router.get("", response_model=list[TripOut])
def list_trips(user_id: uuid.UUID, limit: int = 50, db: Session = Depends(get_db)) -> list[Trip]:
    stmt = (
        select(Trip).where(Trip.user_id == user_id).order_by(Trip.start_time.desc()).limit(limit)
    )
    return db.execute(stmt).scalars().all()


@router.post("", response_model=TripOut, status_code=201)
def create_trip(
    user_id: uuid.UUID,
    payload: TripCreate,
    db: Session = Depends(get_db),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> Trip:
    """Real trip ingestion, used by the bot's /trip quick-log and the web trip
    form (and any future driver app): persists the trip and immediately
    generates its AI post-mortem. A minimal payload (price + distance_km) is
    filled out server-side by normalize_manual_trip."""
    try:
        fields = normalize_manual_trip(
            payload.model_dump(),
            now=datetime.now(timezone.utc),
            default_district_id=_default_district_id(db, user_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    trip = Trip(user_id=user_id, source=DataSource.MANUAL, **fields)
    db.add(trip)
    db.commit()
    db.refresh(trip)

    analyze_trip(db, trip, llm_provider)
    return trip


@router.get("/{trip_id}/analysis", response_model=AiTripAnalysisOut)
def get_trip_analysis(trip_id: uuid.UUID, db: Session = Depends(get_db)) -> AiTripAnalysis:
    analysis = db.execute(
        select(AiTripAnalysis).where(AiTripAnalysis.trip_id == trip_id)
    ).scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail="No AI analysis for this trip yet")
    return analysis
