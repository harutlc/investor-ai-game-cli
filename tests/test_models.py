import pytest

from investor_game.models import (
    EXAMPLE_PITCH,
    Move,
    MoveError,
    Offer,
    Option,
    Pitch,
    PitchError,
    PlayerView,
)

VALID = {
    "name": "GreenCharge",
    "sector": "EV charging",
    "description": "Fast chargers for fleets.",
    "valuation": 2_000_000,
    "ask": 500_000,
}


def test_valid_pitch():
    pitch = Pitch.create(**VALID)
    assert pitch.valuation == 2_000_000
    assert f"{pitch.implied_equity:.1f}" == "20.0"


def test_example_pitch_is_valid():
    pitch = Pitch.create(**EXAMPLE_PITCH)
    assert (pitch.valuation, pitch.ask) == (2_000_000, 500_000)


def test_name_too_long():
    with pytest.raises(PitchError) as err:
        Pitch.create(**{**VALID, "name": "x" * 81})
    assert set(err.value.errors) == {"name"}
    assert "80" in err.value.errors["name"]


@pytest.mark.parametrize("ask", [0, -5, "1.5", "lots", ""])
def test_ask_must_be_whole_positive(ask):
    with pytest.raises(PitchError) as err:
        Pitch.create(**{**VALID, "ask": ask})
    assert "whole number of euros above zero" in err.value.errors["ask"]


def test_multiple_errors_reported_per_field():
    with pytest.raises(PitchError) as err:
        Pitch.create(name=" ", sector="s" * 61, description="d" * 2001, valuation="x", ask=1)
    assert set(err.value.errors) == {"name", "sector", "description", "valuation"}
    assert "2,000" in err.value.errors["description"]


def test_text_is_trimmed():
    assert Pitch.create(**{**VALID, "name": "  GreenCharge  "}).name == "GreenCharge"


def test_move_validation():
    Move.make_offer(500_000, 150).validate_move()
    for equity in (0, 1000, 1200):
        with pytest.raises(MoveError):
            Move.make_offer(500_000, equity).validate_move()
    with pytest.raises(MoveError):
        Move.make_offer(0, 150).validate_move()
    with pytest.raises(MoveError):
        Move.message("x" * 4001).validate_move()
    with pytest.raises(MoveError):
        Move.message("   ").validate_move()
    Move.message("x" * 4000).validate_move()


def test_option_to_move():
    option = Option(kind="counter", label="Counter", amount=500_000, equity=150)
    assert option.to_move().offer == Offer(amount=500_000, equity=150)
    assert Option(kind="walk_away", label="Walk away").to_move().kind == "walk_away"


def test_offer_valuations():
    offer = Offer(amount=500_000, equity=200)
    assert offer.post_money == 2_500_000
    assert offer.pre_money == 2_000_000
    assert offer.describe() == "€500k for 20%"


def test_player_view_has_no_secret_fields():
    fields = set(PlayerView.model_fields)
    forbidden = {"budget", "min_equity", "max_equity", "interest", "patience", "limits"}
    assert not fields & forbidden
