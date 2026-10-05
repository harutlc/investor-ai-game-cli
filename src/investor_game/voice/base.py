"""Voice interfaces: turn a decided action into in-character words and reply options."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..models import Action, Message, Offer, Option, Pitch, PublicProfile
from ..money import equity_to_tenths, format_equity, format_money


class VoiceError(RuntimeError):
    """The text AI failed or returned something unusable."""


@dataclass(frozen=True)
class VoiceRequest:
    """Everything the voice may know for one reply. No secret limits, no numeric moods."""

    investor: PublicProfile
    style: str
    templates: dict[str, str]
    pitch: Pitch
    action: Action
    reason: str
    investor_offer: Offer  # the investor's offer after this turn
    player_offer: Offer | None
    previous_investor_offer: Offer | None
    final_offer: Offer | None
    transcript: tuple[Message, ...]  # conversation before this reply, incl. the player's move
    ended: bool

    @property
    def template_key(self) -> str:
        if self.action is Action.COUNTER and self.reason.startswith("hold"):
            return "hold"
        if self.action is Action.OPEN:
            return "open"
        return self.action.value

    @property
    def stated_offer(self) -> Offer | None:
        """The offer the reply talks about (the deal for accepts, else the investor's)."""
        if self.action in (Action.ACCEPT, Action.PLAYER_ACCEPTED):
            return self.final_offer
        if self.action in (Action.WALK_AWAY, Action.PLAYER_WALKED, Action.OUT_OF_TURNS,
                           Action.CLARIFY):
            return None
        return self.investor_offer

    @property
    def required_offer(self) -> Offer | None:
        """Numbers that must appear in the reply."""
        if self.action in (Action.OPEN, Action.ACCEPT, Action.PLAYER_ACCEPTED):
            return self.stated_offer
        if self.template_key == "counter":
            return self.investor_offer
        return None


@dataclass
class VoiceDraft:
    """Raw output of a voice backend, before the number guard."""

    reply: str
    options: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class VoiceResult:
    reply: str
    options: tuple[Option, ...]
    source: str  # backend name, or "template" when the fallback was used
    note: str = ""  # "", "corrected after retry", "fallback sentence", "voice unavailable"


class VoiceBackend(Protocol):
    name: str

    def compose(self, request: VoiceRequest, correction: str | None = None) -> VoiceDraft:
        """Write the reply and suggested options, or raise ``VoiceError``."""
        ...


def accept_option(offer: Offer) -> Option:
    return Option(kind="accept", label=f"Accept {offer.describe()}")


def walk_away_option() -> Option:
    return Option(kind="walk_away", label="Walk away")


def counter_option(amount: int, equity: int) -> Option:
    return Option(kind="counter", label=f"Counter: {format_money(amount)} for "
                  f"{format_equity(equity)}", amount=amount, equity=equity)


def halfway_counter(request: VoiceRequest) -> Option:
    investor = request.investor_offer
    if request.player_offer is not None and request.player_offer.equity < investor.equity:
        target = request.player_offer.equity
    else:
        target = min(investor.equity, equity_to_tenths(request.pitch.implied_equity))
    equity = max(1, (investor.equity + target) // 2)
    if equity >= investor.equity:
        equity = max(1, investor.equity - 10)
    return counter_option(investor.amount, equity)


def polite_message_option(request: VoiceRequest) -> Option:
    text = (f"I appreciate the offer. {request.pitch.name} is growing fast, and I'd like terms "
            "that keep the team motivated. Can you move closer to my number?")
    return Option(kind="message", label="Make your case politely", text=text)


def system_options(request: VoiceRequest) -> list[Option]:
    """Options the game builds itself: halfway counter, polite message, accept, walk away."""
    return [
        halfway_counter(request),
        polite_message_option(request),
        accept_option(request.investor_offer),
        walk_away_option(),
    ]
