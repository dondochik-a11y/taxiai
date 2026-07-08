"""Real OpenAI Chat Completions call. Selected automatically once OPENAI_API_KEY
is set (see app/providers/factory.py) — no other code changes needed.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import get_settings

_CHAT_URL = "https://api.openai.com/v1/chat/completions"

_ANALYSIS_SYSTEM_PROMPT = (
    "You are a Yandex Taxi driver analytics assistant. Given structured trip and "
    "market context as JSON, respond ONLY with a JSON object: "
    '{"summary_text": str, "estimated_missed_earnings": number|null, "suggested_action": str|null}. '
    "Be concise, concrete, and reference real numbers from the context."
)

_CHAT_SYSTEM_PROMPT = (
    "You are a Yandex Taxi driver's AI copilot. Answer using only the structured "
    "context JSON provided — real recommendations, forecasts, and finance history. "
    "Be concise and actionable."
)


class OpenAILLMProvider:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _call(self, system_prompt: str, user_content: str) -> str:
        resp = httpx.post(
            _CHAT_URL,
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            json={
                "model": self.settings.openai_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def analyze_trip(self, context: dict[str, Any]) -> dict[str, Any]:
        raw = self._call(_ANALYSIS_SYSTEM_PROMPT, json.dumps(context, default=str))
        parsed = json.loads(raw)
        parsed["model_used"] = self.settings.openai_model
        return parsed

    def chat(self, message: str, context: dict[str, Any]) -> str:
        user_content = json.dumps({"message": message, "context": context}, default=str)
        return self._call(_CHAT_SYSTEM_PROMPT, user_content)
