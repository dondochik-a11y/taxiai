"""add daily_goal_income to driver_profiles

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-27 16:05:00.000000

Backs the earnings-goal feature (office task #100, Phase 2): a per-driver daily
net-income target set from the bot's /goal command. Nullable — NULL means no
goal, so the finance summary omits the "осталось N ₽ до цели" line. Downgrades
cleanly.
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "driver_profiles",
        sa.Column("daily_goal_income", sa.Numeric(9, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("driver_profiles", "daily_goal_income")
