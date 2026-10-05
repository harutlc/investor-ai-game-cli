"""Claude voice via the Anthropic Messages API, with structured JSON output."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import anthropic

from .. import llmlog
from .base import VoiceDraft, VoiceError, VoiceRequest
from .prompts import parse_draft, system_prompt, user_prompt

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TOKENS = 8_000
# Models that accept output_config.effort and the server-side "default" refusal fallback.
CURRENT_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

OPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["counter", "message"]},
        "label": {"type": "string"},
        "amount": {"type": "integer", "description": "euros; 0 for a message"},
        "equity": {"type": "number", "description": "percent; 0 for a message"},
        "text": {"type": "string", "description": "what the founder says; empty for a counter"},
    },
    "required": ["kind", "label", "amount", "equity", "text"],
    "additionalProperties": False,
}
REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "options": {"type": "array", "items": OPTION_SCHEMA},
    },
    "required": ["reply", "options"],
    "additionalProperties": False,
}


class ClaudeVoiceBackend:
    name = "claude"

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 timeout: float = 60.0, client: Any = None):
        self.model = model or DEFAULT_MODEL
        # One attempt only: the voice has its own retry and a template fallback,
        # and SDK retries would multiply the time limit.
        self._client = client or anthropic.Anthropic(
            api_key=api_key, timeout=timeout, max_retries=0
        )

    def compose(self, request: VoiceRequest, correction: str | None = None) -> VoiceDraft:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": system_prompt(request),
            "messages": [{"role": "user", "content": user_prompt(request, correction)}],
            "output_config": {"format": {"type": "json_schema", "schema": REPLY_SCHEMA}},
        }
        if self.model in CURRENT_MODELS:
            params["output_config"]["effort"] = "low"  # short in-character chat
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        api = self._client.beta.messages if "betas" in params else self._client.messages
        started_at, started = llmlog.now(), time.monotonic()
        try:
            raw = api.with_raw_response.create(**params)
            body = raw.read()
            response = raw.parse()
        except anthropic.APITimeoutError as exc:
            self._record(started_at, started, getattr(exc, "request", None),
                         error=("timeout", "claude timed out"))
            raise VoiceError("claude timed out") from exc
        except anthropic.APIConnectionError as exc:
            self._record(started_at, started, getattr(exc, "request", None),
                         error=("connection", type(exc).__name__))
            raise VoiceError("claude connection failed") from exc
        except anthropic.APIStatusError as exc:
            self._record(started_at, started, None, response=exc.response,
                         error=("http_status", f"HTTP {exc.status_code}"))
            raise VoiceError(f"claude returned HTTP {exc.status_code}") from exc

        refused = getattr(response, "stop_reason", None) == "refusal"
        self._record(
            started_at, started, raw.http_request,
            response=SimpleNamespace(status_code=raw.status_code, headers=raw.headers,
                                     content=body),
            error=("refused", "stop_reason refusal") if refused else None,
        )
        if refused:
            raise VoiceError("claude declined the request")
        text = next(
            (block.text for block in response.content if getattr(block, "type", "") == "text"),
            "",
        )
        return parse_draft(text, request)

    def _record(self, started_at: Any, started: float, http_request: Any,
                response: Any = None, error: tuple[str, str] | None = None) -> None:
        llmlog.record_http(
            "voice-claude", self.model, http_request, started_at,
            llmlog.elapsed_ms(started, time.monotonic()), response=response,
            error={"type": error[0], "message": error[1]} if error else None,
        )
