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
    # A demand-level PROXY (0–1), NOT a calibrated order probability. Clients
    # must present it as «уровень спроса», never «вероятность заказа».
    probability: float
    expected_avg_check: float
    # Expected income uplift of moving vs staying, in percent. Populated only for
    # a "move" (the gain that cleared the move threshold); None for a "stay",
    # where staying is the baseline and there's no honest uplift to advertise.
    expected_uplift_pct: float | None = None
    # When the recommendation stops being reliable: the target_time of the
    # forecast it's built on (generated_at + horizon_minutes). None if there was
    # no forecast to base it on.
    valid_until: datetime | None = None
    rationale_text: str | None


class RecommendationRequest(BaseModel):
    lat: float
    lng: float
    horizon_minutes: int = 30
