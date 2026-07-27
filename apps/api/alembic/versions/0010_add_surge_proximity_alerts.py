"""add surge proximity alerts

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-27 14:10:00.000000

Backs the proactive «рядом скачок спроса» push (office task #99, Phase 2):
  * two opt-in settings on driver_profiles (surge_alert_enabled +
    surge_alert_threshold), set from the bot's /alert command;
  * proximity_surge_alert_log, the per-(driver, district) cooldown table that
    throttles the push (distinct from the once/day telegram_notification_log).

No notification_type enum change: the proximity alert tags its pending payload
with a plain string and dedups in its own table, so the Postgres enum is left
untouched (and this migration downgrades cleanly).
"""
import sqlalchemy as sa
from alembic import op

from app.db.base import Base

# revision identifiers, used by Alembic.
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column(
        "driver_profiles",
        sa.Column(
            "surge_alert_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "driver_profiles",
        sa.Column(
            "surge_alert_threshold",
            sa.Numeric(3, 1),
            nullable=False,
            server_default="1.5",
        ),
    )
    Base.metadata.tables["proximity_surge_alert_log"].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["proximity_surge_alert_log"].drop(bind=bind, checkfirst=True)
    op.drop_column("driver_profiles", "surge_alert_threshold")
    op.drop_column("driver_profiles", "surge_alert_enabled")
