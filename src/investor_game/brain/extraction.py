"""Offer extraction from free text: only numbers that literally appear can form an offer."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Offer
from ..money import FoundNumber, format_equity, format_money, scan_numbers

NONE_KEY = "none"


@dataclass(frozen=True)
class Candidates:
    amounts: dict[str, FoundNumber] = field(default_factory=dict)
    equities: dict[str, FoundNumber] = field(default_factory=dict)

    @property
    def any(self) -> bool:
        return bool(self.amounts or self.equities)

    def to_state(self) -> dict[str, dict[str, dict[str, object]]]:
        """Candidate values for the brain's state, keyed like the Choice answers."""
        return {
            "amounts": {k: {"eur": f.euros, "written": f.text} for k, f in self.amounts.items()},
            "equities": {k: {"percent": float(f.value), "written": f.text}
                         for k, f in self.equities.items()},
        }

    def amount_criteria(self) -> dict[str, str]:
        criteria = {k: f"The player offers {format_money(f.euros)} (\"{f.text}\")"
                    for k, f in self.amounts.items()}
        criteria[NONE_KEY] = "None of these is the amount the player is offering"
        return criteria

    def equity_criteria(self) -> dict[str, str]:
        criteria = {k: f"The player offers {format_equity(f.tenths)} equity (\"{f.text}\")"
                    for k, f in self.equities.items()}
        criteria[NONE_KEY] = "None of these is the equity share the player is offering"
        return criteria

    def offer_from(self, amount_key: str | None, equity_key: str | None) -> Offer | None:
        """Build an offer only from chosen candidates; ``none`` or a missing side gives None."""
        amount = self.amounts.get(amount_key or NONE_KEY)
        equity = self.equities.get(equity_key or NONE_KEY)
        if amount is None or equity is None:
            return None
        if amount.euros <= 0 or not 0 < equity.tenths < 1000:
            return None
        return Offer(amount=amount.euros, equity=equity.tenths)


def find_candidates(text: str) -> Candidates:
    found = scan_numbers(text)
    amounts = [f for f in found if f.kind == "money"]
    equities = [f for f in found if f.kind == "percent"]
    return Candidates(
        amounts={f"a{i}": f for i, f in enumerate(amounts, 1)},
        equities={f"e{i}": f for i, f in enumerate(equities, 1)},
    )
