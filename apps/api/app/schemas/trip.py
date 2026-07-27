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
    """Real-trip ingestion. Only price + distance_km are required, so the bot's
    /trip quick-log and the web trip form can post a minimal payload; the server
    fills the rest (times, districts, coordinates) with sane defaults via
    services.manual_entry.normalize_manual_trip. A full driver-app ingestion can
    still send every field."""

    price: float
    distance_km: float
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_seconds: int | None = None
    start_district_id: int | None = None
    end_district_id: int | None = None
    start_lat: float | None = None
    start_lng: float | None = None
    end_lat: float | None = None
    end_lng: float | None = None
    time_to_pickup_seconds: int = 0
    wait_time_seconds: int = 0
    tariff: str = "economy"
    surge_multiplier_at_start: float | None = None


class AiTripAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary_text: str
    estimated_missed_earnings: float | None
    suggested_action: str | None
    model_used: str
