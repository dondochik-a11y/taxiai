"""add car_purchase_price + finance other_cost for the real-data loop

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-27 15:00:00.000000

Office task #101 (Phase 3, real-data loop):

* driver_profiles.car_purchase_price — the price the driver paid for the car
  (rubles). Nullable: NULL means no price captured, so the daily summary keeps
  depreciation_estimate at 0 instead of guessing. Feeds a simple per-km
  depreciation estimate (finance_service.depreciation_per_km).
* finance_summaries.other_cost — sum of manually-logged "other" expenses for
  the day, so every logged expense (not just wash/fine) honestly reduces net
  income and shows up in the cost breakdown. NOT NULL, defaults to 0.

Both downgrade cleanly.
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "driver_profiles",
        sa.Column("car_purchase_price", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "finance_summaries",
        sa.Column(
            "other_cost", sa.Numeric(8, 2), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("finance_summaries", "other_cost")
    op.drop_column("driver_profiles", "car_purchase_price")
