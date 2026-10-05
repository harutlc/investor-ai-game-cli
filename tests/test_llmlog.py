import json
import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from investor_game import llmlog
from investor_game.llmlog import Exchange, GameLog, LogRoot

STARTED = datetime(2026, 10, 5, 11, 42, 7, tzinfo=timezone(timedelta(hours=4)))
META = {"persona": {"id": "rex", "name": "Rex Calloway"}, "brain": {"backend": "jev"}}


def exchange(service="brain-jev", **overrides):
    values = dict(
        service=service, model="jev-latest", method="POST",
        url="https://api.typesafe.ai/v1/systemone",
        request_headers={"Authorization": "Bearer ts-secret-123",
                         "Content-Type": "application/json"},
        request_body=b'{"model": "jev-latest", "state": {"text": "\\u20ac500k"}}',
        started_at=STARTED, duration_ms=812, received=True, status=200,
        response_headers={"content-type": "application/json"},
        response_body=b'{"answers": {"accept": {"type": "noul", "noul": 0.1}}}',
    )
    values.update(overrides)
    return Exchange(**values)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


# --- folders ----------------------------------------------------------------


def test_game_folder_and_metadata(tmp_path):
    root = LogRoot(tmp_path / "logs" / "nested")
    log = root.start_game(1, "rex", META, started=STARTED)
    assert log.folder.name == "2026-10-05T11-42-07_g1_rex"
    assert log.folder.parent == tmp_path / "logs" / "nested"
    game = read(log.folder / "game.json")
    assert game["game"] == 1
    assert game["started_at"] == "2026-10-05T11:42:07+04:00"
    assert game["persona"] == {"id": "rex", "name": "Rex Calloway"}
    assert game["brain"] == {"backend": "jev"}


def test_collision_suffix(tmp_path):
    root = LogRoot(tmp_path)
    first = root.start_game(1, "rex", META, started=STARTED)
    (first.folder / "keep.txt").write_text("untouched")
    second = root.start_game(1, "rex", META, started=STARTED)
    third = root.start_game(1, "rex", META, started=STARTED)
    assert second.folder.name == "2026-10-05T11-42-07_g1_rex-2"
    assert third.folder.name == "2026-10-05T11-42-07_g1_rex-3"
    assert (first.folder / "keep.txt").read_text() == "untouched"


# --- files ------------------------------------------------------------------


def test_record_names_order_and_content(tmp_path):
    log = LogRoot(tmp_path).start_game(1, "rex", META, started=STARTED)
    first = log.record(exchange(), 1, "offer")
    second = log.record(exchange(), 2, "message")
    voice = log.record(exchange("voice-claude"), 0, "open")
    assert first.relative_to(log.folder).as_posix() == "brain-jev/001_turn01_offer.json"
    assert second.name == "002_turn02_message.json"
    assert voice.relative_to(log.folder).as_posix() == "voice-claude/001_turn00_open.json"
    doc = read(first)
    assert doc["service"] == "brain-jev" and doc["model"] == "jev-latest"
    assert (doc["game"], doc["turn"], doc["purpose"], doc["sequence"]) == (1, 1, "offer", 1)
    assert doc["started_at"] == "2026-10-05T11:42:07.000+04:00"
    assert doc["duration_ms"] == 812
    assert doc["request"]["method"] == "POST"
    assert doc["request"]["body"] == {"model": "jev-latest", "state": {"text": "€500k"}}
    assert doc["response"]["status"] == 200
    assert doc["response"]["body"]["answers"]["accept"]["noul"] == 0.1
    assert doc["error"] is None
    assert "€500k" in first.read_text(encoding="utf-8")  # not €-escaped
    assert not list(log.folder.rglob("*.tmp"))


def test_text_and_missing_bodies(tmp_path):
    log = LogRoot(tmp_path).start_game(1, "rex", META, started=STARTED)
    text = read(log.record(exchange(response_body=b"Sure! not json"), 1, "offer"))
    assert text["response"]["body"] == "Sure! not json"
    failed = read(log.record(
        exchange(received=False, status=None, response_body=None,
                 error={"type": "timeout", "message": "jev timed out"}), 1, "offer"))
    assert failed["response"] is None
    assert failed["error"] == {"type": "timeout", "message": "jev timed out"}


def test_redaction(tmp_path):
    log = LogRoot(tmp_path, secrets=["ts-secret-123", "sk-ant-xyz"]).start_game(
        1, "rex", META, started=STARTED)
    path = log.record(exchange(
        request_headers={"Authorization": "Bearer ts-secret-123", "X-Api-Key": "sk-ant-xyz",
                         "anthropic-version": "2023-06-01"},
        response_headers={"Set-Cookie": "session=abc"},
        response_body=b'{"echo": "sk-ant-xyz"}',
    ), 1, "offer")
    text = path.read_text(encoding="utf-8")
    doc = json.loads(text)
    assert doc["request"]["headers"]["authorization"] == "[REDACTED]"
    assert doc["request"]["headers"]["x-api-key"] == "[REDACTED]"
    assert doc["request"]["headers"]["anthropic-version"] == "2023-06-01"
    assert doc["response"]["headers"]["set-cookie"] == "[REDACTED]"
    assert "ts-secret-123" not in text and "sk-ant-xyz" not in text


# --- scopes -----------------------------------------------------------------


def test_record_outside_scope_writes_nothing(tmp_path):
    LogRoot(tmp_path).start_game(1, "rex", META, started=STARTED)
    llmlog.record(exchange())
    assert not list(tmp_path.rglob("brain-jev"))
    assert not llmlog.active()


def test_scope_tags_retries(tmp_path):
    log = LogRoot(tmp_path).start_game(1, "rex", META, started=STARTED)
    with llmlog.scope(log, 1, "counter"):
        assert llmlog.active()
        for _ in range(3):
            llmlog.record(exchange("voice-claude"))
        llmlog.record(exchange("brain-jev"))
    names = sorted(p.name for p in (log.folder / "voice-claude").iterdir())
    assert names == ["001_turn01_counter.json", "002_turn01_counter_retry.json",
                     "003_turn01_counter_retry2.json"]
    assert [p.name for p in (log.folder / "brain-jev").iterdir()] == ["001_turn01_counter.json"]


def test_scope_reset_after_exception(tmp_path):
    log = LogRoot(tmp_path).start_game(1, "rex", META, started=STARTED)
    with pytest.raises(RuntimeError), llmlog.scope(log, 1, "offer"):
        raise RuntimeError("boom")
    assert not llmlog.active()


def test_scope_without_log_is_noop(tmp_path):
    with llmlog.scope(None, 1, "offer"):
        assert not llmlog.active()
        llmlog.record(exchange())
    assert list(tmp_path.iterdir()) == []


def test_record_http_from_httpx(tmp_path):
    log = LogRoot(tmp_path).start_game(1, "rex", META, started=STARTED)
    request = httpx.Request("POST", "http://localhost:11434/api/chat", json={"model": "m"})
    response = httpx.Response(200, json={"message": {"content": "{}"}}, request=request)
    with llmlog.scope(log, 3, "reject"):
        llmlog.record_http("voice-ollama", "m", request, STARTED, 5, response=response)
        llmlog.record_http("voice-ollama", "m", request, STARTED, 7,
                           error={"type": "connection", "message": "refused"})
    first, second = sorted((log.folder / "voice-ollama").iterdir())
    assert read(first)["request"]["body"] == {"model": "m"}
    assert read(first)["response"]["body"] == {"message": {"content": "{}"}}
    assert second.name == "002_turn03_reject_retry.json"
    assert read(second)["response"] is None


# --- failures ---------------------------------------------------------------


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
def test_unwritable_directory_warns_once(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        log = LogRoot(locked / "logs").start_game(1, "rex", META, started=STARTED)
        assert log.failed and "could not write" in log.warning
        with llmlog.scope(log, 1, "offer"):
            llmlog.record(exchange())  # silent no-op
        assert log.warning.count("could not write") == 1
    finally:
        locked.chmod(0o700)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
def test_write_failure_mid_game(tmp_path):
    log = LogRoot(tmp_path).start_game(1, "rex", META, started=STARTED)
    log.folder.chmod(0o500)
    try:
        assert log.record(exchange(), 1, "offer") is None
        assert log.failed
        warning = log.warning
        assert log.record(exchange(), 2, "offer") is None
        assert log.warning == warning
    finally:
        log.folder.chmod(0o700)


def test_unserialisable_body_fails_quietly(tmp_path):
    log = GameLog(tmp_path, 1)
    assert log.record(exchange(request_body={1, 2}), 1, "offer") is not None  # str() fallback
    assert log.record(exchange(started_at="not a datetime"), 1, "offer") is None
    assert log.failed
