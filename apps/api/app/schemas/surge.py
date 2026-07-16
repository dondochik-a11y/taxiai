from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SurgeNowOut(BaseModel):
    district_id: int
    surge: float
    observed_at: datetime
    # "radar" — real kef read off the Радар-кэфа app; "radar_stale" — same but
    # 45–180 min old; "radar_near" — median of nearest radar-covered districts;
    # "live" — derived from real Yandex Taxi prices; "synthetic" — from the
    # generated demand feed. The UI must not present synthetic as real.
    source: Literal["radar", "radar_stale", "radar_near", "live", "synthetic"]
