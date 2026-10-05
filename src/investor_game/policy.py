"""The game master: deterministic rules that turn brain judgments into one action.

The brain judges; this module decides. It owns the secret limits, every number in
an investor offer, and the interest/patience updates. It is pure: the same inputs
always give the same ``Decision``.
"""

from __future__ import annotations

import math

from .models import (
    Action,
    Decision,
    GameState,
    Judgments,
    Move,
    MoveKind,
    Offer,
    Outcome,
)
from .personas import Persona

ACCEPT_THRESHOLD = 0.60
UNSURE_BELOW = 0.55
SIGNAL_THRESHOLD = 0.5  # insult / manipulation probability that counts as "yes"
STALL_COST = 0.5
RAPPORT_BONUS = 0.5
OVER_BUDGET_FACTOR = 1.5
MAX_INTEREST = 10.0

QUALITY_LEVELS = ("poor", "fair", "good", "great")
CONCESSION_LEVELS = ("none", "small", "medium", "large")
POLITENESS_LEVELS = ("rude", "neutral", "polite", "very polite")
ASSERTIVENESS_LEVELS = ("timid", "unsure", "confident", "very confident")
INTENTS = (
    "offer",
    "accept_current",
    "walk_away",
    "question",
    "argument",
    "small_talk",
    "unclear",
)

CONCESSION_MULTIPLIER = {"none": 0.0, "small": 0.5, "medium": 1.0, "large": 1.5}
QUALITY_INTEREST = {"poor": -2.0, "fair": 0.0, "good": 1.0, "great": 2.0}
REJECT_INTEREST = -2.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def counter_equity(current: int, player: int, min_equity: int, effective: float) -> int:
    """Move from ``current`` toward ``player`` by ``effective`` of the gap (tenths).

    Rounded up to the next tenth (in the investor's favour) and clamped so it never
    goes below the player's equity or the minimum, and never above ``current``.
    """
    step = (current - player) * min(1.0, max(0.0, effective))
    proposed = math.ceil(round(current - step, 6))
    low = max(player, min_equity)
    return int(_clamp(proposed, low, max(current, low)))


def _rapport(judgments: Judgments) -> float:
    polite = judgments.politeness in ("polite", "very polite")
    confident = judgments.assertiveness in ("confident", "very confident")
    return RAPPORT_BONUS if polite and confident else 0.0


def decide(state: GameState, move: Move, judgments: Judgments | None, persona: Persona) -> Decision:
    """Choose exactly one investor action for ``move`` and compute the new numbers."""
    behaviour, limits = persona.behaviour, persona.limits
    current = state.investor_offer
    interest, patience = state.interest, state.patience

    def decision(action: Action, investor: Offer = current, player: Offer | None = None,
                 outcome: Outcome | None = None, final: Offer | None = None,
                 reason: str = "") -> Decision:
        return Decision(
            action=action,
            investor_offer=investor,
            player_offer=player if player is not None else state.player_offer,
            interest=_clamp(interest, 0.0, MAX_INTEREST),
            patience=_clamp(patience, 0.0, behaviour.start_patience),
            outcome=outcome,
            final_offer=final,
            reason=reason,
        )

    def walk_away(reason: str, player: Offer | None = None) -> Decision:
        return decision(Action.WALK_AWAY, player=player, outcome=Outcome.INVESTOR_WALKED,
                        reason=reason)

    # Player accept and walk-away never depend on the brain.
    if move.kind is MoveKind.ACCEPT:
        return decision(Action.PLAYER_ACCEPTED, outcome=Outcome.DEAL, final=current,
                        reason="player accepted the current offer")
    if move.kind is MoveKind.WALK_AWAY:
        return decision(Action.PLAYER_WALKED, outcome=Outcome.PLAYER_WALKED,
                        reason="player walked away")

    if judgments is None:
        raise ValueError("judgments are required for offers and messages")
    is_message = move.kind is MoveKind.MESSAGE

    # 1. Manipulation attempts are brushed off in character.
    if is_message and judgments.manipulation_probability >= SIGNAL_THRESHOLD:
        patience -= behaviour.insult_cost
        if patience <= 0:
            return walk_away("manipulation attempt exhausted patience")
        return decision(Action.DISMISS, reason="manipulation attempt")

    # 2. Insults cost patience before anything else is decided.
    if is_message and judgments.insult_probability >= SIGNAL_THRESHOLD:
        patience -= behaviour.insult_cost
        interest -= 1
    # 3. Out of patience: leave.
    if patience <= 0:
        return walk_away("patience ran out")

    # 4. Unsure what the player meant: ask, don't guess.
    if is_message and (
        judgments.intent_confidence < UNSURE_BELOW
        or (judgments.has_offer_candidates and judgments.extraction_confidence < UNSURE_BELOW)
    ):
        return decision(Action.CLARIFY, reason="unsure what the player meant")

    offer = move.offer if move.kind is MoveKind.OFFER else judgments.offer
    if is_message:
        interest += _rapport(judgments)

    # 5. No offer on the table.
    if offer is None:
        if is_message and judgments.intent == "accept_current":
            return decision(Action.PLAYER_ACCEPTED, outcome=Outcome.DEAL, final=current,
                            reason="player accepted the current offer in a message")
        if is_message and judgments.intent == "walk_away":
            return decision(Action.PLAYER_WALKED, outcome=Outcome.PLAYER_WALKED,
                            reason="player walked away in a message")
        if is_message and judgments.intent == "offer":
            # Terms were proposed but not both an amount and a share: ask, don't guess.
            return decision(Action.CLARIFY, reason="offer is missing an amount or a share")
        patience -= STALL_COST
        if patience <= 0:
            return walk_away("stalling exhausted patience")
        return decision(Action.COUNTER, reason="hold")

    within_limits = offer.amount <= limits.budget and offer.equity >= limits.min_equity
    far_outside = (
        offer.equity < limits.min_equity - behaviour.tolerance
        or offer.amount > limits.budget * OVER_BUDGET_FACTOR
    )

    # 6. Poor or far-out offers are rejected.
    if far_outside or judgments.quality == "poor":
        patience -= behaviour.reject_cost
        interest += REJECT_INTEREST
        if patience <= 0 or interest <= behaviour.walk_away_interest:
            return walk_away("offer rejected and investor lost interest", player=offer)
        return decision(Action.REJECT, player=offer,
                        reason="offer far outside limits" if far_outside else "poor offer")

    interest += QUALITY_INTEREST.get(judgments.quality, 0.0)

    # 7. Good offers within the limits are accepted.
    at_least_as_good = offer.equity >= current.equity and offer.amount <= current.amount
    likely = (
        judgments.accept_probability >= ACCEPT_THRESHOLD
        and judgments.quality in QUALITY_LEVELS[1:]
    )
    if within_limits and (at_least_as_good or likely):
        return decision(Action.ACCEPT, investor=offer, player=offer, outcome=Outcome.DEAL,
                        final=offer, reason="offer is acceptable")

    # The player gives at least as much equity but wants more money: hold position.
    if offer.equity >= current.equity:
        return decision(Action.COUNTER, player=offer, reason="hold: more money requested")

    # 8. Counter-offer: move toward the player, inside the limits.
    effective = behaviour.concession_rate * CONCESSION_MULTIPLIER.get(judgments.concession, 0.0)
    equity = counter_equity(current.equity, offer.equity, limits.min_equity, effective)
    amount = min(offer.amount, limits.budget)
    counter = Offer(amount=amount, equity=equity)
    if counter == offer and within_limits:
        return decision(Action.ACCEPT, investor=offer, player=offer, outcome=Outcome.DEAL,
                        final=offer, reason="counter met the player's offer")
    return decision(Action.COUNTER, investor=counter, player=offer, reason="counter-offer")


def opening_offer(ask: int, persona: Persona) -> Offer:
    """min(ask, budget) for the persona's maximum desired equity."""
    return Offer(amount=min(ask, persona.limits.budget), equity=persona.limits.max_equity)


def interest_hint(interest: float) -> str:
    if interest <= 3:
        return "Low"
    if interest <= 6:
        return "Medium"
    return "High"


PATIENCE_HINTS = (
    "Listening patiently",
    "Getting restless",
    "Tapping the table",
    "Checking the time",
    "Out of patience",
)


def patience_hint(patience: float, start: float) -> str:
    if patience <= 0:
        return PATIENCE_HINTS[4]
    ratio = patience / start
    if ratio > 0.75:
        return PATIENCE_HINTS[0]
    if ratio > 0.5:
        return PATIENCE_HINTS[1]
    if ratio > 0.25:
        return PATIENCE_HINTS[2]
    return PATIENCE_HINTS[3]
