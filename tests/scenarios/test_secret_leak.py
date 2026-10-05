"""No secret limit or numeric mood ever reaches the player, in any screen of a full game.

Each persona gets sentinel limits (an odd budget and minimum equity) so a value found in
the output can only be a leak, not a coincidence with an offer or a valuation.
"""

import json
import re

import pytest

from investor_game.brain.investor import InvestorBrain
from investor_game.brain.stub import StubBrainBackend
from investor_game.cli.screens import App, ScriptedTerminal
from investor_game.personas import PERSONAS, PERSONAS_BY_ID
from investor_game.policy import PATIENCE_HINTS
from investor_game.session import Session
from investor_game.voice.guarded import GuardedVoice
from investor_game.voice.stub import StubVoiceBackend

SENTINEL_BUDGET = 1_234_567
SENTINEL_MIN_EQUITY = 137  # 13.7%
BUDGET_FORMS = ("1,234,567", "1234567", "€1.23M", "1.23M", "1.234567")
MIN_FORMS = ("13.7%", "13.7 ", "13.7\n")


class RoutedTerminal(ScriptedTerminal):
    """Answers each kind of prompt from its own queue, so the script survives early endings."""

    def __init__(self, routes: dict[str, list[str]]):
        super().__init__([])
        self.routes = routes

    def ask(self, prompt, default=None):
        for prefix, answers in self.routes.items():
            if prompt.startswith(prefix):
                if not answers:
                    raise EOFError
                self.answers = [answers.pop(0)]
                return super().ask(prompt, default)
        self.answers = [""]  # accept defaults (pitch fields, amounts)
        return super().ask(prompt, default)


def routes(persona_index: int, max_equity: int) -> dict[str, list[str]]:
    """Offers stay above the minimum; walk away if still talking; then visit every screen."""
    high, mid = (max_equity - 20) / 10, (max_equity - 30) / 10
    return {
        "Choose an investor": [str(persona_index), "q"],
        "Start negotiating": ["y"],
        "Your move": ["o", "m", "i", "h", "q"],
        "Equity": [f"{high}"],
        "Send this offer": ["y"],
        "Your message": [f"Please, we have strong traction. €500k for {mid}%?"],
        "Walk away from this deal": ["y"],
        "Choose": ["1", "2", "4", "5"],
        "Open a game": ["1"],
    }


@pytest.mark.parametrize(
    "index,persona", list(enumerate(PERSONAS, 1)), ids=[p.id for p in PERSONAS]
)
def test_no_secrets_in_full_game(monkeypatch, index, persona):
    patched = persona.model_copy(update={"limits": persona.limits.model_copy(update={
        "budget": SENTINEL_BUDGET, "min_equity": SENTINEL_MIN_EQUITY})})
    monkeypatch.setitem(PERSONAS_BY_ID, persona.id, patched)

    session = Session(InvestorBrain(StubBrainBackend()), GuardedVoice(StubVoiceBackend()))
    term = RoutedTerminal(routes(index, persona.limits.max_equity))
    try:
        App(term, session, "brain: stub · voice: stub").run()
    except EOFError:
        pass
    output = term.console.export_text()
    views = session.games()
    assert views and views[0].ended, "the scripted game should have finished"
    for screen in ("Your options", "Turn 1:", "Your games (this run)", "Turns used"):
        assert screen in output, f"the script should have shown {screen!r}"
    serialised = json.dumps([v.model_dump(mode="json") for v in views])

    for blob in (output, serialised):
        for form in BUDGET_FORMS + MIN_FORMS:
            assert form not in blob, f"secret value {form!r} leaked"
        assert not re.search(r"(?i)\b(interest|patience)\b[^\n]*\d", blob)
        assert not re.search(r"(?i)\b(budget|min(imum)? equity|max(imum)? equity)\b", blob)

    for view in views:
        assert view.interest_hint in ("Low", "Medium", "High")
        assert view.patience_hint in PATIENCE_HINTS
    view_fields = set(json.loads(serialised)[0])
    assert not view_fields & {"budget", "min_equity", "max_equity", "interest", "patience"}
