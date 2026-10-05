"""Ollama voice: a local model through ``POST /api/chat`` with JSON output."""

from __future__ import annotations

import httpx

from .base import VoiceDraft, VoiceError, VoiceRequest
from .prompts import parse_draft, system_prompt, user_prompt

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1"


class OllamaVoiceBackend:
    name = "ollama"

    def __init__(self, host: str | None = None, model: str | None = None, timeout: float = 60.0,
                 transport: httpx.BaseTransport | None = None):
        self.model = model or DEFAULT_MODEL
        self._client = httpx.Client(
            base_url=(host or DEFAULT_HOST).rstrip("/"), timeout=timeout, transport=transport
        )

    def compose(self, request: VoiceRequest, correction: str | None = None) -> VoiceDraft:
        body = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system_prompt(request)},
                {"role": "user", "content": user_prompt(request, correction)},
            ],
        }
        try:
            response = self._client.post("/api/chat", json=body)
        except httpx.TimeoutException as exc:
            raise VoiceError("ollama timed out") from exc
        except httpx.HTTPError as exc:
            raise VoiceError("ollama is unreachable") from exc
        if response.status_code != 200:
            raise VoiceError(f"ollama returned HTTP {response.status_code}")
        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise VoiceError("ollama returned an unexpected response") from exc
        return parse_draft(content, request)
