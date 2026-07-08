import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import FuelType, TariffPlan


class DriverProfileIn(BaseModel):
    car_make: str | None = None
    car_model: str | None = None
    car_year: int | None = None
    tariff_plan: TariffPlan = TariffPlan.ECONOMY
    fuel_type: FuelType = FuelType.PETROL_95
    fuel_consumption_l_per_100km: float = 8.0
    fuel_price_per_liter: float = 60.0
    rental_cost_per_day: float | None = None
    rental_cost_per_week: float | None = None
    work_schedule: dict = {}
    home_district_id: int | None = None


class UserCreate(BaseModel):
    city: str = "Moscow"
    email: str | None = None
    phone: str | None = None
    telegram_id: int | None = None
    driver_profile: DriverProfileIn


class DriverProfileUpdate(BaseModel):
    """All fields optional — only the ones actually provided get updated.
    Distinct from DriverProfileIn (used at creation), which fills in defaults
    for anything omitted; a partial update must never silently reset a field
    the caller didn't mean to touch."""

    car_make: str | None = None
    car_model: str | None = None
    car_year: int | None = None
    tariff_plan: TariffPlan | None = None
    fuel_type: FuelType | None = None
    fuel_consumption_l_per_100km: float | None = None
    fuel_price_per_liter: float | None = None
    rental_cost_per_day: float | None = None
    rental_cost_per_week: float | None = None
    work_schedule: dict | None = None
    home_district_id: int | None = None


class UserUpdate(BaseModel):
    city: str | None = None
    driver_profile: DriverProfileUpdate | None = None


class DriverProfileOut(DriverProfileIn):
    model_config = ConfigDict(from_attributes=True)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    city: str
    email: str | None
    phone: str | None
    telegram_id: int | None
    driver_profile: DriverProfileOut | None = None
