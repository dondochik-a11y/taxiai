from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Importing app.db.base here (rather than relying on every caller to do it
# first) guarantees the full model registry loads in the one safe order
# (Base defined, then every app.models.* submodule imported by base.py) before
# any other module does `from app.models.X import Y` directly — which would
# otherwise race a partially-initialized module and raise ImportError. Nearly
# everything imports app.db.session (for `engine`/`get_db`), so fixing it here
# once is more robust than guarding every entry point individually.
from app.db.base import Base  # noqa: E402,F401
from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
