import json

import httpx
import pytest
import respx

from investor_game import llmlog
from investor_game.brain.base import BrainError
from investor_game.brain.investor import InvestorBrain
from investor_game.brain.systemone import SystemOneBackend
from investor_game.llmlog import LogRoot
from investor_game.models import Move
from tests.test_brain import JEV_URL, context, jev_responder


@pytest.fixture
def game_log(tmp_path):
    return LogRoot(tmp_path, secrets=["ts-secret-123"]).start_game(1, "rex", {})


def files(game_log, service):
    folder = game_log.folder / service
    return sorted(folder.iterdir()) if folder.exists() else []


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


@respx.mock
def test_jev_success_logged(game_log):
    route = respx.post(JEV_URL).mock(side_effect=jev_responder)
    with llmlog.scope(game_log, 1, "offer"):
        InvestorBrain(SystemOneBackend.jev("ts-secret-123")).judge(
            context(), Move.make_offer(500_000, 200))
    [path] = files(game_log, "brain-jev")
    assert path.name == "001_turn01_offer.json"
    doc = load(path)
    sent = json.loads(route.calls.last.request.content)
    received = route.calls.last.response.json()
    assert doc["request"]["body"] == sent
    assert set(doc["request"]["body"]) == {"model", "state", "questions"}
    assert doc["request"]["url"] == JEV_URL
    assert doc["response"]["body"] == received
    assert doc["response"]["status"] == 200
    assert doc["model"] == "jev-latest"
    assert doc["error"] is None
    text = path.read_text(encoding="utf-8")
    assert "ts-secret-123" not in text
    assert doc["request"]["headers"]["authorization"] == "[REDACTED]"


@respx.mock
def test_timeout_logged_without_response(game_log):
    respx.post(JEV_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(BrainError), llmlog.scope(game_log, 2, "message"):
        InvestorBrain(SystemOneBackend.jev("k")).judge(context(), Move.message("hello there"))
    [path] = files(game_log, "brain-jev")
    doc = load(path)
    assert path.name == "001_turn02_message.json"
    assert doc["response"] is None
    assert doc["error"]["type"] == "timeout"
    assert doc["request"]["body"]["state"]["player_move"]["text"] == "hello there"


@respx.mock
def test_connection_error_logged(game_log):
    respx.post(JEV_URL).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(BrainError), llmlog.scope(game_log, 1, "offer"):
        InvestorBrain(SystemOneBackend.jev("k")).judge(context(), Move.make_offer(500_000, 200))
    assert load(files(game_log, "brain-jev")[0])["error"]["type"] == "connection"


@respx.mock
def test_retry_gets_its_own_file(game_log, monkeypatch):
    monkeypatch.setattr("investor_game.brain.systemone.RETRY_BACKOFF", 0.01)
    respx.post(JEV_URL).mock(side_effect=[httpx.Response(429, json={"error": "slow down"}),
                                          jev_responder])
    with llmlog.scope(game_log, 1, "offer"):
        InvestorBrain(SystemOneBackend.jev("k")).judge(context(), Move.make_offer(500_000, 200))
    first, second = files(game_log, "brain-jev")
    assert (first.name, second.name) == ("001_turn01_offer.json", "002_turn01_offer_retry.json")
    assert load(first)["response"]["status"] == 429
    assert load(first)["error"]["type"] == "http_status"
    assert load(second)["response"]["status"] == 200


@respx.mock
def test_laya_logged_in_its_own_folder(game_log):
    respx.post("http://localhost:8000/v1/systemone").mock(side_effect=jev_responder)
    with llmlog.scope(game_log, 1, "offer"):
        InvestorBrain(SystemOneBackend.laya()).judge(context(), Move.make_offer(500_000, 200))
    [path] = files(game_log, "brain-laya")
    assert load(path)["model"] == "laya"
    assert not files(game_log, "brain-jev")


@respx.mock
def test_no_scope_no_files(tmp_path):
    respx.post(JEV_URL).mock(side_effect=jev_responder)
    InvestorBrain(SystemOneBackend.jev("k")).judge(context(), Move.make_offer(500_000, 200))
    assert list(tmp_path.iterdir()) == []
