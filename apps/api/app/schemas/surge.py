from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SurgeNowOut(BaseModel):
    district_id: int
    surge: float
    observed_at: datetime
    # "radar" — real kef read off the Радар-кэфа app; "live" — derived from
    # real Yandex Taxi prices; "synthetic" — from the generated demand feed.
    # The UI must not present synthetic as real.
    source: Literal["radar", "live", "synthetic"]
