from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class District(Base):
    """Moscow district/hub reference table. Rarely changes; seeded once from
    packages/shared/constants/moscow_districts.json."""

    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    name_en: Mapped[str | None] = mapped_column(String(128), nullable=True)
    okrug: Mapped[str | None] = mapped_column(String(64), nullable=True)

    geom = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True), nullable=True
    )
    centroid = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=True
    )

    # Denormalized for cheap JSON responses without geometry parsing.
    centroid_lat: Mapped[float] = mapped_column(Numeric(9, 6))
    centroid_lng: Mapped[float] = mapped_column(Numeric(9, 6))

    airport_nearby: Mapped[bool] = mapped_column(Boolean, default=False)
    metro_stations_count: Mapped[int | None] = mapped_column(nullable=True)
