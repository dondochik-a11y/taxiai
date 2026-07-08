from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatMessageIn(BaseModel):
    message: str


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    created_at: datetime


class ChatReplyOut(BaseModel):
    reply: str
