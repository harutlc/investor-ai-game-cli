"""HTTP adapter for System One decision models: TypeSafe Jev (hosted) and Laya (local).

Both speak ``POST /v1/systemone`` with ``{model, state, questions}`` and return
``{answers: {id: {type, noul | choice | score, probabilities, confidence}}}``.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from .. import llmlog
from .base import BrainError, Question, RawAnswer

JEV_BASE_URL = "https://api.typesafe.ai"
JEV_MODEL = "jev-latest"
LAYA_BASE_URL = "http://localhost:8000"
LAYA_MODEL: str | None = None  # unset: Laya's router picks the checkpoint by language
AUTO_MODEL_LABEL = "auto"  # how an unset model is shown in logs and game.json
PATH = "/v1/systemone"
RETRY_STATUSES = (429, 529)
RETRY_BACKOFF = 0.5


class SystemOneBackend:
    """One code path for Jev and Laya; only the base URL, model and auth differ."""

    def __init__(
        self,
        name: str,
        base_url: str,
        model: str | None,
        api_key: str | None = None,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        jev_confidence: bool = False,
    ):
        self.name = name
        self.model = model
        self.timeout = timeout
        # Recompute choice/score confidence on Jev's scale from the probabilities
        # (Laya reports 1 - normalised entropy instead).
        self.jev_confidence = jev_confidence
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
        return cls("laya", base_url or LAYA_BASE_URL, model or LAYA_MODEL, api_key, timeout,
                   jev_confidence=True)

    def close(self) -> None:
        self._client.close()

    def ask(self, state: dict[str, Any], questions: list[Question]) -> dict[str, RawAnswer]:
        body: dict[str, Any] = {} if self.model is None else {"model": self.model}
        body["state"] = state
        body["questions"] = {q.id: q.to_api() for q in questions}
        deadline = time.monotonic() + self.timeout
        response, logging_time = self._post(body, deadline)
        deadline += logging_time  # writing call logs never eats into the time limit
        if response.status_code in RETRY_STATUSES and deadline - time.monotonic() > RETRY_BACKOFF:
            time.sleep(RETRY_BACKOFF)
            response, _ = self._post(body, deadline)
        if response.status_code != 200:
            raise BrainError(f"{self.name} returned HTTP {response.status_code}")
        try:
            payload = response.json()
            answers = payload["answers"]
            return {q.id: parse_answer(answers[q.id], q, self.jev_confidence)
                    for q in questions}
        except (ValueError, KeyError, TypeError) as exc:
            raise BrainError(f"{self.name} returned a malformed response: {exc!r}") from exc

    def _post(self, body: dict[str, Any], deadline: float) -> tuple[httpx.Response, float]:
        """POST once and record the exchange; returns the response and time spent logging."""
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BrainError(f"{self.name} timed out")
        request = self._client.build_request("POST", PATH, json=body, timeout=remaining)
        started_at, started = llmlog.now(), time.monotonic()
        try:
            response = self._client.send(request)
        except httpx.TimeoutException as exc:
            self._record(request, started_at, started, error=("timeout", f"{self.name} timed out"))
            raise BrainError(f"{self.name} timed out") from exc
        except httpx.HTTPError as exc:
            self._record(request, started_at, started, error=("connection", type(exc).__name__))
            raise BrainError(f"{self.name} request failed: {exc!r}") from exc
        finished = time.monotonic()
        error = None if response.status_code == 200 else (
            "http_status", f"HTTP {response.status_code}")
        self._record(request, started_at, started, response=response, error=error,
                     finished=finished)
        return response, time.monotonic() - finished

    def _record(self, request: httpx.Request, started_at: Any, started: float,
                response: httpx.Response | None = None,
                error: tuple[str, str] | None = None, finished: float | None = None) -> None:
        llmlog.record_http(
            f"brain-{self.name}", self.model or AUTO_MODEL_LABEL, request, started_at,
            llmlog.elapsed_ms(started, finished or time.monotonic()), response=response,
            error={"type": error[0], "message": error[1]} if error else None,
        )

def _probabilities(data: dict[str, Any]) -> dict[str, float]:
    raw = data.get("probabilities") or {}
    if not isinstance(raw, dict):
        raise TypeError("probabilities must be an object")
    return {str(k): float(v) for k, v in raw.items()}


def jev_scale_confidence(probabilities: dict[str, float], chosen: str) -> float | None:
    """Jev's confidence ``(n*p - 1)/(n - 1)`` from a probability distribution, in [0, 1]."""
    if not probabilities or chosen not in probabilities:
        return None
    n, p = len(probabilities), probabilities[chosen]
    if n < 2:
        return max(0.0, min(1.0, p))
    return max(0.0, min(1.0, (n * p - 1) / (n - 1)))


def _confidence(data: dict[str, Any], probabilities: dict[str, float], chosen: str,
                recompute: bool) -> float:
    if recompute:
        value = jev_scale_confidence(probabilities, chosen)
        if value is None:
            value = data.get("answer_confidence", data.get("confidence"))
    else:
        value = data.get("confidence")
    if value is None:
        value = probabilities.get(chosen, 0.0)
    return float(value)


def parse_answer(data: dict[str, Any], question: Question,
                 recompute_confidence: bool = False) -> RawAnswer:
    """Normalise one answer.

    Tolerates a missing ``confidence`` (derived from probabilities). With
    ``recompute_confidence`` (Laya), choice/score confidence is recomputed on Jev's scale.
    """
    kind = data.get("type", question.type)
    if kind != question.type:
        raise TypeError(f"expected {question.type} answer, got {kind}")
    probabilities = _probabilities(data)
    if kind == "noul":
        value = float(data["noul"])
        if not 0.0 <= value <= 1.0:
            raise ValueError("noul out of range")
        return RawAnswer(type="noul", noul=value)
    if kind == "choice":
        choice = str(data["choice"])
        return RawAnswer(type="choice", choice=choice,
                         confidence=_confidence(data, probabilities, choice,
                                                recompute_confidence),
                         probabilities=probabilities)
    if probabilities:
        level = int(max(probabilities, key=lambda k: probabilities[k]))
    else:
        level = int(round(float(data["score"])))
    return RawAnswer(type="score", level=level,
                     confidence=_confidence(data, probabilities, str(level),
                                            recompute_confidence),
                     probabilities=probabilities)
