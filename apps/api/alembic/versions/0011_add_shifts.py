"""add shifts

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-27 16:00:00.000000

Backs the /shift start/stop toggle (office task #100, Phase 2): the shifts table
records real work-shift boundaries (started_at, ended_at nullable). finance_service
uses these for honest online-hours (₽/hour), falling back to the first→last trip
span when a day has no shift. Downgrades cleanly.
"""
from alembic import op

from app.db.base import Base

# revision identifiers, used by Alembic.
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["shifts"].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["shifts"].drop(bind=bind, checkfirst=True)
