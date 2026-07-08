import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ai_analysis import AiTripAnalysis
from app.models.trip import Trip
from app.providers.base import LLMProvider
from app.providers.factory import get_llm_provider
from app.schemas.trip import AiTripAnalysisOut, TripCreate, TripOut
from app.services.ai_analysis_service import analyze_trip

router = APIRouter(prefix="/trips", tags=["trips"])


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
    """Real trip ingestion endpoint (for a future driver app, or manual testing):
    persists the trip and immediately generates its AI post-mortem."""
    trip = Trip(user_id=user_id, source="manual", **payload.model_dump())
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
