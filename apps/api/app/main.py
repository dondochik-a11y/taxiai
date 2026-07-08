from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.base import Base  # noqa: F401  (must import before any single app.models.* submodule)
from app.api.v1.routers import chat, districts, finance, forecasts, recommendations, surge, telegram, trips, users
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="TaxiAI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix="/v1")
app.include_router(districts.router, prefix="/v1")
app.include_router(trips.router, prefix="/v1")
app.include_router(finance.router, prefix="/v1")
app.include_router(forecasts.router, prefix="/v1")
app.include_router(recommendations.router, prefix="/v1")
app.include_router(chat.router, prefix="/v1")
app.include_router(telegram.router, prefix="/v1")
app.include_router(surge.router, prefix="/v1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.environment}
