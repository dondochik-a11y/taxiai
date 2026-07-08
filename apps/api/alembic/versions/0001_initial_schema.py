"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-08 08:47:18.491004

This bootstrap migration creates the PostGIS extension and every table directly
from the SQLAlchemy ORM metadata (app.db.base.Base.metadata), which is the
single source of truth for the schema defined in app/models/. Using
metadata.create_all here (rather than hand-transcribing ~17 op.create_table
calls) avoids drift between the models and this migration for the initial
bootstrap. Subsequent migrations should be generated incrementally via
`alembic revision --autogenerate` against a running database and should use
explicit op.* calls as usual.
"""
from alembic import op

from app.db.base import Base

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
