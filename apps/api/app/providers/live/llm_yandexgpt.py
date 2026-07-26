"""Real YandexGPT (Yandex Cloud Foundation Models) call. Selected automatically
once YANDEXGPT_API_KEY is set (see app/providers/factory.py) — no other code
changes needed. Mirrors llm_openai.py: same system prompts and behaviour, only
the transport (endpoint, auth, payload/response shape) differs.

Foundation Models has no native response_format/JSON mode, so analyze_trip
parses the JSON object out of the returned free text and degrades to a safe
default dict if the model doesn't return valid JSON.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import get_settings

_COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# Kept identical to llm_openai.py so switching providers is a pure transport swap.
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

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any] | None:
    """Robustly pull a JSON object out of a free-text completion: try the raw
    text, then a ```json fenced block, then the first balanced {...} span.
    Returns None if nothing parses."""
    candidates: list[str] = [text.strip()]

    fenced = _JSON_FENCE_RE.search(text)
    if fenced:
        candidates.append(fenced.group(1).strip())

    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidates.append(text[first : last + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


class YandexGPTLLMProvider:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def _model_uri(self) -> str:
        return f"gpt://{self.settings.yandexgpt_folder_id}/{self.settings.yandexgpt_model}"

    def _call(self, system_prompt: str, user_content: str) -> str:
        resp = httpx.post(
            _COMPLETION_URL,
            headers={
                "Authorization": f"Api-Key {self.settings.yandexgpt_api_key}",
                "x-folder-id": self.settings.yandexgpt_folder_id,
            },
            json={
                "modelUri": self._model_uri,
                "completionOptions": {"temperature": 0.3, "maxTokens": 2000},
                "messages": [
                    {"role": "system", "text": system_prompt},
                    {"role": "user", "text": user_content},
                ],
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        return resp.json()["result"]["alternatives"][0]["message"]["text"]

    def analyze_trip(self, context: dict[str, Any]) -> dict[str, Any]:
        raw = self._call(_ANALYSIS_SYSTEM_PROMPT, json.dumps(context, default=str))
        parsed = _extract_json(raw)
        if parsed is None:
            # No native JSON mode: if the model returned prose, keep the driver
            # from losing the insight entirely — surface the text as the summary
            # rather than raising (the caller reads summary_text/model_used).
            parsed = {
                "summary_text": raw.strip(),
                "estimated_missed_earnings": None,
                "suggested_action": None,
            }
        parsed.setdefault("summary_text", "")
        parsed.setdefault("estimated_missed_earnings", None)
        parsed.setdefault("suggested_action", None)
        parsed["model_used"] = self.settings.yandexgpt_model
        return parsed

    def chat(self, message: str, context: dict[str, Any]) -> str:
        user_content = json.dumps({"message": message, "context": context}, default=str)
        return self._call(_CHAT_SYSTEM_PROMPT, user_content)
