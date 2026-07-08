"""add telegram notification log

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-08 09:18:56.955667

Adds telegram_notification_log, used by the bot's polling loop to dedup
morning-plan/pre-shift-alert/post-shift-summary notifications. Creates just
this one table from ORM metadata (unlike migration 0001's full-schema
bootstrap) since 0001/0002 have already run against any existing database.
"""
from alembic import op

from app.db.base import Base

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["telegram_notification_log"].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["telegram_notification_log"].drop(bind=bind, checkfirst=True)
