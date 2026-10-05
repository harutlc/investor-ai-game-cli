"""HTTP adapter for System One decision models: TypeSafe Jev (hosted) and Laya (local).

Both speak ``POST /v1/systemone`` with ``{model, state, questions}`` and return
``{answers: {id: {type, noul | choice | score, probabilities, confidence}}}``.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from .base import BrainError, Question, RawAnswer

JEV_BASE_URL = "https://api.typesafe.ai"
JEV_MODEL = "jev-latest"
LAYA_BASE_URL = "http://localhost:8000"
LAYA_MODEL = "laya"
PATH = "/v1/systemone"
RETRY_STATUSES = (429, 529)
RETRY_BACKOFF = 0.5


class SystemOneBackend:
    """One code path for Jev and Laya; only the base URL, model and auth differ."""

    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.name = name
        self.model = model
        self.timeout = timeout
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers, transport=transport
        )

    @classmethod
    def jev(cls, api_key: str, base_url: str | None = None, model: str | None = None,
            timeout: float = 10.0) -> SystemOneBackend:
        return cls("jev", base_url or JEV_BASE_URL, model or JEV_MODEL, api_key, timeout)

    @classmethod
    def laya(cls, base_url: str | None = None, model: str | None = None,
             api_key: str | None = None, timeout: float = 10.0) -> SystemOneBackend:
        return cls("laya", base_url or LAYA_BASE_URL, model or LAYA_MODEL, api_key, timeout)

    def close(self) -> None:
        self._client.close()

    def ask(self, state: dict[str, Any], questions: list[Question]) -> dict[str, RawAnswer]:
        body = {
            "model": self.model,
            "state": state,
            "questions": {q.id: q.to_api() for q in questions},
        }
        deadline = time.monotonic() + self.timeout
        response = self._post(body, deadline)
        if response.status_code in RETRY_STATUSES and deadline - time.monotonic() > RETRY_BACKOFF:
            time.sleep(RETRY_BACKOFF)
            response = self._post(body, deadline)
        if response.status_code != 200:
            raise BrainError(f"{self.name} returned HTTP {response.status_code}")
        try:
            payload = response.json()
            answers = payload["answers"]
            return {q.id: parse_answer(answers[q.id], q) for q in questions}
        except (ValueError, KeyError, TypeError) as exc:
            raise BrainError(f"{self.name} returned a malformed response: {exc!r}") from exc

    def _post(self, body: dict[str, Any], deadline: float) -> httpx.Response:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BrainError(f"{self.name} timed out")
        try:
            return self._client.post(PATH, json=body, timeout=remaining)
        except httpx.TimeoutException as exc:
            raise BrainError(f"{self.name} timed out") from exc
        except httpx.HTTPError as exc:
            raise BrainError(f"{self.name} request failed: {exc!r}") from exc


def _probabilities(data: dict[str, Any]) -> dict[str, float]:
    raw = data.get("probabilities") or {}
    if not isinstance(raw, dict):
        raise TypeError("probabilities must be an object")
    return {str(k): float(v) for k, v in raw.items()}


def parse_answer(data: dict[str, Any], question: Question) -> RawAnswer:
    """Normalise one answer. Tolerates a missing ``confidence`` (derived from probabilities)."""
    kind = data.get("type", question.type)
    if kind != question.type:
        raise TypeError(f"expected {question.type} answer, got {kind}")
    probabilities = _probabilities(data)
    confidence = data.get("confidence")
    if kind == "noul":
        value = float(data["noul"])
        if not 0.0 <= value <= 1.0:
            raise ValueError("noul out of range")
        return RawAnswer(type="noul", noul=value)
    if kind == "choice":
        choice = str(data["choice"])
        if confidence is None:
            confidence = probabilities.get(choice, 0.0)
        return RawAnswer(type="choice", choice=choice, confidence=float(confidence),
                         probabilities=probabilities)
    if probabilities:
        level = int(max(probabilities, key=lambda k: probabilities[k]))
    else:
        level = int(round(float(data["score"])))
    if confidence is None:
        confidence = probabilities.get(str(level), 0.0)
    return RawAnswer(type="score", level=level, confidence=float(confidence),
                     probabilities=probabilities)
