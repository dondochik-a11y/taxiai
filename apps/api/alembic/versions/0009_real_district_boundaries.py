"""real Moscow district boundaries

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-27 11:00:00.000000

Replaces the placeholder ~1.5km square polygons (seeded by 0002/0004) with real
administrative boundaries for the 125 official Moscow districts (районы). This
makes the map choropleth, point-in-polygon geocoding and reposition-distance
honest.

Source data lives in the repo at app/data/moscow_districts.geojson (one Feature
per district row, already re-keyed to our `name` — see that file's `_comment`).
It is read from disk at migrate time, NOT fetched over the network, so this is
safe to run offline on the VPS. The 5 non-district demand hubs (rail stations
Белорусская/Павелецкая/Курская, airports Шереметьевская/Домодедово) have no
administrative boundary and deliberately keep their placeholder squares.

Idempotent: it UPDATEs geom for districts matched by name, so re-running sets the
same geometry. Missing rows/features are skipped, never inserted or deleted.
"""
import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# The GeoJSON ships inside the api package (apps/api/app/data), which is copied
# into the Docker image (Dockerfile `COPY . .`) and bind-mounted on the VPS, so
# this relative path resolves in every environment without SHARED_CONSTANTS_DIR.
# parents: [0]=versions [1]=alembic [2]=apps/api.
_GEOJSON_FILE = Path(__file__).resolve().parents[2] / "app" / "data" / "moscow_districts.geojson"

# Half-width of the placeholder square, in degrees (~1.5km at Moscow's latitude).
# Must match 0002/0004 so downgrade restores the exact prior placeholder state.
_HALF_SIDE_DEG = 0.0075

_UPDATE_REAL_SQL = sa.text(
    """
    UPDATE districts
    SET geom = ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326))
    WHERE name = :name
    """
)

_RESTORE_SQUARE_SQL = sa.text(
    """
    UPDATE districts
    SET geom = ST_Multi(
        ST_MakeEnvelope(
            centroid_lng - :half, centroid_lat - :half,
            centroid_lng + :half, centroid_lat + :half, 4326
        )
    )
    WHERE name = :name
    """
)


def _load_features() -> list[dict]:
    data = json.loads(_GEOJSON_FILE.read_text(encoding="utf-8"))
    return data["features"]


def upgrade() -> None:
    bind = op.get_bind()
    for feat in _load_features():
        bind.execute(
            _UPDATE_REAL_SQL,
            {
                "name": feat["properties"]["name"],
                "geojson": json.dumps(feat["geometry"]),
            },
        )


def downgrade() -> None:
    # Restore the ~1.5km placeholder square around each district's stored centroid
    # for exactly the districts this migration touched. centroid_lat/lng are never
    # modified here, so this returns geom to its pre-0009 state.
    bind = op.get_bind()
    for feat in _load_features():
        bind.execute(
            _RESTORE_SQUARE_SQL,
            {"name": feat["properties"]["name"], "half": _HALF_SIDE_DEG},
        )
