import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    start_time: datetime
    end_time: datetime
    start_district_id: int
    end_district_id: int
    distance_km: float
    duration_seconds: int
    time_to_pickup_seconds: int
    wait_time_seconds: int
    price: float
    tariff: str
    surge_multiplier_at_start: float | None


class TripCreate(BaseModel):
    start_time: datetime
    end_time: datetime
    start_district_id: int
    end_district_id: int
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    time_to_pickup_seconds: int
    wait_time_seconds: int
    distance_km: float
    duration_seconds: int
    price: float
    tariff: str = "economy"
    surge_multiplier_at_start: float | None = None


class AiTripAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary_text: str
    estimated_missed_earnings: float | None
    suggested_action: str | None
    model_used: str
