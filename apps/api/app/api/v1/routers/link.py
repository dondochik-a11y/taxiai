from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.link import LinkCodeCreate, LinkCodeOut, RedeemTelegram, RedeemWeb
from app.schemas.user import UserOut
from app.services import link_service

router = APIRouter(prefix="/link", tags=["link"])


@router.post("/code", response_model=LinkCodeOut, status_code=201)
def create_code(payload: LinkCodeCreate, db: Session = Depends(get_db)) -> LinkCodeOut:
    """Generate a short one-time code for an existing account. The other side
    (bot or web) redeems it to link to the same user."""
    row = link_service.generate_code(db, payload.user_id)
    return LinkCodeOut(code=row.code, expires_at=row.expires_at)


@router.post("/redeem-telegram", response_model=UserOut)
def redeem_telegram(payload: RedeemTelegram, db: Session = Depends(get_db)) -> User:
    """Bot side: attach this telegram_id to the web account that made the code."""
    return link_service.redeem_for_telegram(db, payload.code, payload.telegram_id)


@router.post("/redeem-web", response_model=UserOut)
def redeem_web(payload: RedeemWeb, db: Session = Depends(get_db)) -> User:
    """Web side: adopt the bot account that made the code (returns its user)."""
    return link_service.redeem_for_web(db, payload.code)
