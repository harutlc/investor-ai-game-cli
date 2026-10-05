import re

import pytest

from investor_game.personas import PERSONAS, TEMPLATE_KEYS, fill_template, get_persona


def test_six_personas_in_order():
    assert [p.id for p in PERSONAS] == ["rex", "grace", "max", "henry", "mira", "amara"]
    for persona in PERSONAS:
        profile = persona.profile
        assert profile.name and profile.emoji and profile.description
        assert len(profile.traits) == 2


def test_public_profile_excludes_secrets():
    for persona in PERSONAS:
        dumped = persona.profile.model_dump()
        assert set(dumped) == {"id", "name", "emoji", "description", "traits"}


@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p.id)
def test_limits_consistent(persona):
    limits = persona.limits
    assert limits.budget > 0
    assert 0 < limits.min_equity < limits.max_equity < 1000


def test_behaviour_ordering():
    rex, grace, mx, henry = (get_persona(i) for i in ("rex", "grace", "max", "henry"))
    assert rex.limits.max_equity > grace.limits.max_equity
    assert rex.behaviour.concession_rate < grace.behaviour.concession_rate
    patience = {p.id: p.behaviour.start_patience for p in PERSONAS}
    insult = {p.id: p.behaviour.insult_cost for p in PERSONAS}
    assert min(patience, key=patience.get) == "max"
    assert sorted(patience.values())[0] < sorted(patience.values())[1]
    assert max(insult, key=insult.get) == "max"
    assert max(patience, key=patience.get) == "henry"
    assert henry.behaviour.start_patience > sorted(patience.values())[-2]
    assert mx.behaviour.insult_cost > sorted(insult.values())[-2]


@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p.id)
def test_every_template_renders(persona):
    assert set(persona.templates) == set(TEMPLATE_KEYS)
    assert persona.style
    for key in TEMPLATE_KEYS:
        text = fill_template(
            persona, key, amount="€500k", equity="30%", startup="GreenCharge",
            player_offer="€500k for 10%",
        )
        assert text.strip()
        assert not re.search(r"[{}]", text)
