"""Read surge-coefficient bubbles off a kef-radar screenshot via an OpenAI
vision model. Stylised white-on-colour digits + Russian map labels are exactly
what a vision LLM handles well and Tesseract does not.

Vision genuinely needs a real model — a mock can't read an arbitrary image — so
this path uses the OpenAI key directly regardless of the chat LLM's mock/live
toggle. If no key is configured it raises OcrUnavailable, and the caller tells
the user to set one.
"""
from __future__ import annotations

import base64
import json
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings
from app.schemas.kef import KefIngestIn, KefReading

_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_MSK = ZoneInfo("Europe/Moscow")

_PROMPT = (
    "This is a screenshot from a Yandex-taxi 'kef radar' app for drivers. The map "
    "shows small round/teardrop markers ('bubbles'), each printed with one or two "
    "numbers — a surge coefficient, or a min and max coefficient (typically 1.0 to "
    "5.0, e.g. '1.18' over '1.56'). Extract EVERY such surge bubble.\n\n"
    "For each bubble return: kef_min (the smaller/only number), kef_max (the larger "
    "number, or equal to kef_min if only one is shown), and area_hint = the nearest "
    "district/neighbourhood NAME label printed on the map to that bubble, written in "
    "Russian with normal capitalisation (e.g. 'Марфино', not 'МАРФИНО'); use null if "
    "no name label is clearly near it.\n\n"
    "Also return 'clock' = the time in the phone status bar at the very top, as "
    "'HH:MM', or null.\n\n"
    "Ignore the promo/subscription banner, buttons, and the big range shown on the "
    "fixed side control. Respond ONLY with JSON: "
    '{"clock": "HH:MM"|null, "readings": [{"kef_min": number, "kef_max": number, '
    '"area_hint": string|null}]}.'
)


class OcrUnavailable(RuntimeError):
    """Raised when no OpenAI key is configured — vision OCR can't run mocked."""


def _observed_at(clock: str | None) -> datetime:
    """Combine the OCR'd status-bar clock with today's date (Moscow), since the
    screenshot carries a time but no date. Falls back to now."""
    now = datetime.now(_MSK)
    if not clock:
        return now
    try:
        hh, mm = (int(x) for x in clock.split(":")[:2])
        return datetime.combine(date.today(), time(hh, mm), tzinfo=_MSK)
    except (ValueError, TypeError):
        return now


def read_screenshot(image_bytes: bytes, mime: str = "image/jpeg") -> KefIngestIn:
    settings = get_settings()
    if not settings.openai_api_key:
        raise OcrUnavailable("OPENAI_API_KEY is not set")

    data_uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
    resp = httpx.post(
        _CHAT_URL,
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={
            "model": settings.openai_model,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _PROMPT},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]
    parsed = json.loads(raw)

    readings: list[KefReading] = []
    for r in parsed.get("readings", []):
        try:
            kmin = float(r["kef_min"])
        except (KeyError, TypeError, ValueError):
            continue
        kmax = r.get("kef_max")
        try:
            kmax = float(kmax) if kmax is not None else kmin
        except (TypeError, ValueError):
            kmax = kmin
        # Guard against the model hallucinating out-of-range values.
        if not (0 < kmin <= 20 and 0 < kmax <= 20):
            continue
        readings.append(
            KefReading(
                kef_min=kmin,
                kef_max=max(kmin, kmax),
                area_hint=(r.get("area_hint") or None),
            )
        )

    return KefIngestIn(
        observed_at=_observed_at(parsed.get("clock")),
        raw_text=raw,
        readings=readings,
    )
