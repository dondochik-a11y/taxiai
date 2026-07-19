"""Thin HTTP wrapper over the FastAPI backend. The bot holds no business
logic of its own — every decision (what to say, when to notify) is made
server-side; this module only shapes HTTP calls.
"""
from __future__ import annotations

import httpx

from bot.config import settings


class ApiClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=settings.api_base_url, timeout=20.0)

    async def link_telegram_user(self, telegram_id: int) -> dict:
        resp = await self._client.post("/v1/telegram/link", params={"telegram_id": telegram_id})
        resp.raise_for_status()
        return resp.json()

    async def get_user_by_telegram_id(self, telegram_id: int) -> dict | None:
        linked = await self.link_telegram_user(telegram_id)
        return linked

    async def send_chat_message(self, user_id: str, message: str) -> str:
        resp = await self._client.post(f"/v1/chat/{user_id}", json={"message": message})
        resp.raise_for_status()
        return resp.json()["reply"]

    async def get_pending_notifications(self) -> list[dict]:
        resp = await self._client.get("/v1/telegram/pending-notifications")
        resp.raise_for_status()
        return resp.json()

    async def get_user(self, user_id: str) -> dict:
        resp = await self._client.get(f"/v1/users/{user_id}")
        resp.raise_for_status()
        return resp.json()

    async def update_profile(self, user_id: str, driver_profile: dict) -> dict:
        """Partial update — only keys present in driver_profile get changed."""
        resp = await self._client.patch(f"/v1/users/{user_id}", json={"driver_profile": driver_profile})
        resp.raise_for_status()
        return resp.json()

    async def get_districts(self) -> list[dict]:
        resp = await self._client.get("/v1/districts")
        resp.raise_for_status()
        return resp.json()

    async def get_recommendation(
        self, user_id: str, lat: float, lng: float, horizon_minutes: int = 30
    ) -> dict:
        resp = await self._client.post(
            f"/v1/recommendations/{user_id}",
            json={"lat": lat, "lng": lng, "horizon_minutes": horizon_minutes},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_current_surge(self) -> list[dict]:
        resp = await self._client.get("/v1/surge/current")
        resp.raise_for_status()
        return resp.json()

    async def get_finance_daily_summary(self, user_id: str) -> dict:
        resp = await self._client.get("/v1/finance/daily-summary", params={"user_id": user_id})
        resp.raise_for_status()
        return resp.json()

    async def get_daily_plan(self) -> list[dict]:
        resp = await self._client.get("/v1/forecasts/daily-plan")
        resp.raise_for_status()
        return resp.json()

    async def ocr_ingest_kef(
        self, image_b64: str, user_id: str | None = None, mime: str = "image/jpeg"
    ) -> dict:
        payload: dict = {"image_b64": image_b64, "mime": mime}
        if user_id:
            payload["user_id"] = user_id
        # vision OCR is slow — give it well past the client default
        resp = await self._client.post("/v1/kef/ocr-ingest", json=payload, timeout=90.0)
        resp.raise_for_status()
        return resp.json()

    async def create_link_code(self, user_id: str) -> dict:
        resp = await self._client.post("/v1/link/code", json={"user_id": user_id})
        resp.raise_for_status()
        return resp.json()

    async def redeem_link_code_telegram(self, code: str, telegram_id: int) -> httpx.Response:
        """Returns the raw response so the handler can distinguish 404/410
        (bad/expired code) from success without raising."""
        return await self._client.post(
            "/v1/link/redeem-telegram", json={"code": code, "telegram_id": telegram_id}
        )

    async def close(self) -> None:
        await self._client.aclose()


api_client = ApiClient()
