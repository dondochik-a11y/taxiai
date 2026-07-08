"""seed remaining Moscow districts

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-08 16:20:00.000000

packages/shared/constants/moscow_districts.json grew from 20 seed rows to the
full set of 125 official Moscow districts (plus the station/airport hubs that
were already there). Migration 0002 already ran on existing databases, so this
re-reads the same JSON and inserts only the districts that aren't in the table
yet (matched by name). Same placeholder-square polygons as 0002.
"""
import json
import os
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# Same file-resolution logic as 0002: docker mounts the constants dir at
# SHARED_CONSTANTS_DIR; the host venv reaches it relative to the repo root.
_env_dir = os.environ.get("SHARED_CONSTANTS_DIR")
if _env_dir:
    _SEED_FILE = Path(_env_dir) / "moscow_districts.json"
else:
    _SEED_FILE = (
        Path(__file__).resolve().parents[4] / "packages" / "shared" / "constants" / "moscow_districts.json"
    )

# Half-width of the placeholder square, in degrees (~1.5km at Moscow's latitude).
_HALF_SIDE_DEG = 0.0075

_INSERT_SQL = sa.text(
    """
    INSERT INTO districts (
        name, name_en, okrug, geom, centroid, centroid_lat, centroid_lng,
        airport_nearby, metro_stations_count
    )
    VALUES (
        :name, :name_en, :okrug,
        ST_Multi(ST_MakeEnvelope(:min_lng, :min_lat, :max_lng, :max_lat, 4326)),
        ST_SetSRID(ST_MakePoint(:lng, :lat), 4326),
        :lat, :lng, :airport_nearby, :metro_stations_count
    )
    """
)


def upgrade() -> None:
    data = json.loads(_SEED_FILE.read_text(encoding="utf-8"))
    bind = op.get_bind()
    existing = {row[0] for row in bind.execute(sa.text("SELECT name FROM districts"))}
    for d in data["districts"]:
        if d["name"] in existing:
            continue
        lat, lng = d["centroid_lat"], d["centroid_lng"]
        bind.execute(
            _INSERT_SQL,
            {
                "name": d["name"],
                "name_en": d["name_en"],
                "okrug": d["okrug"],
                "lat": lat,
                "lng": lng,
                "min_lat": lat - _HALF_SIDE_DEG,
                "max_lat": lat + _HALF_SIDE_DEG,
                "min_lng": lng - _HALF_SIDE_DEG,
                "max_lng": lng + _HALF_SIDE_DEG,
                "airport_nearby": d["airport_nearby"],
                "metro_stations_count": d["metro_stations_count"],
            },
        )


def downgrade() -> None:
    # The original 20 seed names from migration 0002 are kept; everything else
    # added by this migration is removed.
    original = [
        "Тверской", "Арбат", "Замоскворечье", "Пресненский", "Хамовники",
        "Белорусская", "Павелецкая", "Курская", "Сокольники", "Люблино",
        "Печатники", "Марьино", "Царицыно", "Раменки", "Дорогомилово",
        "Митино", "Ховрино", "Шереметьевская", "Внуково", "Домодедово",
    ]
    op.get_bind().execute(
        sa.text("DELETE FROM districts WHERE name != ALL(:names)"),
        {"names": original},
    )
