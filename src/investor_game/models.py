"""Domain models shared by the engine, policy, brain, voice and CLI."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from . import money

MAX_TURNS = 15
MAX_MESSAGE_CHARS = 4_000
GAME_ENDED_MESSAGE = "This game has already ended"
BRAIN_UNAVAILABLE_MESSAGE = "The investor couldn't respond. Your move wasn't used. Try again."


class GameOverError(RuntimeError):
    """A move was sent to a finished game."""

    def __init__(self) -> None:
        super().__init__(GAME_ENDED_MESSAGE)


class BrainUnavailableError(RuntimeError):
    """The decision AI failed; the game is unchanged and the move can be retried."""

    def __init__(self) -> None:
        super().__init__(BRAIN_UNAVAILABLE_MESSAGE)


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


# ---------------------------------------------------------------------------
# Pitch
# ---------------------------------------------------------------------------

_TEXT_LIMITS = {
    "name": ("Startup name", 80),
    "sector": ("Sector", 60),
    "description": ("Description", 2_000),
}
_MONEY_FIELDS = {"valuation": "Valuation", "ask": "Amount to raise"}


class PitchError(ValueError):
    """A pitch failed validation. ``errors`` maps field name to a plain message."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(errors.values()))
        self.errors = errors


def validate_text_field(field: str, value: str) -> str:
    label, limit = _TEXT_LIMITS[field]
    text = (value or "").strip()
    if not 1 <= len(text) <= limit:
        raise ValueError(f"{label} must be between 1 and {limit:,} characters.")
    return text


def validate_money_field(field: str, value: str | int) -> int:
    try:
        return money.parse_money(value)
    except ValueError as exc:
        raise ValueError(f"{_MONEY_FIELDS[field]} {money.MONEY_ERROR}.") from exc


class Pitch(Frozen):
    name: str
    sector: str
    description: str
    valuation: int  # pre-money, whole euros
    ask: int  # whole euros

    @classmethod
    def create(cls, **fields: str | int) -> Pitch:
        """Validate raw input; raise ``PitchError`` with one message per bad field."""
        errors: dict[str, str] = {}
        clean: dict[str, str | int] = {}
        for field in _TEXT_LIMITS:
            try:
                clean[field] = validate_text_field(field, str(fields.get(field, "")))
            except ValueError as exc:
                errors[field] = str(exc)
        for field in _MONEY_FIELDS:
            try:
                clean[field] = validate_money_field(field, fields.get(field, ""))
            except ValueError as exc:
                errors[field] = str(exc)
        if errors:
            raise PitchError(errors)
        return cls(**clean)

    @property
    def implied_equity(self) -> Decimal:
        return money.implied_equity(self.ask, self.valuation)


EXAMPLE_PITCH = {
    "name": "GreenCharge",
    "sector": "EV charging",
    "description": (
        "Fast-charging hubs for electric delivery fleets in European cities, with smart "
        "scheduling software that cuts fleet charging costs by 30%."
    ),
    "valuation": "€2M",
    "ask": "€500k",
}


# ---------------------------------------------------------------------------
# Offers and moves
# ---------------------------------------------------------------------------


class Offer(Frozen):
    amount: int  # euros
    equity: int  # tenths of a percent

    @property
    def post_money(self) -> Decimal:
        return money.post_money(self.amount, self.equity)

    @property
    def pre_money(self) -> Decimal:
        return money.pre_money(self.amount, self.equity)

    def describe(self) -> str:
        return f"{money.format_money(self.amount)} for {money.format_equity(self.equity)}"


class MoveKind(StrEnum):
    ACCEPT = "accept"
    WALK_AWAY = "walk_away"
    OFFER = "offer"
    MESSAGE = "message"


class MoveError(ValueError):
    """A player move failed validation; it does not use up a turn."""


class Move(Frozen):
    kind: MoveKind
    offer: Offer | None = None
    text: str | None = None

    @classmethod
    def accept(cls) -> Move:
        return cls(kind=MoveKind.ACCEPT)

    @classmethod
    def walk_away(cls) -> Move:
        return cls(kind=MoveKind.WALK_AWAY)

    @classmethod
    def make_offer(cls, amount: int, equity: int) -> Move:
        return cls(kind=MoveKind.OFFER, offer=Offer(amount=amount, equity=equity))

    @classmethod
    def message(cls, text: str) -> Move:
        return cls(kind=MoveKind.MESSAGE, text=text)

    def validate_move(self) -> None:
        if self.kind is MoveKind.OFFER:
            if self.offer is None or self.offer.amount <= 0:
                raise MoveError("An offer needs an amount above €0.")
            if not 0 < self.offer.equity < money.FULL_EQUITY:
                raise MoveError("Equity must be more than 0% and less than 100%.")
        if self.kind is MoveKind.MESSAGE:
            text = (self.text or "").strip()
            if not text:
                raise MoveError("Write a message before sending it.")
            if len(self.text or "") > MAX_MESSAGE_CHARS:
                raise MoveError(f"Messages can be at most {MAX_MESSAGE_CHARS:,} characters.")

    def describe(self) -> str:
        if self.kind is MoveKind.OFFER and self.offer:
            return f"Offer {self.offer.describe()}"
        if self.kind is MoveKind.MESSAGE:
            return self.text or ""
        return "Accept the current offer" if self.kind is MoveKind.ACCEPT else "Walk away"


OptionKind = Literal["accept", "walk_away", "counter", "message"]


class Option(Frozen):
    """A suggested player reply."""

    kind: OptionKind
    label: str
    amount: int | None = None
    equity: int | None = None  # tenths
    text: str | None = None

    def to_move(self) -> Move:
        if self.kind == "accept":
            return Move.accept()
        if self.kind == "walk_away":
            return Move.walk_away()
        if self.kind == "counter":
            return Move.make_offer(self.amount or 0, self.equity or 0)
        return Move.message(self.text or self.label)


# ---------------------------------------------------------------------------
# Brain answers and judgments
# ---------------------------------------------------------------------------

UNCERTAIN_BELOW = 0.55


class Answer(Frozen):
    """One brain answer, ready for the Brain insights view."""

    id: str
    question: str
    kind: Literal["noul", "choice", "score"]
    value: str
    confidence: float  # probability of "yes" for a noul, confidence otherwise

    @property
    def uncertain(self) -> bool:
        if self.kind == "noul":
            return 0.45 <= self.confidence <= 0.55
        return self.confidence < UNCERTAIN_BELOW


class Judgments(Frozen):
    """The brain's typed judgments about one player move."""

    accept_probability: float
    quality: str  # poor | fair | good | great
    concession: str  # none | small | medium | large
    intent: str | None = None
    intent_confidence: float = 1.0
    politeness: str | None = None  # rude | neutral | polite | very polite
    assertiveness: str | None = None  # timid | unsure | confident | very confident
    insult_probability: float = 0.0
    manipulation_probability: float = 0.0
    offer: Offer | None = None  # offer extracted from a free message
    extraction_confidence: float = 1.0
    has_offer_candidates: bool = False


class Action(StrEnum):
    OPEN = "open"
    ACCEPT = "accept"
    COUNTER = "counter"
    REJECT = "reject"
    CLARIFY = "clarify"
    DISMISS = "dismiss"
    WALK_AWAY = "walk_away"
    PLAYER_ACCEPTED = "player_accepted"
    PLAYER_WALKED = "player_walked"
    OUT_OF_TURNS = "out_of_turns"


class Outcome(StrEnum):
    DEAL = "Deal"
    INVESTOR_WALKED = "Investor walked away"
    PLAYER_WALKED = "You walked away"
    OUT_OF_TURNS = "Out of turns"


class Decision(Frozen):
    """The game master's decision for one turn. All numbers are final."""

    action: Action
    investor_offer: Offer  # the investor's offer after this turn
    player_offer: Offer | None  # the player's latest offer after this turn
    interest: float
    patience: float
    outcome: Outcome | None = None
    final_offer: Offer | None = None
    reason: str = ""


# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------


class Message(Frozen):
    role: Literal["investor", "player"]
    text: str
    action: str | None = None


class TurnInsight(Frozen):
    turn: int
    move: str
    answers: tuple[Answer, ...]
    action: Action
    backend: str
    latency_ms: int
    voice: str = ""


class GameState(Frozen):
    """Full game state, including secrets. Never handed to the CLI."""

    id: int
    persona_id: str
    pitch: Pitch
    investor_offer: Offer
    player_offer: Offer | None = None
    interest: float
    patience: float
    turn: int = 0
    transcript: tuple[Message, ...] = ()
    insights: tuple[TurnInsight, ...] = ()
    options: tuple[Option, ...] = ()
    outcome: Outcome | None = None
    final_offer: Offer | None = None

    @property
    def ended(self) -> bool:
        return self.outcome is not None


class PublicProfile(Frozen):
    id: str
    name: str
    emoji: str
    description: str
    traits: tuple[str, str]

    @property
    def first_name(self) -> str:
        parts = self.name.split()
        return parts[1] if parts[0].endswith(".") and len(parts) > 1 else parts[0]


class PlayerView(Frozen):
    """Everything the player may see about a game. Holds no secret values."""

    id: int
    investor: PublicProfile
    pitch: Pitch
    investor_offer: Offer
    player_offer: Offer | None
    turn: int
    max_turns: int
    interest_hint: str
    patience_hint: str
    transcript: tuple[Message, ...]
    insights: tuple[TurnInsight, ...]
    options: tuple[Option, ...]
    outcome: Outcome | None
    final_offer: Offer | None
    log_folder: str | None = None  # this game's LLM log folder, when logging is on
    log_warning: str | None = None  # set once if writing LLM logs failed

    @property
    def ended(self) -> bool:
        return self.outcome is not None

    @property
    def equity_gap(self) -> int | None:
        if self.player_offer is None:
            return None
        return self.investor_offer.equity - self.player_offer.equity

    @property
    def amount_gap(self) -> int | None:
        if self.player_offer is None:
            return None
        return self.player_offer.amount - self.investor_offer.amount

    @property
    def last_investor_message(self) -> Message | None:
        return next((m for m in reversed(self.transcript) if m.role == "investor"), None)
