import os

import pytest

from investor_game.brain.base import BrainError
from investor_game.brain.investor import InvestorBrain
from investor_game.brain.stub import StubBrainBackend
from investor_game.engine import Game
from investor_game.models import (
    GAME_ENDED_MESSAGE,
    MAX_TURNS,
    Action,
    BrainUnavailableError,
    GameOverError,
    Move,
    MoveError,
    Offer,
    Outcome,
    Pitch,
    PlayerView,
)
from investor_game.personas import get_persona
from investor_game.session import Session
from investor_game.voice.guarded import GuardedVoice
from investor_game.voice.stub import StubVoiceBackend

PITCH = Pitch(name="GreenCharge", sector="EV charging", description="Chargers",
              valuation=2_000_000, ask=500_000)


class FlakyBrain:
    """Fails the first ``failures`` calls, then behaves like the stub."""

    name = "flaky"

    def __init__(self, failures=1):
        self.failures = failures
        self.stub = StubBrainBackend()

    def ask(self, state, questions):
        if self.failures:
            self.failures -= 1
            raise BrainError("down")
        return self.stub.ask(state, questions)


def start(persona_id="henry", pitch=PITCH, brain=None):
    return Game.start(1, pitch, persona_id, InvestorBrain(brain or StubBrainBackend()),
                      GuardedVoice(StubVoiceBackend()))


def test_opening_within_budget():
    game = start("henry")
    henry = get_persona("henry")
    view = game.view()
    assert view.investor_offer == Offer(amount=500_000, equity=henry.limits.max_equity)
    assert view.turn == 0
    assert view.transcript[0].role == "investor"
    assert "€500k" in view.transcript[0].text
    assert {o.kind for o in view.options} >= {"accept", "walk_away"}


def test_opening_above_budget():
    pitch = PITCH.model_copy(update={"ask": 3_000_000, "valuation": 9_000_000})
    game = start("rex", pitch)
    assert game.view().investor_offer.amount == get_persona("rex").limits.budget


def test_greedy_opens_higher_than_generous():
    assert start("rex").view().investor_offer.equity > start("grace").view().investor_offer.equity


def test_counter_turn_updates_state():
    game = start("henry")
    view = game.play(Move.make_offer(500_000, 180))
    assert view.turn == 1
    assert view.player_offer == Offer(amount=500_000, equity=180)
    assert [m.role for m in view.transcript] == ["investor", "player", "investor"]
    assert view.insights[-1].backend == "stub"
    assert view.insights[-1].answers


def test_brain_failure_leaves_state_unchanged():
    game = start("henry", brain=FlakyBrain(failures=1))
    before = game.state
    with pytest.raises(BrainUnavailableError, match="Your move wasn't used"):
        game.play(Move.make_offer(500_000, 180))
    assert game.state == before
    assert game.play(Move.make_offer(500_000, 180)).turn == 1


def test_invalid_move_does_not_use_turn():
    game = start()
    with pytest.raises(MoveError):
        game.play(Move.make_offer(500_000, 0))
    assert game.view().turn == 0


def test_player_accepts():
    game = start("henry")
    offer = game.view().investor_offer
    view = game.play(Move.accept())
    assert view.outcome is Outcome.DEAL
    assert view.final_offer == offer
    assert view.options == ()
    assert view.insights[-1].backend == "rules"


def test_player_walks_away():
    view = start().play(Move.walk_away())
    assert view.outcome is Outcome.PLAYER_WALKED


def test_investor_walks_after_insults():
    game = start("max")
    view = game.play(Move.message("You idiot."))
    assert view.outcome is Outcome.INVESTOR_WALKED
    assert view.insights[-1].action is Action.WALK_AWAY


def test_investor_accepts_matching_offer():
    game = start("henry")
    offer = game.view().investor_offer
    view = game.play(Move.make_offer(offer.amount, offer.equity))
    assert view.outcome is Outcome.DEAL
    assert view.final_offer == offer


def test_out_of_turns():
    game = start("henry")
    for _ in range(MAX_TURNS):
        view = game.play(Move.message("Tell me more about how you work with founders?"))
        if view.ended:
            break
    assert view.outcome in (Outcome.OUT_OF_TURNS, Outcome.INVESTOR_WALKED)
    # Henry is patient: 15 polite questions (0.5 stalling cost each) still leave patience.
    assert view.outcome is Outcome.OUT_OF_TURNS
    assert view.turn == MAX_TURNS
    assert view.transcript[-1].action == "out_of_turns"


def test_move_after_end_refused():
    game = start()
    game.play(Move.accept())
    before = game.state
    with pytest.raises(GameOverError, match=GAME_ENDED_MESSAGE):
        game.play(Move.make_offer(500_000, 200))
    assert game.state == before


def test_view_is_player_safe():
    view = start().view()
    assert isinstance(view, PlayerView)
    dumped = view.model_dump()
    assert not {"interest", "patience", "budget", "min_equity", "max_equity"} & set(dumped)
    assert view.patience_hint == "Listening patiently"
    assert view.interest_hint == "Medium"


def test_session_lists_newest_first_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session = Session(InvestorBrain(StubBrainBackend()), GuardedVoice(StubVoiceBackend()))
    first = session.new_game(PITCH, "rex")
    assert isinstance(first, PlayerView)
    session.play(first.id, Move.walk_away())
    second = session.new_game(PITCH, "grace")
    assert isinstance(session.play(second.id, Move.accept()), PlayerView)
    views = session.games()
    assert [v.investor.id for v in views] == ["grace", "rex"]
    assert session.get(first.id).outcome is Outcome.PLAYER_WALKED
    assert os.listdir(tmp_path) == []


def test_cli_only_touches_player_views():
    """The CLI package never imports the engine's state or persona secrets."""
    import re
    from pathlib import Path

    cli = Path(__file__).parents[1] / "src" / "investor_game" / "cli"
    source = "\n".join(p.read_text() for p in cli.glob("*.py"))
    assert source, "cli package should exist"
    forbidden = r"GameState|\bengine\b|get_persona|\.limits\b|\.behaviour\b|\.state\b"
    assert not re.search(forbidden, source)
