"""add model metrics

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-27 09:00:00.000000

Adds model_metrics — one row per demand-model retrain holding the holdout
evaluation (overall + per-horizon MAE) that train_demand_model.py previously
only printed. Persisting it gives a queryable forecast-quality history and a
trained_at the staleness watchdog can check to catch a retrain that silently
stopped happening. Created from ORM metadata like migrations 0005/0007, since
0001's full-schema bootstrap already ran against existing DBs.
"""
from alembic import op

from app.db.base import Base

# revision identifiers, used by Alembic.
revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["model_metrics"].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["model_metrics"].drop(bind=bind, checkfirst=True)
