import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class KefReading(BaseModel):
    """A single surge-coefficient bubble read off a radar screenshot. The radar
    shows a range (min–max across tariffs); a single-value read leaves kef_max
    unset and it mirrors kef_min."""

    kef_min: float = Field(gt=0, le=20)
    kef_max: float | None = Field(default=None, gt=0, le=20)
    tariff_class: str | None = None

    # Geo is best-effort. Give district_id if already resolved, else an area_hint
    # (an OCR'd map label like "Марфино") and the server tries to resolve it.
    district_id: int | None = None
    area_hint: str | None = None
    lat: float | None = None
    lng: float | None = None


class KefIngestIn(BaseModel):
    observed_at: datetime | None = None  # screenshot clock; defaults to now (UTC)
    user_id: uuid.UUID | None = None
    raw_text: str | None = None
    readings: list[KefReading] = Field(default_factory=list)


class KefIngestOut(BaseModel):
    stored: int
    resolved_districts: int  # of the stored rows, how many pinned to a district


class KefOcrIn(BaseModel):
    image_b64: str  # base64-encoded screenshot bytes
    mime: str = "image/jpeg"
    user_id: uuid.UUID | None = None


class KefOcrOut(BaseModel):
    """OCR-ingest result, richer so the bot can echo what it read back."""

    stored: int
    resolved_districts: int
    observed_at: datetime
    readings: list[KefReading]
