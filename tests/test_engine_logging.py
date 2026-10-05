import json
import os

import pytest

from investor_game import llmlog
from investor_game.brain.base import BrainError
from investor_game.brain.investor import InvestorBrain
from investor_game.brain.stub import StubBrainBackend
from investor_game.llmlog import Exchange, LogRoot
from investor_game.models import BrainUnavailableError, Move, Pitch
from investor_game.session import Session
from investor_game.voice.guarded import GuardedVoice
from investor_game.voice.stub import StubVoiceBackend

PITCH = Pitch(name="GreenCharge", sector="EV charging", description="Chargers",
              valuation=2_000_000, ask=500_000)
BACKENDS = {"brain": {"backend": "recording", "model": "rec-1"},
            "voice": {"backend": "recording", "model": "rec-2"}}


def fake_exchange(service):
    return Exchange(service=service, model="rec", method="POST", url="http://fake/",
                    request_headers={}, request_body=b'{"q": 1}', started_at=llmlog.now(),
                    duration_ms=1, received=True, status=200, response_body=b'{"a": 1}')


class RecordingBrain:
    """Stub answers, but records a fake exchange like a real backend would."""

    name = "recording"

    def __init__(self, fail=False):
        self.stub = StubBrainBackend()
        self.fail = fail

    def ask(self, state, questions):
        llmlog.record(fake_exchange("brain-rec"))
        if self.fail:
            raise BrainError("down")
        return self.stub.ask(state, questions)


class RecordingVoice:
    name = "recording"

    def __init__(self):
        self.stub = StubVoiceBackend()

    def compose(self, request, correction=None):
        llmlog.record(fake_exchange("voice-rec"))
        return self.stub.compose(request, correction)


def session(tmp_path, brain=None, log=True):
    root = LogRoot(tmp_path / "logs") if log else None
    return Session(InvestorBrain(brain or RecordingBrain()), GuardedVoice(RecordingVoice()),
                   log_root=root, backends=BACKENDS)


def names(folder):
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_calls_carry_turn_and_purpose(tmp_path):
    s = session(tmp_path)
    view = s.new_game(PITCH, "henry")
    folder = tmp_path / "logs" / os.path.basename(view.log_folder)
    s.play(view.id, Move.make_offer(500_000, 180))
    s.play(view.id, Move.message("Please, can you do better?"))
    s.play(view.id, Move.accept())  # no brain call; voice closes the deal
    assert names(folder / "brain-rec") == ["001_turn01_offer.json", "002_turn02_message.json"]
    voice = names(folder / "voice-rec")
    assert voice[0] == "001_turn00_open.json"
    assert voice[1].startswith("002_turn01_")
    assert voice[3] == "004_turn03_player_accepted.json"
    game = json.loads((folder / "game.json").read_text(encoding="utf-8"))
    assert game["persona"] == {"id": "henry", "name": "Henry Lowe"}
    assert game["pitch"]["name"] == "GreenCharge"
    assert game["brain"] == {"backend": "recording", "model": "rec-1"}


def test_each_game_gets_its_own_folder(tmp_path):
    s = session(tmp_path)
    first = s.new_game(PITCH, "rex")
    s.play(first.id, Move.walk_away())
    second = s.new_game(PITCH, "grace")
    folders = sorted(p.name for p in (tmp_path / "logs").iterdir())
    assert len(folders) == 2
    assert folders[0].endswith("_g1_rex") and folders[1].endswith("_g2_grace")
    assert second.log_folder.endswith("_g2_grace")


def test_no_log_root_records_nothing(tmp_path):
    s = session(tmp_path, log=False)
    view = s.new_game(PITCH, "henry")
    s.play(view.id, Move.make_offer(500_000, 180))
    assert view.log_folder is None and view.log_warning is None
    assert not (tmp_path / "logs").exists()


def test_brain_failure_logged_but_turn_not_applied(tmp_path):
    s = session(tmp_path, brain=RecordingBrain(fail=True))
    view = s.new_game(PITCH, "henry")
    game = s._game(view.id)
    before = game.state
    with pytest.raises(BrainUnavailableError):
        s.play(view.id, Move.make_offer(500_000, 180))
    assert game.state == before
    folder = tmp_path / "logs" / os.path.basename(view.log_folder)
    assert names(folder / "brain-rec") == ["001_turn01_offer.json"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
def test_log_warning_on_view(tmp_path):
    s = session(tmp_path)
    view = s.new_game(PITCH, "henry")
    assert view.log_warning is None
    folder = tmp_path / "logs" / os.path.basename(view.log_folder)
    folder.chmod(0o500)
    try:
        view = s.play(view.id, Move.make_offer(500_000, 180))
        assert view.turn == 1  # the turn still happened
        assert "LLM logging stopped" in view.log_warning
    finally:
        folder.chmod(0o700)
