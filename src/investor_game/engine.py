"""Game lifecycle: opening offer, atomic turns, end conditions and the player-safe view."""

from __future__ import annotations

from .brain.base import BrainError
from .brain.investor import InvestorBrain
from .brain.questions import BrainContext
from .models import (
    MAX_TURNS,
    Action,
    BrainUnavailableError,
    Decision,
    GameOverError,
    GameState,
    Message,
    Move,
    MoveKind,
    Outcome,
    Pitch,
    PlayerView,
    TurnInsight,
)
from .personas import Persona, fill_template, get_persona
from .policy import decide, interest_hint, opening_offer, patience_hint
from .voice.base import VoiceRequest
from .voice.guarded import GuardedVoice


def player_view(state: GameState, persona: Persona) -> PlayerView:
    """The only representation of a game the player (and the CLI) ever gets."""
    return PlayerView(
        id=state.id,
        investor=persona.profile,
        pitch=state.pitch,
        investor_offer=state.investor_offer,
        player_offer=state.player_offer,
        turn=state.turn,
        max_turns=MAX_TURNS,
        interest_hint=interest_hint(state.interest),
        patience_hint=patience_hint(state.patience, persona.behaviour.start_patience),
        transcript=state.transcript,
        insights=state.insights,
        options=state.options,
        outcome=state.outcome,
        final_offer=state.final_offer,
    )


class Game:
    """One negotiation. The state reference is swapped only when a turn fully succeeds."""

    def __init__(self, state: GameState, brain: InvestorBrain, voice: GuardedVoice):
        self._state = state
        self.persona = get_persona(state.persona_id)
        self.brain = brain
        self.voice = voice

    @classmethod
    def start(cls, game_id: int, pitch: Pitch, persona_id: str, brain: InvestorBrain,
              voice: GuardedVoice) -> Game:
        persona = get_persona(persona_id)
        offer = opening_offer(pitch.ask, persona)
        state = GameState(
            id=game_id,
            persona_id=persona_id,
            pitch=pitch,
            investor_offer=offer,
            interest=persona.behaviour.start_interest,
            patience=persona.behaviour.start_patience,
        )
        opening = Decision(action=Action.OPEN, investor_offer=offer, player_offer=None,
                           interest=state.interest, patience=state.patience)
        result = voice.render(cls._voice_request(persona, state, opening, (), ended=False))
        state = state.model_copy(update={
            "transcript": (Message(role="investor", text=result.reply, action=Action.OPEN.value),),
            "options": result.options,
        })
        return cls(state, brain, voice)

    @property
    def state(self) -> GameState:
        return self._state

    def view(self) -> PlayerView:
        return player_view(self._state, self.persona)

    def play(self, move: Move) -> PlayerView:
        """Apply one player move all-or-nothing and return the new view."""
        state = self._state
        if state.ended:
            raise GameOverError()
        move.validate_move()

        judgments, answers, backend, latency = None, (), "rules", 0
        if move.kind in (MoveKind.OFFER, MoveKind.MESSAGE):
            try:
                result = self.brain.judge(self._brain_context(state), move)
            except BrainError as exc:
                raise BrainUnavailableError() from exc
            judgments, answers = result.judgments, result.answers
            backend, latency = result.backend, result.latency_ms

        decision = decide(state, move, judgments, self.persona)
        turn = state.turn + 1
        outcome = decision.outcome
        out_of_turns = outcome is None and turn >= MAX_TURNS
        if out_of_turns:
            outcome = Outcome.OUT_OF_TURNS

        transcript = state.transcript + (
            Message(role="player", text=move.describe(), action=move.kind.value),
        )
        reply = self.voice.render(
            self._voice_request(self.persona, state, decision, transcript,
                                ended=outcome is not None)
        )
        transcript += (Message(role="investor", text=reply.reply, action=decision.action.value),)
        if out_of_turns:
            closing = fill_template(self.persona, "out_of_turns", amount="", equity="",
                                    startup=state.pitch.name, player_offer="")
            transcript += (
                Message(role="investor", text=closing, action=Action.OUT_OF_TURNS.value),
            )

        insight = TurnInsight(
            turn=turn,
            move=move.describe(),
            answers=answers,
            action=decision.action,
            backend=backend,
            latency_ms=latency,
            voice=f"{reply.source}{f' ({reply.note})' if reply.note else ''}",
        )
        self._state = state.model_copy(update={
            "investor_offer": decision.investor_offer,
            "player_offer": decision.player_offer,
            "interest": decision.interest,
            "patience": decision.patience,
            "turn": turn,
            "transcript": transcript,
            "insights": state.insights + (insight,),
            "options": () if outcome else reply.options,
            "outcome": outcome,
            "final_offer": decision.final_offer if outcome is Outcome.DEAL else None,
        })
        return self.view()

    def _brain_context(self, state: GameState) -> BrainContext:
        return BrainContext(
            investor=self.persona.profile,
            style=self.persona.style,
            pitch=state.pitch,
            investor_offer=state.investor_offer,
            player_offer=state.player_offer,
            transcript=state.transcript,
        )

    @staticmethod
    def _voice_request(persona: Persona, state: GameState, decision: Decision,
                       transcript: tuple[Message, ...], ended: bool) -> VoiceRequest:
        return VoiceRequest(
            investor=persona.profile,
            style=persona.style,
            templates=persona.templates,
            pitch=state.pitch,
            action=decision.action,
            reason=decision.reason,
            investor_offer=decision.investor_offer,
            player_offer=decision.player_offer,
            previous_investor_offer=state.investor_offer,
            final_offer=decision.final_offer,
            transcript=transcript,
            ended=ended,
        )
