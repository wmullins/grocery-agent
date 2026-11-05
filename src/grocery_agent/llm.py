from __future__ import annotations

import json
from typing import Any

import httpx

from .config import LlmSettings
from .models import RecipeDraft


class LLMError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: LlmSettings) -> None:
        self.settings = settings

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.settings.base_url.rstrip("/"), timeout=self.settings.timeout_seconds)

    def available(self) -> bool:
        if not self.settings.enabled:
            return False
        try:
            with self._client() as client:
                response = client.get("/api/tags")
                response.raise_for_status()
                return True
        except httpx.HTTPError:
            return False

    def _chat(self, system: str, prompt: str) -> str:
        payload = {
            "model": self.settings.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.1},
        }
        with self._client() as client:
            response = client.post("/api/chat", json=payload)
            if response.status_code >= 400:
                raise LLMError(f"Ollama returned HTTP {response.status_code}")
            data = response.json()
        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMError("Ollama returned an empty response")
        return content

    def _json(self, system: str, prompt: str) -> dict[str, Any]:
        content = self._chat(system, prompt)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError("Ollama returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise LLMError("Ollama returned a non-object JSON value")
        return parsed

    def extract_recipe(self, title: str, body: str) -> RecipeDraft | None:
        if not self.available():
            return None
        system = (
            "You extract recipes from personal notes. Return one JSON object only. "
            "Never invent ingredients, quantities, or servings. Use null when unknown. "
            "Preserve the note's meaning and mark uncertain values with lower confidence."
        )
        prompt = (
            f"Title: {title}\n\n"
            "Return JSON with keys: title, servings, prep_minutes, cook_minutes, "
            "ingredients (array of objects with name, quantity, unit, optional, note), "
            "tags (array of strings), confidence (0 to 1).\n\n"
            f"Note:\n{body[:12000]}"
        )
        try:
            data = self._json(system, prompt)
            return RecipeDraft.model_validate(data)
        except (LLMError, ValueError):
            return None
