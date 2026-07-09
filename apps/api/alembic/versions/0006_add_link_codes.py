"""add link codes

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-09 08:40:00.000000

Adds link_codes — short-lived one-time codes that connect a Telegram account
and a web account to the same user row (see app/services/link_service.py).
Created from ORM metadata like migrations 0003/0005.
"""
from alembic import op

from app.db.base import Base

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["link_codes"].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["link_codes"].drop(bind=bind, checkfirst=True)
