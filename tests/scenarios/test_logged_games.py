"""Full games with LLM call logging enabled."""

import json

import httpx
import respx

from investor_game.brain.investor import InvestorBrain
from investor_game.brain.stub import StubBrainBackend
from investor_game.cli.screens import App, ScriptedTerminal
from investor_game.llmlog import LogRoot
from investor_game.session import Session
from investor_game.voice.guarded import GuardedVoice
from investor_game.voice.ollama import OllamaVoiceBackend
from investor_game.voice.stub import StubVoiceBackend

DEFAULTS = ["", "", "", "", ""]


def play(voice, log_dir, answers):
    session = Session(InvestorBrain(StubBrainBackend()), GuardedVoice(voice),
                      log_root=LogRoot(log_dir), backends={})
    term = ScriptedTerminal(answers)
    try:
        App(term, session).run()
    except EOFError:
        pass
    return session


def test_offline_game_folder_has_only_game_json(tmp_path):
    play(StubVoiceBackend(), tmp_path, ["4", *DEFAULTS, "y", "o", "500k", "15", "y", "3", "5"])
    [folder] = tmp_path.iterdir()
    assert [p.name for p in folder.iterdir()] == ["game.json"]


def test_two_games_two_folders(tmp_path):
    play(StubVoiceBackend(), tmp_path,
         ["1", *DEFAULTS, "y", "4", "3", "2", *DEFAULTS, "y", "3", "5"])
    folders = sorted(p.name for p in tmp_path.iterdir())
    assert len(folders) == 2
    assert folders[0].endswith("_g1_rex") and folders[1].endswith("_g2_grace")


@respx.mock
def test_ollama_game_logs_every_call(tmp_path):
    def reply(request):
        body = json.loads(request.content)
        system = body["messages"][0]["content"]
        # Echo the exact terms the system prompt asks for, so the guard passes.
        marker = "The exact terms to state are "
        terms = system.split(marker)[1].split(". Write")[0] if marker in system else "Noted"
        return httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps(
            {"reply": f"Mm. {terms}.", "options": []})}})

    respx.post("http://localhost:11434/api/chat").mock(side_effect=reply)
    session = play(OllamaVoiceBackend(), tmp_path,
                   ["4", *DEFAULTS, "y", "o", "500k", "15", "y",
                    "m", "Please, we have traction. Can you do better?", "q", "y", "5"])
    view = session.games()[0]
    folder = tmp_path / view.log_folder.rsplit("/", 1)[-1]
    names = sorted(p.name for p in (folder / "voice-ollama").iterdir())
    assert names[0] == "001_turn00_open.json"
    turns = {name.split("_")[1] for name in names}
    assert turns == {"turn00", "turn01", "turn02", "turn03"}
    assert not (folder / "brain-stub").exists()
    opening = json.loads((folder / "voice-ollama" / names[0]).read_text(encoding="utf-8"))
    assert opening["request"]["body"]["model"] == "llama3.1"
    assert opening["response"]["status"] == 200
