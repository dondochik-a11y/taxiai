import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import DriverProfile, User
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    """Onboarding endpoint: city/car/tariff/fuel/rental/schedule in one call."""
    user = User(city=payload.city, email=payload.email, phone=payload.phone, telegram_id=payload.telegram_id)
    db.add(user)
    db.flush()

    profile_data = payload.driver_profile.model_dump()
    profile = DriverProfile(user_id=user.id, **profile_data)
    db.add(profile)

    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db)) -> User:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, payload: UserUpdate, db: Session = Depends(get_db)) -> User:
    """Partial update — used by the bot's /profile flow (and any future web
    settings page) to fill in fields left blank at bot-first onboarding.
    Only fields actually present in the request body are touched."""
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "city" in update_data:
        user.city = update_data["city"]

    profile_data = update_data.get("driver_profile")
    if profile_data:
        profile = db.execute(
            select(DriverProfile).where(DriverProfile.user_id == user_id)
        ).scalar_one_or_none()
        if profile is None:
            profile = DriverProfile(user_id=user_id)
            db.add(profile)
        for key, value in profile_data.items():
            setattr(profile, key, value)

    db.commit()
    db.refresh(user)
    return user
