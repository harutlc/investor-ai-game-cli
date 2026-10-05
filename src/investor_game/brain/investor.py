"""The investor's brain: asks the per-move questions and turns answers into Judgments."""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..models import Answer, Judgments, Move, MoveKind
from .base import BrainBackend, BrainError, Question, RawAnswer, build_insight_answers
from .extraction import Candidates, find_candidates
from .questions import BrainContext, build_questions, build_state


@dataclass(frozen=True)
class BrainResult:
    judgments: Judgments
    answers: tuple[Answer, ...]
    backend: str
    latency_ms: int


def _need(answers: dict[str, RawAnswer], question: Question) -> RawAnswer:
    raw = answers.get(question.id)
    if raw is None or raw.type != question.type:
        raise BrainError(f"missing or mistyped answer for {question.id!r}")
    levels = len(question.levels)
    if question.type == "score" and (raw.level is None or not 0 <= raw.level < levels):
        raise BrainError(f"score answer out of range for {question.id!r}")
    if question.type == "choice":
        keys = question.criteria if isinstance(question.criteria, dict) else {}
        if raw.choice not in keys:
            raise BrainError(f"unknown choice for {question.id!r}")
    if question.type == "noul" and raw.noul is None:
        raise BrainError(f"missing probability for {question.id!r}")
    return raw


def interpret(questions: list[Question], answers: dict[str, RawAnswer], move: Move,
              candidates: Candidates) -> Judgments:
    by_id = {q.id: q for q in questions}
    raw = {q.id: _need(answers, q) for q in questions}

    def level(qid: str) -> str:
        return by_id[qid].levels[raw[qid].level]  # type: ignore[index]

    def conf(qid: str) -> float:
        value = raw[qid].confidence
        return 0.0 if value is None else float(value)

    values: dict = {
        "accept_probability": float(raw["accept"].noul),  # type: ignore[arg-type]
        "quality": level("quality"),
        "concession": level("concession"),
    }
    if move.kind is MoveKind.MESSAGE:
        extraction_confidences = [conf(q) for q in ("offer_amount", "offer_equity") if q in raw]
        values.update(
            intent=raw["intent"].choice,
            intent_confidence=conf("intent"),
            politeness=level("politeness"),
            assertiveness=level("confidence"),
            insult_probability=float(raw["insult"].noul),  # type: ignore[arg-type]
            manipulation_probability=float(raw["manipulation"].noul),  # type: ignore[arg-type]
            has_offer_candidates=candidates.any,
            extraction_confidence=min(extraction_confidences, default=1.0),
            offer=candidates.offer_from(
                raw["offer_amount"].choice if "offer_amount" in raw else None,
                raw["offer_equity"].choice if "offer_equity" in raw else None,
            ),
        )
    return Judgments(**values)


class InvestorBrain:
    """Wraps a backend (Jev, Laya or stub) with the game's questions and interpretation."""

    def __init__(self, backend: BrainBackend):
        self.backend = backend

    @property
    def name(self) -> str:
        return self.backend.name

    def judge(self, context: BrainContext, move: Move) -> BrainResult:
        is_message = move.kind is MoveKind.MESSAGE
        candidates = find_candidates(move.text or "") if is_message else Candidates()
        state = build_state(context, move, candidates)
        questions = build_questions(move, candidates)
        started = time.perf_counter()
        answers = self.backend.ask(state, questions)
        latency_ms = int((time.perf_counter() - started) * 1000)
        judgments = interpret(questions, answers, move, candidates)
        return BrainResult(
            judgments=judgments,
            answers=build_insight_answers(questions, answers),
            backend=self.backend.name,
            latency_ms=latency_ms,
        )
