"""Brain interfaces: typed questions in, typed answers out. The brain never writes chat."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from ..models import Answer

QuestionType = Literal["noul", "choice", "score"]


class BrainError(RuntimeError):
    """The decision AI failed (timeout, connection, bad status or malformed answer)."""


@dataclass(frozen=True)
class Question:
    """One System One question.

    ``levels`` names the ordered Score levels (``criteria`` holds their descriptions);
    for a Choice the criteria keys are the answers.
    """

    id: str
    type: QuestionType
    instructions: str | dict[str, Any] | list[Any]
    summary: str  # plain-language version for Brain insights
    criteria: dict[str, str] | list[str] | None = None
    levels: tuple[str, ...] = ()

    def to_api(self) -> dict[str, Any]:
        body: dict[str, Any] = {"type": self.type, "instructions": self.instructions}
        if self.criteria is not None:
            body["criteria"] = self.criteria
        return body


@dataclass(frozen=True)
class RawAnswer:
    """A backend's answer to one question, normalised across backends."""

    type: QuestionType
    noul: float | None = None  # probability of yes
    choice: str | None = None  # chosen key
    level: int | None = None  # chosen score level index
    confidence: float | None = None
    probabilities: dict[str, float] = field(default_factory=dict)


class BrainBackend(Protocol):
    """Something that can answer a batch of System One questions over one state."""

    name: str

    def ask(self, state: dict[str, Any], questions: list[Question]) -> dict[str, RawAnswer]:
        """Answer every question or raise ``BrainError``."""
        ...


def answer_label(question: Question, raw: RawAnswer) -> str:
    """Human-readable answer for Brain insights."""
    if question.type == "noul":
        return "yes" if (raw.noul or 0.0) >= 0.5 else "no"
    if question.type == "score":
        return question.levels[raw.level] if raw.level is not None else "?"
    if (
        question.id.startswith("offer_")
        and isinstance(question.criteria, dict)
        and raw.choice in question.criteria
        and raw.choice != "none"
    ):
        # Show the candidate number, e.g. '€500k ("€500k")', rather than its key.
        return question.criteria[raw.choice].removeprefix("The player offers ")
    return (raw.choice or "?").replace("_", " ")


def answer_confidence(raw: RawAnswer) -> float:
    if raw.type == "noul":
        return float(raw.noul or 0.0)
    return float(raw.confidence if raw.confidence is not None else 0.0)


def build_insight_answers(
    questions: list[Question], answers: dict[str, RawAnswer]
) -> tuple[Answer, ...]:
    """One insights ``Answer`` per question, in question order."""
    return tuple(
        Answer(
            id=q.id,
            question=q.summary,
            kind=q.type,
            value=answer_label(q, answers[q.id]),
            confidence=round(answer_confidence(answers[q.id]), 4),
        )
        for q in questions
        if q.id in answers
    )
