"""Wraps any voice so a turn always gets a correct reply and valid options."""

from __future__ import annotations

import logging

from .base import VoiceBackend, VoiceRequest, VoiceResult, system_options
from .guard import check_reply, correction_note, fallback_sentence, repair_options
from .stub import template_reply

log = logging.getLogger(__name__)


class GuardedVoice:
    """call → number guard → one corrective retry → plain sentence. Never raises."""

    def __init__(self, backend: VoiceBackend):
        self.backend = backend

    @property
    def name(self) -> str:
        return self.backend.name

    def render(self, request: VoiceRequest) -> VoiceResult:
        try:
            draft = self.backend.compose(request)
            problems = check_reply(draft.reply, request)
            note = ""
            if problems:
                log.info("voice reply failed the number guard: %s", problems)
                draft = self.backend.compose(request, correction_note(problems, request))
                problems = check_reply(draft.reply, request)
                note = "corrected after retry"
            reply = draft.reply
            if problems:
                log.info("voice retry failed the number guard: %s", problems)
                reply, note = fallback_sentence(request), "fallback sentence"
            return VoiceResult(reply=reply, options=repair_options(draft.options, request),
                               source=self.backend.name, note=note)
        except Exception:  # noqa: BLE001 - the voice must never break a turn
            log.warning("voice backend %s failed; using templates", self.backend.name,
                        exc_info=True)
            options = repair_options(
                [o.model_dump() | {"equity": o.equity / 10 if o.equity else None}
                 for o in system_options(request)],
                request,
            )
            return VoiceResult(reply=template_reply(request), options=options,
                               source="template", note="voice unavailable")
