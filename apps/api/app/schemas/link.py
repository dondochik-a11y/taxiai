import uuid
from datetime import datetime

from pydantic import BaseModel


class LinkCodeCreate(BaseModel):
    user_id: uuid.UUID


class LinkCodeOut(BaseModel):
    code: str
    expires_at: datetime


class RedeemTelegram(BaseModel):
    code: str
    telegram_id: int


class RedeemWeb(BaseModel):
    code: str
