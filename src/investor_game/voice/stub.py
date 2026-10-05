"""Built-in template voice: deterministic, offline, and the fallback for every other voice."""

from __future__ import annotations

from ..money import format_equity, format_money
from .base import VoiceDraft, VoiceRequest, system_options


def template_reply(request: VoiceRequest) -> str:
    """The persona's template for the decided action, filled with the decided numbers only."""
    offer = request.stated_offer or request.investor_offer
    player = request.player_offer
    values = {
        "amount": format_money(offer.amount),
        "equity": format_equity(offer.equity),
        "startup": request.pitch.name,
        "player_offer": player.describe() if player else "That",
    }
    return request.templates[request.template_key].format(**values)


class StubVoiceBackend:
    name = "stub"

    def compose(self, request: VoiceRequest, correction: str | None = None) -> VoiceDraft:
        options = [] if request.ended else [
            option.model_dump(exclude_none=True) for option in system_options(request)
        ]
        for option in options:
            if option.get("equity") is not None:
                option["equity"] = option["equity"] / 10  # options speak percent, like an LLM
        return VoiceDraft(reply=template_reply(request), options=options)
