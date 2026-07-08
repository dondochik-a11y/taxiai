import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ExpenseCategory, pg_enum


class FinanceSummary(Base):
    __tablename__ = "finance_summaries"
    __table_args__ = (UniqueConstraint("user_id", "summary_date", name="uq_finance_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    summary_date: Mapped[date] = mapped_column(Date)

    gross_income: Mapped[float] = mapped_column(Numeric(9, 2), default=0)
    net_income: Mapped[float] = mapped_column(Numeric(9, 2), default=0)
    fuel_cost: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    rental_cost: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    wash_cost: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    fines_cost: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    tax_estimate: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    depreciation_estimate: Mapped[float] = mapped_column(Numeric(8, 2), default=0)

    trips_count: Mapped[int] = mapped_column(Integer, default=0)
    online_hours: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    income_per_hour: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    income_per_km: Mapped[float] = mapped_column(Numeric(8, 2), default=0)


class Expense(Base):
    """Manually-logged costs (washes, fines, other) with no automatic data source."""

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    expense_date: Mapped[date] = mapped_column(Date)
    category: Mapped[ExpenseCategory] = mapped_column(pg_enum(ExpenseCategory, "expense_category"))
    amount: Mapped[float] = mapped_column(Numeric(8, 2))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
