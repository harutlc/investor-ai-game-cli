"""Ollama voice: a local model through ``POST /api/chat`` with JSON output."""

from __future__ import annotations

import time
from typing import Any

import httpx

from .. import llmlog
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
        http_request = self._client.build_request("POST", "/api/chat", json=body)
        started_at, started = llmlog.now(), time.monotonic()
        try:
            response = self._client.send(http_request)
        except httpx.TimeoutException as exc:
            self._record(http_request, started_at, started, error=("timeout", "ollama timed out"))
            raise VoiceError("ollama timed out") from exc
        except httpx.HTTPError as exc:
            self._record(http_request, started_at, started,
                         error=("connection", type(exc).__name__))
            raise VoiceError("ollama is unreachable") from exc
        error = None if response.status_code == 200 else (
            "http_status", f"HTTP {response.status_code}")
        self._record(http_request, started_at, started, response=response, error=error)
        if response.status_code != 200:
            raise VoiceError(f"ollama returned HTTP {response.status_code}")
        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise VoiceError("ollama returned an unexpected response") from exc
        return parse_draft(content, request)

    def _record(self, http_request: httpx.Request, started_at: Any, started: float,
                response: httpx.Response | None = None,
                error: tuple[str, str] | None = None) -> None:
        llmlog.record_http(
            "voice-ollama", self.model, http_request, started_at,
            llmlog.elapsed_ms(started, time.monotonic()), response=response,
            error={"type": error[0], "message": error[1]} if error else None,
        )
