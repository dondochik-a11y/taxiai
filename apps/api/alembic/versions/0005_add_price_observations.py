"""add price observations

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-08 19:05:00.000000

Adds price_observations — real ride-price quotes per district (Yandex Taxi
widget API), from which the live surge coefficient is derived at read time
(price / rolling baseline, see app/services/surge_service.py). Created from
ORM metadata like migration 0003, since 0001's full-schema bootstrap has
already run against existing databases.
"""
from alembic import op

from app.db.base import Base

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["price_observations"].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["price_observations"].drop(bind=bind, checkfirst=True)
    op.execute("DROP TYPE IF EXISTS price_source")
