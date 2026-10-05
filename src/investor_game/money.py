"""Euro amounts, equity percentages and valuation maths.

Money is held as whole euros (``int``). Equity is held as tenths of a percent
(``int``): 240 means 24.0%. Valuations are computed with ``Decimal`` and only
rounded for display.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal

EQUITY_SCALE = 10  # equity is stored in tenths of a percent
FULL_EQUITY = 100 * EQUITY_SCALE

MONEY_ERROR = "must be a whole number of euros above zero"

_SUFFIXES = {
    "": Decimal(1),
    "k": Decimal(1_000),
    "thousand": Decimal(1_000),
    "m": Decimal(1_000_000),
    "mm": Decimal(1_000_000),
    "mn": Decimal(1_000_000),
    "million": Decimal(1_000_000),
    "bn": Decimal(1_000_000_000),
    "b": Decimal(1_000_000_000),
    "billion": Decimal(1_000_000_000),
}

_NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_SUFFIX = r"k|thousand|mm|mn|million|m|bn|billion|b"
_PARSE_MONEY = re.compile(
    rf"^\s*(?:€|eur\b|euros?\b)?\s*(?P<num>{_NUMBER})\s*(?P<suf>{_SUFFIX})?\s*"
    rf"(?:€|eur|euros?)?\s*$",
    re.IGNORECASE,
)


def _to_decimal(number: str) -> Decimal:
    return Decimal(number.replace(",", ""))


def parse_money(text: str | int) -> int:
    """Parse ``500000``, ``500k``, ``2M``, ``0.5M`` or ``€2,000,000`` into whole euros.

    Raises ``ValueError`` when the text is not a whole, positive euro amount.
    """
    if isinstance(text, int):
        value = Decimal(text)
    else:
        match = _PARSE_MONEY.match(text or "")
        if not match:
            raise ValueError(MONEY_ERROR)
        try:
            value = _to_decimal(match["num"]) * _SUFFIXES[(match["suf"] or "").lower()]
        except InvalidOperation as exc:
            raise ValueError(MONEY_ERROR) from exc
    if value <= 0 or value != value.to_integral_value():
        raise ValueError(MONEY_ERROR)
    return int(value)


def parse_equity(text: str | float | int) -> int:
    """Parse ``15``, ``15%`` or ``15.5`` into tenths of a percent (0 < equity < 100)."""
    raw = str(text).strip().rstrip("%").strip()
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("Equity must be a percentage between 0 and 100") from exc
    tenths = int((value * EQUITY_SCALE).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if not 0 < tenths < FULL_EQUITY:
        raise ValueError("Equity must be a percentage between 0 and 100")
    return tenths


def equity_to_tenths(percent: float | Decimal) -> int:
    return int((Decimal(str(percent)) * EQUITY_SCALE).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def post_money(amount: int, equity_tenths: int) -> Decimal:
    """Company value after the investment implied by ``amount`` for ``equity``."""
    return Decimal(amount) * FULL_EQUITY / Decimal(equity_tenths)


def pre_money(amount: int, equity_tenths: int) -> Decimal:
    """Company value before the investment implied by the offer."""
    return post_money(amount, equity_tenths) - amount


def implied_equity(ask: int, valuation: int) -> Decimal:
    """Equity percentage the ask implies at a pre-money ``valuation``."""
    return Decimal(ask) * 100 / (Decimal(valuation) + Decimal(ask))


def _strip(number: str) -> str:
    return number.rstrip("0").rstrip(".") if "." in number else number


def _round(value: Decimal, decimals: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def format_money(amount: int | Decimal) -> str:
    """Short form: ``€950``, ``€500k``, ``€227k``, ``€2.27M``, ``€2M``."""
    value = Decimal(amount)
    sign = "−" if value < 0 else ""
    value = abs(value)
    if value < 1_000:
        return f"{sign}€{value.quantize(Decimal(1), rounding=ROUND_HALF_UP)}"
    if value < 1_000_000:
        thousands = value / 1_000
        decimals = 0 if thousands >= 100 else (1 if thousands >= 10 else 2)
        rounded = _round(thousands, decimals)
        if rounded < 1_000:
            return f"{sign}€{_strip(f'{rounded:.{decimals}f}')}k"
    millions = value / 1_000_000
    return f"{sign}€{_strip(f'{_round(millions, 2):.2f}')}M"


def format_money_long(amount: int | Decimal) -> str:
    """Long form with thousands separators: ``€1,772,727``."""
    value = Decimal(amount).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    sign = "−" if value < 0 else ""
    return f"{sign}€{abs(value):,}"


def format_equity(tenths: int, fixed: bool = False) -> str:
    """``24%``/``24.5%`` for chat; ``24.0%`` when ``fixed`` (panels and tables)."""
    value = Decimal(tenths) / EQUITY_SCALE
    text = f"{value:.1f}"
    return f"{text if fixed else _strip(text)}%"


def format_percent(value: Decimal | float, decimals: int = 1) -> str:
    return f"{Decimal(str(value)):.{decimals}f}%"


# ---------------------------------------------------------------------------
# Number scanning: shared by offer extraction and the voice's number guard.
# ---------------------------------------------------------------------------

NumberKind = Literal["money", "percent"]


@dataclass(frozen=True)
class FoundNumber:
    """A money amount or percentage that literally appears in some text."""

    kind: NumberKind
    value: Decimal  # euros for money, percent for percent
    step: Decimal  # precision it was written with (€10k for "€2.27M", 1 for "24%")
    text: str
    start: int
    end: int

    @property
    def euros(self) -> int:
        return int(self.value.quantize(Decimal(1), rounding=ROUND_HALF_UP))

    @property
    def tenths(self) -> int:
        return equity_to_tenths(self.value)

    def matches(self, target: Decimal | int) -> bool:
        """True when ``target`` rounds to this number at the precision it was written."""
        return abs(Decimal(target) - self.value) <= self.step / 2


_PERCENT_RE = re.compile(
    r"(?<![\w.])(?P<num>\d+(?:\.\d+)?)\s*(?:%|percent\b|per\s+cent\b|pc\b)", re.IGNORECASE
)
_MONEY_RE = re.compile(
    rf"(?:(?P<cur>€|\beur\b|\beuros?\b)\s*(?P<num1>{_NUMBER})\s*(?P<suf1>{_SUFFIX})?\b"
    rf"|(?<![\w.,])(?P<num2>{_NUMBER})\s*(?:(?P<suf2>{_SUFFIX})\b\s*(?:€|eur\b|euros?\b)?"
    rf"|(?P<cur2>€|eur\b|euros?\b))"
    rf"|(?<![\w.,€])(?P<bare>\d{{1,3}}(?:,\d{{3}})+|\d{{5,}})(?![\w.,%]))",
    re.IGNORECASE,
)

BARE_MONEY_MIN = 10_000


def _step(number: str, multiplier: Decimal) -> Decimal:
    plain = number.replace(",", "")
    decimals = len(plain.split(".")[1]) if "." in plain else 0
    return multiplier / (Decimal(10) ** decimals)


def scan_numbers(text: str, include_bare: bool = True) -> list[FoundNumber]:
    """Find money amounts and percentages written in ``text``, in order of appearance.

    Money needs a € / EUR marker or a k/M suffix. Bare numbers count as money only when
    ``include_bare`` is set and they are at least €10,000 (so "15 turns" or "2026" are
    ignored).
    """
    found: list[FoundNumber] = []
    taken: list[tuple[int, int]] = []
    for match in _PERCENT_RE.finditer(text):
        number = match["num"]
        found.append(
            FoundNumber("percent", Decimal(number), _step(number, Decimal(1)), match.group(0),
                        match.start(), match.end())
        )
        taken.append((match.start(), match.end()))

    for match in _MONEY_RE.finditer(text):
        if any(start < match.end() and match.start() < end for start, end in taken):
            continue
        if match["bare"] is not None:
            if not include_bare:
                continue
            number, suffix = match["bare"], ""
        elif match["num1"] is not None:
            number, suffix = match["num1"], match["suf1"] or ""
        else:
            number, suffix = match["num2"], match["suf2"] or ""
        multiplier = _SUFFIXES[suffix.lower()]
        value = _to_decimal(number) * multiplier
        if match["bare"] is not None and value < BARE_MONEY_MIN:
            continue
        if value <= 0:
            continue
        found.append(
            FoundNumber("money", value, _step(number, multiplier), match.group(0).strip(),
                        match.start(), match.end())
        )
    found.sort(key=lambda item: item.start)
    return found
