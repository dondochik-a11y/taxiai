"""seed districts

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-08 08:50:57.854747

Seeds the districts reference table from packages/shared/constants/moscow_districts.json.
Polygons are small placeholder squares (~1.5km) around each real centroid — see the
"_comment" field in that file. Good enough for MVP point-in-polygon geocoding; replace
with real administrative boundary GeoJSON later without touching downstream code.
"""
import json
import os
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Local dev (host venv): apps/api/alembic/versions/... -> repo_root/packages/shared/constants,
# 4 parents up. Inside the api Docker image only apps/api is copied in (see apps/api/Dockerfile's
# build context), so that relative path doesn't exist there — docker-compose.yml instead mounts
# packages/shared/constants at SHARED_CONSTANTS_DIR and we prefer that when set.
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
    for d in data["districts"]:
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
    op.execute("DELETE FROM districts")
