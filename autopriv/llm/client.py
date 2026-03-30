from __future__ import annotations

import json
import urllib.request
from typing import Any

from autopriv.settings import AppSettings


class LLMConfigError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def ensure_ready(self) -> None:
        model = self.settings.model
        if not model or not model.enabled:
            raise LLMConfigError(
                "Missing LLM config: AUTOPRIV_LLM_API_KEY, AUTOPRIV_LLM_BASE_URL and AUTOPRIV_LLM_MODEL are required"
            )

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> dict[str, Any]:
        self.ensure_ready()
        model = self.settings.model
        assert model is not None

        base_url = (model.base_url or "").rstrip("/")
        url = f"{base_url}/chat/completions"
        payload = {
            "model": model.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        req = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {model.api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=self.settings.model_timeout_s) as resp:
            raw = json.loads(resp.read().decode("utf-8"))

        content = raw["choices"][0]["message"]["content"]
        return _safe_json_load(content)


def _safe_json_load(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json\n", "", 1).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise LLMConfigError("LLM output is not a JSON object")
    return data
