import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ForecastOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    district_id: int
    generated_at: datetime
    horizon_minutes: int
    target_time: datetime
    predicted_demand_level: float
    predicted_surge: float
    predicted_avg_check: float
    predicted_wait_time_seconds: int
    model_version: str


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    current_district_id: int
    recommended_district_id: int
    recommended_horizon_minutes: int
    action: str
    probability: float
    expected_avg_check: float
    rationale_text: str | None


class RecommendationRequest(BaseModel):
    lat: float
    lng: float
    horizon_minutes: int = 30
