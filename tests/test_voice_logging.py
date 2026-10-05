import json

import anthropic
import httpx
import httpx2
import pytest
import respx
from anthropic import DefaultHttpxClient

from investor_game import llmlog
from investor_game.llmlog import LogRoot
from investor_game.models import Action
from investor_game.voice.base import VoiceError
from investor_game.voice.claude import ClaudeVoiceBackend
from investor_game.voice.guarded import GuardedVoice
from investor_game.voice.ollama import OllamaVoiceBackend
from tests.test_voice import FakeClaude, claude_json, request

OLLAMA = "http://localhost:11434/api/chat"
API_KEY = "sk-ant-secret-xyz"


@pytest.fixture
def game_log(tmp_path):
    return LogRoot(tmp_path, secrets=[API_KEY]).start_game(1, "rex", {})


def files(game_log, service):
    folder = game_log.folder / service
    return sorted(folder.iterdir()) if folder.exists() else []


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def ollama_reply(text):
    return httpx.Response(200, json={"model": "llama3.1", "message": {"role": "assistant",
                                                                       "content": text}})


# --- Ollama -----------------------------------------------------------------


@respx.mock
def test_ollama_success_logged(game_log):
    route = respx.post(OLLAMA).mock(return_value=ollama_reply(claude_json("€550k for 24%.")))
    with llmlog.scope(game_log, 1, "counter"):
        GuardedVoice(OllamaVoiceBackend()).render(request())
    [path] = files(game_log, "voice-ollama")
    assert path.name == "001_turn01_counter.json"
    doc = load(path)
    assert doc["request"]["body"] == json.loads(route.calls.last.request.content)
    assert doc["request"]["body"]["messages"][0]["role"] == "system"
    assert doc["response"]["body"]["message"]["content"] == claude_json("€550k for 24%.")
    assert "€550k" in path.read_text(encoding="utf-8")


@respx.mock
def test_ollama_guard_retry_logged(game_log):
    respx.post(OLLAMA).mock(side_effect=[ollama_reply(claude_json("€900k for 5%.")),
                                         ollama_reply(claude_json("€550k for 24%."))])
    with llmlog.scope(game_log, 3, "counter"):
        result = GuardedVoice(OllamaVoiceBackend()).render(request())
    assert result.note == "corrected after retry"
    first, second = files(game_log, "voice-ollama")
    assert second.name == "002_turn03_counter_retry.json"
    assert "CORRECTION" in load(second)["request"]["body"]["messages"][1]["content"]


@respx.mock
def test_ollama_non_json_body_stored_as_text(game_log):
    respx.post(OLLAMA).mock(return_value=httpx.Response(200, text="<html>proxy error</html>"))
    with llmlog.scope(game_log, 1, "counter"):
        GuardedVoice(OllamaVoiceBackend()).render(request())
    doc = load(files(game_log, "voice-ollama")[0])
    assert doc["response"]["body"] == "<html>proxy error</html>"


@respx.mock
def test_ollama_http_error_and_connection_error(game_log):
    respx.post(OLLAMA).mock(side_effect=[httpx.Response(500, json={"error": "model not found"}),
                                         httpx.ConnectError("refused")])
    with llmlog.scope(game_log, 1, "counter"):
        for _ in range(2):
            with pytest.raises(VoiceError):
                OllamaVoiceBackend().compose(request())
    status, connection = (load(p) for p in files(game_log, "voice-ollama"))
    assert status["response"]["status"] == 500
    assert status["error"]["type"] == "http_status"
    assert status["response"]["body"] == {"error": "model not found"}
    assert connection["response"] is None and connection["error"]["type"] == "connection"


# --- Claude (fake client) ---------------------------------------------------


def test_claude_fake_logged(game_log):
    fake = FakeClaude(claude_json("€550k for 24%."))
    with llmlog.scope(game_log, 0, "open"):
        ClaudeVoiceBackend(client=fake).compose(request(Action.OPEN, player=None))
    [path] = files(game_log, "voice-claude")
    assert path.name == "001_turn00_open.json"
    doc = load(path)
    assert doc["request"]["body"]["model"] == "claude-opus-5-5"
    assert doc["request"]["headers"]["x-api-key"] == "[REDACTED]"
    assert doc["response"]["body"]["content"][0]["text"] == claude_json("€550k for 24%.")


def test_claude_refusal_logged(game_log):
    with llmlog.scope(game_log, 1, "counter"), pytest.raises(VoiceError):
        ClaudeVoiceBackend(client=FakeClaude(None, stop_reason="refusal")).compose(request())
    doc = load(files(game_log, "voice-claude")[0])
    assert doc["error"]["type"] == "refused"
    assert doc["response"]["status"] == 200


# --- Claude (real SDK over a mock transport) --------------------------------


def real_client(handler):
    return anthropic.Anthropic(
        api_key=API_KEY, max_retries=0,
        http_client=DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )


def message(text):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 5}}


def test_claude_real_sdk_exact_bodies(game_log):
    sent = []

    def handler(http_request):
        sent.append(json.loads(http_request.content))
        return httpx2.Response(200, json=message(claude_json("€550k for 24%.")))

    backend = ClaudeVoiceBackend(client=real_client(handler))
    with llmlog.scope(game_log, 1, "counter"):
        draft = backend.compose(request())
    assert draft.reply == "€550k for 24%."
    [path] = files(game_log, "voice-claude")
    text = path.read_text(encoding="utf-8")
    doc = json.loads(text)
    assert doc["request"]["body"] == sent[0]
    assert doc["request"]["body"]["fallbacks"] == "default"
    assert doc["request"]["url"].startswith("https://api.anthropic.com/v1/messages")
    assert doc["response"]["body"] == message(claude_json("€550k for 24%."))
    assert API_KEY not in text
    assert doc["request"]["headers"]["x-api-key"] == "[REDACTED]"


def test_claude_real_sdk_status_error_logged(game_log):
    def handler(http_request):
        return httpx2.Response(529, json={"type": "error", "error": {"type": "overloaded_error",
                                                                     "message": "Overloaded"}})

    with llmlog.scope(game_log, 2, "reject"), pytest.raises(VoiceError, match="529"):
        ClaudeVoiceBackend(client=real_client(handler)).compose(request())
    doc = load(files(game_log, "voice-claude")[0])
    assert doc["response"]["status"] == 529
    assert doc["error"]["type"] == "http_status"
    assert doc["request"]["body"]["model"] == "claude-opus-5-5"


def test_claude_real_sdk_connection_error_logged(game_log):
    def handler(http_request):
        raise httpx2.ConnectError("refused", request=http_request)

    with llmlog.scope(game_log, 1, "counter"), pytest.raises(VoiceError):
        ClaudeVoiceBackend(client=real_client(handler)).compose(request())
    doc = load(files(game_log, "voice-claude")[0])
    assert doc["response"] is None
    assert doc["error"]["type"] == "connection"
    assert doc["request"]["body"]["model"] == "claude-opus-5-5"
