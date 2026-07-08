import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.providers.base import LLMProvider
from app.providers.factory import get_llm_provider
from app.schemas.chat import ChatMessageIn, ChatMessageOut, ChatReplyOut
from app.services.chat_service import get_history, send_message

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/{user_id}", response_model=ChatReplyOut)
def post_message(
    user_id: uuid.UUID,
    payload: ChatMessageIn,
    db: Session = Depends(get_db),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> ChatReplyOut:
    reply = send_message(db, user_id, payload.message, llm_provider)
    return ChatReplyOut(reply=reply)


@router.get("/{user_id}/history", response_model=list[ChatMessageOut])
def get_chat_history(user_id: uuid.UUID, db: Session = Depends(get_db)):
    return get_history(db, user_id)
