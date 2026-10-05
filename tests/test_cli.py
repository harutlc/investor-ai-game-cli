import pytest
from rich.console import Console
from typer.testing import CliRunner

from investor_game.brain.base import BrainError
from investor_game.brain.investor import InvestorBrain
from investor_game.brain.stub import StubBrainBackend
from investor_game.cli import app as app_module
from investor_game.cli import render
from investor_game.cli.screens import App, ScriptedTerminal
from investor_game.config import ConfigError, Settings
from investor_game.models import MAX_TURNS, Message, Offer, Outcome, Pitch, PlayerView
from investor_game.personas import PERSONAS_BY_ID
from investor_game.session import Session
from investor_game.voice.guarded import GuardedVoice
from investor_game.voice.stub import StubVoiceBackend

PITCH = Pitch(name="GreenCharge", sector="EV charging", description="Chargers",
              valuation=2_000_000, ask=500_000)
DEFAULTS = ["", "", "", "", ""]  # name, sector, description, valuation, ask


def make_view(**overrides) -> PlayerView:
    values = dict(
        id=1, investor=PERSONAS_BY_ID["max"].profile, pitch=PITCH,
        investor_offer=Offer(amount=550_000, equity=240),
        player_offer=Offer(amount=550_000, equity=180), turn=3, max_turns=MAX_TURNS,
        interest_hint="Medium", patience_hint="Getting restless",
        transcript=(Message(role="investor", text="Hurry up."),), insights=(), options=(),
        outcome=None, final_offer=None,
    )
    values.update(overrides)
    return PlayerView(**values)


def text_of(renderable) -> str:
    console = Console(record=True, width=120, force_terminal=False)
    console.print(renderable)
    return console.export_text()


def run_app(answers, brain_backend=None):
    session = Session(InvestorBrain(brain_backend or StubBrainBackend()),
                      GuardedVoice(StubVoiceBackend()))
    term = ScriptedTerminal(answers)
    try:
        App(term, session, "brain: stub · voice: stub").run()
    except EOFError:
        pass
    return term.console.export_text(), session


# --- config -----------------------------------------------------------------


def test_defaults_to_stub_without_keys():
    settings = Settings.build(env={})
    assert (settings.brain, settings.voice) == ("stub", "stub")
    assert settings.missing() == []


def test_real_backends_when_keys_set():
    settings = Settings.build(env={"TYPESAFE_API_KEY": "t", "ANTHROPIC_API_KEY": "a"})
    assert (settings.brain, settings.voice) == ("jev", "claude")
    assert Settings.build(offline=True, env={"TYPESAFE_API_KEY": "t"}).brain == "stub"


def test_missing_keys_named():
    assert Settings.build("jev", "claude", env={}).missing() == [
        "TYPESAFE_API_KEY is required for the jev brain.",
        "ANTHROPIC_API_KEY is required for the claude voice.",
    ]
    assert Settings.build("laya", "ollama", env={}).missing() == []


def test_unknown_backend():
    with pytest.raises(ConfigError, match="Unknown brain"):
        Settings.build("gpt", env={})


# --- command ----------------------------------------------------------------

runner = CliRunner()


def test_version():
    result = runner.invoke(app_module.app, ["--version"])
    assert result.exit_code == 0
    assert "investor-game 0.1.0" in result.output


def test_missing_key_exits_non_zero(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(app_module.app, ["--voice", "claude"])
    assert result.exit_code != 0
    assert "ANTHROPIC_API_KEY" in result.output


def test_ctrl_c_exits_130(monkeypatch):
    def interrupted(self):
        raise KeyboardInterrupt

    monkeypatch.setattr(App, "run", interrupted)
    result = runner.invoke(app_module.app, ["--offline"])
    assert result.exit_code == 130
    assert "Goodbye" in result.output
    assert "Traceback" not in result.output


def test_unexpected_error_is_plain(monkeypatch):
    def broken(self):
        raise RuntimeError("secret internal detail https://api.example")

    monkeypatch.setattr(App, "run", broken)
    result = runner.invoke(app_module.app, ["--offline"])
    assert result.exit_code == 1
    assert "Something went wrong" in result.output
    assert "secret internal detail" not in result.output


# --- setup ------------------------------------------------------------------


def test_setup_defaults_give_greencharge():
    output, session = run_app(["1", *DEFAULTS, "y"])
    assert "Setup → Negotiation → Debrief" in output
    assert "20.0% equity" in output
    view = session.games()[0]
    assert (view.pitch.name, view.pitch.sector) == ("GreenCharge", "EV charging")
    assert (view.pitch.valuation, view.pitch.ask) == (2_000_000, 500_000)
    assert view.investor.id == "rex"


def test_setup_invalid_valuation_reprompts():
    output, session = run_app(["4", "", "", "", "lots", "3M", "", "y"])
    assert "Valuation must be a whole number of euros above zero" in output
    assert session.games()[0].pitch.valuation == 3_000_000


def test_setup_lists_all_investors():
    output, _ = run_app(["q"])
    for persona in PERSONAS_BY_ID.values():
        assert persona.name in output


# --- negotiation ------------------------------------------------------------


def test_deal_panel_gap():
    output = text_of(render.deal_panel(make_view()))
    assert "€550k for 24.0%" in output
    assert "€550k for 18.0%" in output
    assert "6.0 points" in output
    assert "Turn 3 of 15" in output


def test_mood_panel_hints_only():
    output = text_of(render.mood_panel(make_view()))
    assert "Interest: Medium" in output
    assert "Patience: Getting restless" in output
    assert "Hints only. The real numbers stay hidden." in output


def test_offer_preview_and_send():
    output, session = run_app(["4", *DEFAULTS, "y", "o", "500k", "15", "y"])
    assert "€500k for 15.0% → €3.33M post-money, €2.83M pre-money" in output
    view = session.games()[0]
    assert view.turn == 1
    assert view.player_offer == Offer(amount=500_000, equity=150)


def test_offer_declined_is_not_sent():
    _, session = run_app(["4", *DEFAULTS, "y", "o", "500k", "15", "n"])
    assert session.games()[0].turn == 0


def test_pick_walk_away_option():
    output, session = run_app(["4", *DEFAULTS, "y", "4", "5"])
    assert session.games()[0].outcome is Outcome.PLAYER_WALKED
    assert "No deal — You walked away" in output


def test_free_message():
    _, session = run_app(["4", *DEFAULTS, "y", "m", "Lovely weather today!"])
    view = session.games()[0]
    assert view.turn == 1
    assert view.transcript[1].text == "Lovely weather today!"


def test_prompts_are_not_eaten_as_markup():
    from investor_game.cli.screens import Terminal

    console = Console(record=True, width=120, force_terminal=False)
    console.input = lambda prompt: console.print(prompt, end="") or "y"
    Terminal(console).ask("Walk away from this deal? [y/N]")
    assert "[y/N]" in console.export_text()


def test_quit_confirms_walk_away():
    _, session = run_app(["4", *DEFAULTS, "y", "q", "n", "q", "y", "5"])
    assert session.games()[0].outcome is Outcome.PLAYER_WALKED


def test_insights_after_two_turns():
    output, session = run_app(["4", *DEFAULTS, "y", "o", "500k", "15", "y",
                               "m", "Please, can you do better?", "i"])
    assert session.games()[0].turn == 2
    assert "Turn 1: Offer €500k for 15%" in output
    assert "Turn 2: Please, can you do better?" in output
    assert "Would the investor accept this offer?" in output
    assert "Brain: stub" in output
    assert " ms)" in output


# --- debrief ----------------------------------------------------------------


def test_deal_debrief():
    view = make_view(outcome=Outcome.DEAL, final_offer=Offer(amount=500_000, equity=220))
    output = text_of(render.debrief(view))
    assert "Deal closed" in output
    assert "€2.27M" in output and "€1.77M" in output
    assert "−€227k, −11.4%" in output
    assert "Turns used" in output


def test_no_deal_debrief():
    output = text_of(render.debrief(make_view(outcome=Outcome.INVESTOR_WALKED)))
    assert "No deal — Max Brandt walked away" in output
    assert "Where it stopped" in output
    assert "€550k for 24.0%" in output and "€550k for 18.0%" in output


def test_play_again_and_your_games():
    answers = ["1", *DEFAULTS, "y", "4",  # walk away from Rex
               "3",  # play again
               "2", *DEFAULTS, "y", "3",  # accept Grace's offer (option 3)
               "4", "2", "5"]  # your games, open the older one, quit
    output, session = run_app(answers)
    views = session.games()
    assert [v.investor.id for v in views] == ["grace", "rex"]
    assert views[0].outcome is Outcome.DEAL
    assert "Your games (this run)" in output


# --- errors -----------------------------------------------------------------


class FailOnce:
    name = "flaky"

    def __init__(self):
        self.failed = False
        self.stub = StubBrainBackend()

    def ask(self, state, questions):
        if not self.failed:
            self.failed = True
            raise BrainError("connection refused at https://internal")
        return self.stub.ask(state, questions)


def test_brain_failure_retry():
    output, session = run_app(["4", *DEFAULTS, "y", "o", "500k", "15", "y",
                               "o", "500k", "15", "y"], brain_backend=FailOnce())
    assert "Your move wasn't used" in output
    assert "https://internal" not in output
    assert session.games()[0].turn == 1
