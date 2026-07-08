from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.user import DriverProfileIn, UserOut
from app.services.notification_service import get_pending_notifications

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get("/pending-notifications")
def pending_notifications(db: Session = Depends(get_db)) -> list[dict]:
    """Polled by the bot every 1-2 minutes; all decisioning happens server-side
    (see app/services/notification_service.py), the bot just renders + sends."""
    return get_pending_notifications(db)


@router.post("/link", response_model=UserOut, status_code=201)
def link_telegram_user(telegram_id: int, db: Session = Depends(get_db)) -> User:
    """Bot-first onboarding: /start creates a minimal account with default
    driver_profile values (city/tariff/fuel defaults) if this telegram_id
    isn't already linked. Fine-tuning those defaults is a web app task,
    deferred past this MVP pass."""
    from app.models.user import DriverProfile

    existing = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
    if existing:
        return existing

    user = User(telegram_id=telegram_id, city="Moscow")
    db.add(user)
    db.flush()
    db.add(DriverProfile(user_id=user.id, **DriverProfileIn().model_dump()))
    db.commit()
    db.refresh(user)
    return user
