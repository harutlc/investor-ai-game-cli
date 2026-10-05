from decimal import Decimal

import pytest

from investor_game.money import (
    format_equity,
    format_money,
    format_money_long,
    implied_equity,
    parse_equity,
    parse_money,
    post_money,
    pre_money,
    scan_numbers,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("500000", 500_000),
        ("500k", 500_000),
        ("500K", 500_000),
        ("2M", 2_000_000),
        ("0.5M", 500_000),
        ("€2,000,000", 2_000_000),
        ("€ 750k", 750_000),
        ("1.25m", 1_250_000),
        ("300000 EUR", 300_000),
    ],
)
def test_parse_money(text, expected):
    assert parse_money(text) == expected


@pytest.mark.parametrize("text", ["lots", "", "0", "-5", "1.5", "0.0001k", "€", "12abc"])
def test_parse_money_rejects(text):
    with pytest.raises(ValueError, match="whole number of euros above zero"):
        parse_money(text)


def test_parse_equity():
    assert parse_equity("15") == 150
    assert parse_equity("15.5%") == 155
    for bad in ["0", "100", "120", "x", "-3"]:
        with pytest.raises(ValueError):
            parse_equity(bad)


def test_valuation_maths():
    assert post_money(500_000, 200) == Decimal(2_500_000)
    assert pre_money(500_000, 200) == Decimal(2_000_000)
    assert f"{implied_equity(500_000, 2_000_000):.1f}" == "20.0"


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (950, "€950"),
        (500_000, "€500k"),
        (550_000, "€550k"),
        (227_273, "€227k"),
        (12_500, "€12.5k"),
        (2_000_000, "€2M"),
        (2_500_000, "€2.5M"),
        (2_272_727, "€2.27M"),
        (3_333_333, "€3.33M"),
        (2_625_000, "€2.63M"),
        (999_999, "€1M"),
        (-227_273, "−€227k"),
    ],
)
def test_format_money(amount, expected):
    assert format_money(amount) == expected


def test_format_long_and_equity():
    assert format_money_long(1_772_727) == "€1,772,727"
    assert format_money_long(Decimal("1772727.27")) == "€1,772,727"
    assert format_equity(240) == "24%"
    assert format_equity(245) == "24.5%"
    assert format_equity(240, fixed=True) == "24.0%"


def test_scan_offer_in_words():
    found = scan_numbers("€500k for 15%, we have another fund interested")
    assert [(f.kind, f.value) for f in found] == [
        ("money", Decimal(500_000)),
        ("percent", Decimal(15)),
    ]
    assert found[0].text == "€500k"
    assert found[1].start > found[0].start


def test_scan_percent_words_and_ignores_plain_numbers():
    found = scan_numbers("I could do 15 percent, we have 15 turns left in 2026")
    assert [(f.kind, f.value) for f in found] == [("percent", Decimal(15))]


def test_scan_various_money_forms():
    found = scan_numbers("Either 0.5M or 600,000 or 750 thousand euros, or 1.2 million")
    assert [f.euros for f in found if f.kind == "money"] == [500_000, 600_000, 750_000, 1_200_000]


def test_scan_bare_numbers_optional():
    assert scan_numbers("500000 for 20%", include_bare=False)[0].kind == "percent"
    assert [f.kind for f in scan_numbers("500000 for 20%")] == ["money", "percent"]


def test_precision_aware_match():
    millions = scan_numbers("€2.27M")[0]
    assert millions.matches(2_272_727)
    assert not millions.matches(2_300_000)
    percent = scan_numbers("24%")[0]
    assert percent.matches(24)
    assert not percent.matches(Decimal("25"))
    exact = scan_numbers("€550,000")[0]
    assert exact.matches(550_000) and not exact.matches(550_001)
