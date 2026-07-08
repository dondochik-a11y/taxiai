import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import FuelType, TariffPlan, pg_enum


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(64), default="Moscow")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    driver_profile: Mapped["DriverProfile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class DriverProfile(Base):
    __tablename__ = "driver_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    car_make: Mapped[str | None] = mapped_column(String(64), nullable=True)
    car_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    car_year: Mapped[int | None] = mapped_column(nullable=True)

    tariff_plan: Mapped[TariffPlan] = mapped_column(
        pg_enum(TariffPlan, "tariff_plan"), default=TariffPlan.ECONOMY
    )
    fuel_type: Mapped[FuelType] = mapped_column(pg_enum(FuelType, "fuel_type"), default=FuelType.PETROL_95)
    fuel_consumption_l_per_100km: Mapped[float] = mapped_column(Numeric(5, 2), default=8.0)
    fuel_price_per_liter: Mapped[float] = mapped_column(Numeric(6, 2), default=60.0)

    rental_cost_per_day: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    rental_cost_per_week: Mapped[float | None] = mapped_column(Numeric(9, 2), nullable=True)

    # e.g. {"mon": ["09:00-21:00"], "tue": [], ...}
    work_schedule: Mapped[dict] = mapped_column(JSONB, default=dict)

    home_district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="RESTRICT"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="driver_profile")
