"""The number guard: every euro amount and percentage the player sees must match the decision."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..models import Offer, Option
from ..money import (
    FULL_EQUITY,
    equity_to_tenths,
    format_equity,
    format_money,
    parse_money,
    scan_numbers,
)
from .base import (
    VoiceRequest,
    accept_option,
    counter_option,
    system_options,
    walk_away_option,
)

MAX_OPTIONS = 5
MIN_OPTIONS = 3
MAX_LABEL = 160


def _offers(request: VoiceRequest) -> list[Offer]:
    offers = [request.investor_offer, request.player_offer, request.previous_investor_offer,
              request.final_offer]
    return [offer for offer in offers if offer is not None]


def allowed_numbers(request: VoiceRequest) -> tuple[set[Decimal], set[Decimal]]:
    """(euro amounts, percentages) that may appear in a reply for this turn."""
    amounts: set[Decimal] = {Decimal(request.pitch.ask), Decimal(request.pitch.valuation),
                             Decimal(request.pitch.valuation + request.pitch.ask)}
    percents: set[Decimal] = {request.pitch.implied_equity}
    for offer in _offers(request):
        amounts |= {Decimal(offer.amount), offer.post_money, offer.pre_money}
        percents.add(Decimal(offer.equity) / 10)
    return amounts, percents


def check_text(text: str, request: VoiceRequest, extra: list[Offer] = ()) -> list[str]:
    """Problems with the numbers in ``text``; an empty list means it is safe to show."""
    amounts, percents = allowed_numbers(request)
    for offer in extra:
        amounts.add(Decimal(offer.amount))
        percents.add(Decimal(offer.equity) / 10)
    problems = []
    for found in scan_numbers(text):
        pool = amounts if found.kind == "money" else percents
        if not any(found.matches(value) for value in pool):
            problems.append(f"{found.text!r} is not one of the agreed numbers")
    return problems


def contains_offer(text: str, offer: Offer) -> bool:
    found = scan_numbers(text)
    has_amount = any(f.kind == "money" and f.matches(offer.amount) for f in found)
    has_equity = any(f.kind == "percent" and f.matches(Decimal(offer.equity) / 10) for f in found)
    return has_amount and has_equity


def check_reply(reply: str, request: VoiceRequest) -> list[str]:
    if not reply or not reply.strip():
        return ["the reply is empty"]
    problems = check_text(reply, request)
    required = request.required_offer
    if required is not None and not contains_offer(reply, required):
        problems.append(
            f"the reply must state {format_money(required.amount)} for "
            f"{format_equity(required.equity)}"
        )
    return problems


def correction_note(problems: list[str], request: VoiceRequest) -> str:
    stated = request.stated_offer
    numbers = f" The offer is exactly {stated.describe()}." if stated else ""
    return (
        "Your previous reply had wrong numbers: " + "; ".join(problems) + "." + numbers
        + " Rewrite it using only the agreed numbers."
    )


def fallback_sentence(request: VoiceRequest) -> str:
    """A plain, always-correct sentence built from the decision."""
    offer = request.stated_offer
    terms = offer.describe() if offer else ""
    sentences = {
        "open": f"I can do {terms}. That's my offer.",
        "counter": f"I can do {terms}. That's my offer.",
        "hold": f"My offer stays at {terms}.",
        "reject": f"That doesn't work for me. My offer stays at {terms}.",
        "dismiss": f"Let's stick to the deal. My offer stays at {terms}.",
        "clarify": "Could you tell me the exact amount and equity share you have in mind?",
        "accept": f"Deal: {terms}.",
        "player_accepted": f"Deal: {terms}.",
        "walk_away": "I'm walking away. No deal.",
        "player_walked": "Understood. No deal.",
        "out_of_turns": "We're out of time. No deal.",
    }
    return sentences[request.template_key]


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        if isinstance(value, str):
            return parse_money(value)
        number = Decimal(str(value))
        return int(number) if number == number.to_integral_value() and number > 0 else None
    except (ValueError, ArithmeticError):
        return None


def _as_tenths(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        tenths = equity_to_tenths(Decimal(str(value).strip().rstrip("%")))
    except (ValueError, ArithmeticError):
        return None
    return tenths if 0 < tenths < FULL_EQUITY else None


def _repair_one(raw: Any, request: VoiceRequest) -> Option | None:
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    label = str(raw.get("label") or "").strip()[:MAX_LABEL]
    if kind == "counter":
        amount, equity = _as_int(raw.get("amount")), _as_tenths(raw.get("equity"))
        if amount is None or equity is None:
            return None
        option = counter_option(amount, equity)
        if label and not check_text(label, request, extra=[Offer(amount=amount, equity=equity)]):
            # Keep the model's wording only when its numbers are the option's own.
            if contains_offer(label, Offer(amount=amount, equity=equity)):
                option = option.model_copy(update={"label": label})
        return option
    if kind == "message":
        text = str(raw.get("text") or label).strip()[:2000]
        label = label or text[:60]
        if not text or check_text(text, request) or check_text(label, request):
            return None
        return Option(kind="message", label=label, text=text)
    return None  # accept / walk away are always rebuilt by the system


def repair_options(raw_options: Any, request: VoiceRequest) -> tuple[Option, ...]:
    """Validate generated options; fix or drop bad ones; always offer accept and walk away."""
    if request.ended:
        return ()
    generated: list[Option] = []
    for raw in raw_options if isinstance(raw_options, list) else []:
        option = _repair_one(raw, request)
        if option is not None:
            generated.append(option)

    fixed = [accept_option(request.investor_offer), walk_away_option()]
    extras = [o for o in system_options(request) if o.kind in ("counter", "message")]
    current = request.investor_offer
    seen: set[tuple] = set()
    result: list[Option] = []
    candidates = [(False, o) for o in generated] + [(True, o) for o in extras]
    for is_extra, option in candidates:
        if len(result) + len(fixed) >= MAX_OPTIONS:
            break
        if is_extra and len(result) + len(fixed) >= MIN_OPTIONS:
            break  # system extras only fill up to the minimum
        if option.kind == "counter" and option.equity >= current.equity:
            continue  # giving at least the equity asked for is accepting, or worse
        key = (option.kind, option.amount, option.equity, (option.text or "").lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(option)
    return tuple(result + fixed)
