import base64
import binascii
import json

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.kef import KefIngestIn, KefIngestOut, KefOcrIn, KefOcrOut
from app.services import kef_ocr, kef_service

router = APIRouter(prefix="/kef", tags=["kef"])


@router.post("/ingest", response_model=KefIngestOut, status_code=201)
def ingest_kef(payload: KefIngestIn, db: Session = Depends(get_db)) -> KefIngestOut:
    """Store surge-coefficient readings (already parsed). Rows land in
    kef_observations (raw); the surge radar reads the district-resolved ones
    directly as its top-priority source (surge_service._radar_surge)."""
    stored, resolved = kef_service.ingest(db, payload)
    return KefIngestOut(stored=stored, resolved_districts=resolved)


@router.post("/ocr-ingest", response_model=KefOcrOut, status_code=201)
def ocr_ingest_kef(payload: KefOcrIn, db: Session = Depends(get_db)) -> KefOcrOut:
    """Accept a base64 kef-radar screenshot, OCR the surge bubbles via the vision
    model, and store them. Returns what was read so the caller can echo it."""
    try:
        image_bytes = base64.b64decode(payload.image_b64)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Некорректный base64 изображения.")

    try:
        parsed = kef_ocr.read_screenshot(image_bytes, mime=payload.mime)
    except kef_ocr.OcrUnavailable:
        raise HTTPException(status_code=503, detail="OCR не настроен (нет ключа OpenAI).")
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        raise HTTPException(status_code=502, detail=f"Не удалось распознать скрин: {exc}")

    parsed.user_id = payload.user_id
    stored, resolved = kef_service.ingest(db, parsed)
    return KefOcrOut(
        stored=stored,
        resolved_districts=resolved,
        observed_at=parsed.observed_at,
        readings=parsed.readings,
    )
