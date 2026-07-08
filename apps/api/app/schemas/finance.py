from datetime import date

from pydantic import BaseModel, ConfigDict


class FinanceSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary_date: date
    gross_income: float
    net_income: float
    fuel_cost: float
    rental_cost: float
    wash_cost: float
    fines_cost: float
    tax_estimate: float
    depreciation_estimate: float
    trips_count: int
    online_hours: float
    income_per_hour: float
    income_per_km: float
