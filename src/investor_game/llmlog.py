"""Opt-in LLM call logs: one folder per game, one sub-folder per LLM, one JSON file per call.

The engine opens a ``scope`` (game log, turn, purpose) around each brain or voice call;
backends call ``record`` with the raw HTTP exchange. Without an active scope (logging
off) ``record`` does nothing. Logging failures never propagate into the game.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

REDACTED = "[REDACTED]"
SECRET_HEADERS = frozenset(
    {"authorization", "proxy-authorization", "x-api-key", "api-key", "cookie", "set-cookie"}
)
MIN_SECRET_LENGTH = 4


def now() -> datetime:
    return datetime.now().astimezone()


def _decode_body(body: Any) -> Any:
    """Bytes or text → parsed JSON when possible, else text. Objects pass through."""
    if body is None:
        return None
    if isinstance(body, bytes | bytearray):
        if not body:
            return None
        body = bytes(body).decode("utf-8", errors="replace")
    if isinstance(body, str):
        try:
            return json.loads(body)
        except ValueError:
            return body
    return body


def _headers(headers: Mapping[str, str] | Iterable[tuple[str, str]] | None) -> dict[str, str]:
    if headers is None:
        return {}
    items = headers.items() if hasattr(headers, "items") else headers
    return {
        str(name).lower(): REDACTED if str(name).lower() in SECRET_HEADERS else str(value)
        for name, value in items
    }


@dataclass
class Exchange:
    """One HTTP request and its response (or the error instead of a response)."""

    service: str  # sub-folder name, e.g. "brain-jev", "voice-claude"
    model: str
    method: str
    url: str
    request_headers: Any
    request_body: Any
    started_at: datetime
    duration_ms: int
    status: int | None = None
    response_headers: Any = None
    response_body: Any = None
    error: dict[str, str] | None = None
    received: bool = False  # True when a response arrived (even an error status)


class GameLog:
    """The log folder of one game. ``record`` never raises."""

    def __init__(self, folder: Path, game_id: int, secrets: Iterable[str] = (),
                 failed: bool = False, warning: str | None = None):
        self.folder = folder
        self.game_id = game_id
        self.secrets = [s for s in secrets if s and len(s) >= MIN_SECRET_LENGTH]
        self.failed = failed
        self.warning = warning
        self._sequences: dict[str, int] = {}

    def _fail(self) -> None:
        self.failed = True
        self.warning = f"LLM logging stopped for this game: could not write to {self.folder}."

    def _scrub(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, REDACTED)
        return text

    def write_json(self, path: Path, document: Any) -> None:
        """Atomic write (tmp file + replace) of pretty UTF-8 JSON, secrets scrubbed."""
        text = self._scrub(json.dumps(document, indent=2, ensure_ascii=False, default=str))
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text + "\n", encoding="utf-8")
        os.replace(tmp, path)

    def record(self, exchange: Exchange, turn: int, purpose: str) -> Path | None:
        if self.failed:
            return None
        try:
            sequence = self._sequences.get(exchange.service, 0) + 1
            service_dir = self.folder / exchange.service
            service_dir.mkdir(parents=True, exist_ok=True)
            path = service_dir / f"{sequence:03d}_turn{turn:02d}_{purpose}.json"
            document = {
                "service": exchange.service,
                "model": exchange.model,
                "game": self.game_id,
                "turn": turn,
                "purpose": purpose,
                "sequence": sequence,
                "started_at": exchange.started_at.isoformat(timespec="milliseconds"),
                "duration_ms": exchange.duration_ms,
                "request": {
                    "method": exchange.method,
                    "url": exchange.url,
                    "headers": _headers(exchange.request_headers),
                    "body": _decode_body(exchange.request_body),
                },
                "response": (
                    {
                        "status": exchange.status,
                        "headers": _headers(exchange.response_headers),
                        "body": _decode_body(exchange.response_body),
                    }
                    if exchange.received
                    else None
                ),
                "error": exchange.error,
            }
            self.write_json(path, document)
            self._sequences[exchange.service] = sequence
            return path
        except Exception:  # noqa: BLE001 - logging must never break a turn
            self._fail()
            return None


class LogRoot:
    """The configured log directory; creates one ``GameLog`` folder per game."""

    def __init__(self, path: Path | str, secrets: Iterable[str] = ()):
        self.path = Path(path)
        self.secrets = list(secrets)

    def start_game(self, game_id: int, persona_id: str, metadata: Mapping[str, Any],
                   started: datetime | None = None) -> GameLog:
        """Create ``<time>_g<id>_<persona>`` (with ``-2``… on collision) and ``game.json``."""
        started = started or now()
        base = f"{started.strftime('%Y-%m-%dT%H-%M-%S')}_g{game_id}_{persona_id}"
        folder = self.path / base
        try:
            self.path.mkdir(parents=True, exist_ok=True)
            suffix = 1
            while True:
                try:
                    folder.mkdir(exist_ok=False)
                    break
                except FileExistsError:
                    suffix += 1
                    folder = self.path / f"{base}-{suffix}"
            log = GameLog(folder, game_id, self.secrets)
            log.write_json(folder / "game.json", {
                "game": game_id,
                "started_at": started.isoformat(timespec="seconds"),
                **metadata,
            })
            return log
        except Exception:  # noqa: BLE001 - logging must never break a game
            log = GameLog(folder, game_id, self.secrets)
            log._fail()
            return log


# ---------------------------------------------------------------------------
# Scopes: which game, turn and purpose the next LLM calls belong to.
# ---------------------------------------------------------------------------


@dataclass
class _Scope:
    log: GameLog | None
    turn: int
    purpose: str
    calls: dict[str, int] = field(default_factory=dict)


_ACTIVE: ContextVar[_Scope | None] = ContextVar("investor_game_llm_log_scope", default=None)


@contextmanager
def scope(log: GameLog | None, turn: int, purpose: str) -> Iterator[None]:
    """Attribute LLM calls made inside the block to ``log`` at ``turn``/``purpose``."""
    token = _ACTIVE.set(_Scope(log, turn, purpose))
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def active() -> bool:
    current = _ACTIVE.get()
    return current is not None and current.log is not None and not current.log.failed


def record(exchange: Exchange) -> None:
    """Write ``exchange`` into the active scope's game log; a no-op when logging is off.

    The second call to the same service within one scope is tagged ``_retry``,
    the third ``_retry2`` and so on.
    """
    current = _ACTIVE.get()
    if current is None or current.log is None or current.log.failed:
        return
    count = current.calls.get(exchange.service, 0) + 1
    current.calls[exchange.service] = count
    retry = "" if count == 1 else ("_retry" if count == 2 else f"_retry{count - 1}")
    current.log.record(exchange, current.turn, f"{current.purpose}{retry}")


def record_http(service: str, model: str, request: Any, started_at: datetime,
                duration_ms: int, response: Any = None,
                error: dict[str, str] | None = None) -> None:
    """Record an httpx/httpx2 request and optional response (duck-typed)."""
    if not active():
        return
    if response is not None and request is None:
        request = getattr(response, "request", None)
    exchange = Exchange(
        service=service,
        model=model,
        method=getattr(request, "method", "") if request is not None else "",
        url=str(getattr(request, "url", "")) if request is not None else "",
        request_headers=getattr(request, "headers", None),
        request_body=_safe_content(request),
        started_at=started_at,
        duration_ms=duration_ms,
        error=error,
    )
    if response is not None:
        exchange.received = True
        exchange.status = getattr(response, "status_code", None)
        exchange.response_headers = getattr(response, "headers", None)
        exchange.response_body = _safe_content(response)
    record(exchange)


def _safe_content(message: Any) -> Any:
    """Body bytes of an httpx request/response; ``None`` when unavailable (e.g. streamed)."""
    if message is None:
        return None
    try:
        return message.content
    except Exception:  # noqa: BLE001 - unread/streaming bodies are simply not logged
        return None


def elapsed_ms(started: float, finished: float) -> int:
    return int((finished - started) * 1000)
