from pydantic import BaseModel, ConfigDict


class DistrictOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    name_en: str | None
    okrug: str | None
    centroid_lat: float
    centroid_lng: float
    airport_nearby: bool
    metro_stations_count: int | None
