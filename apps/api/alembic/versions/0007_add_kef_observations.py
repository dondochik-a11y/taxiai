"""add kef observations

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-09 08:00:00.000000

Adds kef_observations — raw surge-coefficient readings lifted from driver
kef-radar screenshots (OCR'd via the bot). District is best-effort (a
screenshot has no map bounds), so the clean demand_snapshots table is fed
later by an ETL step, not directly. Created from ORM metadata like migration
0005, since 0001's full-schema bootstrap already ran against existing DBs.
"""
from alembic import op

from app.db.base import Base

# revision identifiers, used by Alembic.
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["kef_observations"].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["kef_observations"].drop(bind=bind, checkfirst=True)
    op.execute("DROP TYPE IF EXISTS kef_source")
