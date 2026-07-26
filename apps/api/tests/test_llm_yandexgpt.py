"""Unit tests for the YandexGPT Foundation Models provider. Fully network-free:
httpx.post is monkeypatched with a fake that returns a canned Foundation Models
response envelope. Covers chat text extraction, analyze_trip JSON parsing from
fenced/plain responses, and graceful degradation on malformed output."""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.providers.live import llm_yandexgpt
from app.providers.live.llm_yandexgpt import YandexGPTLLMProvider


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self._text = text

    def raise_for_status(self) -> None:  # pragma: no cover - always ok here
        return None

    def json(self) -> dict[str, Any]:
        return {"result": {"alternatives": [{"message": {"text": self._text}}]}}


def _patch_completion(monkeypatch: pytest.MonkeyPatch, reply_text: str) -> dict[str, Any]:
    """Replace httpx.post with a fake returning reply_text; capture the request
    payload so tests can assert on endpoint/auth/body shape."""
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        return _FakeResponse(reply_text)

    monkeypatch.setattr(llm_yandexgpt.httpx, "post", fake_post)
    return captured


def test_chat_returns_alternative_text(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_completion(monkeypatch, "Сегодня спрос выше в центре.")
    provider = YandexGPTLLMProvider()

    reply = provider.chat("где лучше работать?", {"latest_recommendation": None})

    assert reply == "Сегодня спрос выше в центре."
    # Endpoint, auth header and payload shape are the contract with Foundation Models.
    assert captured["url"] == llm_yandexgpt._COMPLETION_URL
    assert captured["headers"]["Authorization"].startswith("Api-Key ")
    assert "x-folder-id" in captured["headers"]
    body = captured["json"]
    assert body["modelUri"].startswith("gpt://")
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1]["role"] == "user"
    assert "text" in body["messages"][0]


def test_analyze_trip_parses_plain_json(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "summary_text": "Вы ждали дольше обычного.",
        "estimated_missed_earnings": 120.5,
        "suggested_action": "Поезжайте в центр.",
    }
    _patch_completion(monkeypatch, json.dumps(payload, ensure_ascii=False))
    provider = YandexGPTLLMProvider()

    result = provider.analyze_trip({"trip": {}})

    assert result["summary_text"] == payload["summary_text"]
    assert result["estimated_missed_earnings"] == 120.5
    assert result["suggested_action"] == "Поезжайте в центр."
    assert result["model_used"] == provider.settings.yandexgpt_model


def test_analyze_trip_parses_fenced_json_with_prose(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "summary_text": "Чек за км ниже среднего.",
        "estimated_missed_earnings": None,
        "suggested_action": None,
    }
    fenced = (
        "Вот анализ поездки:\n"
        "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```\n"
        "Надеюсь, это поможет!"
    )
    _patch_completion(monkeypatch, fenced)
    provider = YandexGPTLLMProvider()

    result = provider.analyze_trip({"trip": {}})

    assert result["summary_text"] == payload["summary_text"]
    assert result["estimated_missed_earnings"] is None
    assert result["model_used"] == provider.settings.yandexgpt_model


def test_analyze_trip_degrades_gracefully_on_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    prose = "Извините, не могу сформировать JSON, но поездка была обычной."
    _patch_completion(monkeypatch, prose)
    provider = YandexGPTLLMProvider()

    result = provider.analyze_trip({"trip": {}})

    # Caller reads these keys unconditionally — they must always be present.
    assert result["summary_text"] == prose
    assert result["estimated_missed_earnings"] is None
    assert result["suggested_action"] is None
    assert result["model_used"] == provider.settings.yandexgpt_model
