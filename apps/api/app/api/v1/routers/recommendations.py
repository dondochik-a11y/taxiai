import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.providers.base import MapsProvider
from app.providers.factory import get_maps_provider
from app.schemas.forecast import RecommendationOut, RecommendationRequest
from app.services.recommendation_service import generate_recommendation

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("/{user_id}", response_model=RecommendationOut)
def create_recommendation(
    user_id: uuid.UUID,
    payload: RecommendationRequest,
    db: Session = Depends(get_db),
    maps_provider: MapsProvider = Depends(get_maps_provider),
):
    try:
        return generate_recommendation(
            db, user_id, payload.lat, payload.lng, maps_provider, payload.horizon_minutes
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
