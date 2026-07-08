from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.district import District
from app.schemas.district import DistrictOut

router = APIRouter(prefix="/districts", tags=["districts"])


@router.get("", response_model=list[DistrictOut])
def list_districts(db: Session = Depends(get_db)) -> list[District]:
    return db.execute(select(District).order_by(District.name)).scalars().all()
