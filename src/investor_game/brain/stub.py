"""A deterministic, offline stand-in for the decision AI.

It answers the same typed questions as Jev or Laya using simple rules: keyword
lists for insults and manipulation, the offer compared with the investor's current
offer, and the investor's public traits.
"""

from __future__ import annotations

import re
from typing import Any

from .base import Question, RawAnswer

MANIPULATION_PATTERNS = (
    r"ignore (all |any |your |the |previous |prior )*(instructions|rules|prompt)",
    r"disregard (all |your |the |previous )*(instructions|rules)",
    r"system prompt",
    r"you are now",
    r"pretend (to be|you)",
    r"act as",
    r"developer mode",
    r"jailbreak",
    r"new rules?:",
    r"reveal (your )?(budget|limits?|secret)",
    r"you (must|have to) accept",
    r"you (already )?(agreed|accepted)",
    r"override",
    r"as an ai",
)
INSULT_WORDS = (
    "idiot", "stupid", "moron", "fool", "dumb", "loser", "clown", "shut up", "pathetic",
    "useless", "jerk", "greedy pig", "dinosaur", "scam artist", "imbecile", "incompetent",
)
ACCEPT_PATTERNS = (r"\bdeal\b(?! breaker)", r"\baccept", r"\bagreed\b", r"\bi'?ll take it\b",
                   r"\bsounds good\b", r"\blet'?s do it\b", r"\bshake on it\b")
WALK_PATTERNS = (r"walk(ing)? away", r"\bi'?m out\b", r"\bno deal\b", r"\bgoodbye\b",
                 r"\bforget it\b", r"\bnot interested\b")
POLITE_WORDS = ("please", "thank", "appreciate", "grateful", "kind", "respect")
CONFIDENT_WORDS = ("another fund", "other investors", "traction", "revenue", "growth",
                   "customers", "we will", "we've", "proven", "term sheet", "firm", "confident")
UNSURE_WORDS = ("maybe", "perhaps", "not sure", "i guess", "sorry", "i think", "possibly")


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, text) for p in patterns)


def _contains(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def _noul(p: float) -> RawAnswer:
    return RawAnswer(type="noul", noul=p)


def _choice(key: str, confidence: float, keys: list[str]) -> RawAnswer:
    rest = (1.0 - confidence) / max(1, len(keys) - 1)
    probabilities = {k: (confidence if k == key else rest) for k in keys}
    return RawAnswer(type="choice", choice=key, confidence=confidence, probabilities=probabilities)


def _score(level: int, confidence: float, size: int) -> RawAnswer:
    rest = (1.0 - confidence) / max(1, size - 1)
    probabilities = {str(i): (confidence if i == level else rest) for i in range(size)}
    return RawAnswer(type="score", level=level, confidence=confidence, probabilities=probabilities)


class StubBrainBackend:
    """Rule-based brain with no network access. Same input, same answers."""

    name = "stub"

    def ask(self, state: dict[str, Any], questions: list[Question]) -> dict[str, RawAnswer]:
        move = state.get("player_move", {})
        text = (move.get("text") or "").lower()
        traits = " ".join(state.get("investor", {}).get("traits", [])).lower()
        investor = (state.get("current_offers") or {}).get("investor") or {}
        candidates = state.get("offer_candidates") or {"amounts": {}, "equities": {}}

        offer = self._offer(move, candidates)
        ratio = self._ratio(offer, investor, traits)
        manipulative = _matches(text, MANIPULATION_PATTERNS)
        insulting = _contains(text, INSULT_WORDS)

        answers: dict[str, RawAnswer] = {}
        for q in questions:
            if q.id == "accept":
                answers[q.id] = _noul(self._accept_probability(ratio))
            elif q.id == "quality":
                answers[q.id] = _score(self._quality(ratio, offer, investor), 0.8, len(q.levels))
            elif q.id == "concession":
                answers[q.id] = _score(self._concession(ratio, traits), 0.75, len(q.levels))
            elif q.id == "intent":
                key, conf = self._intent(text, candidates, manipulative)
                answers[q.id] = _choice(key, conf, list(q.criteria or {}))
            elif q.id == "politeness":
                level = 0 if insulting else (2 if _contains(text, POLITE_WORDS) else 1)
                answers[q.id] = _score(level, 0.8, len(q.levels))
            elif q.id == "confidence":
                if _contains(text, UNSURE_WORDS):
                    level = 1
                elif _contains(text, CONFIDENT_WORDS):
                    level = 2
                else:
                    level = 1 if len(text) < 25 else 2
                answers[q.id] = _score(level, 0.7, len(q.levels))
            elif q.id == "insult":
                answers[q.id] = _noul(0.92 if insulting else 0.04)
            elif q.id == "manipulation":
                answers[q.id] = _noul(0.95 if manipulative else 0.03)
            elif q.id in ("offer_amount", "offer_equity"):
                keys = list(q.criteria or {})
                found = [k for k in keys if k != "none"]
                if not found:
                    answers[q.id] = _choice("none", 0.9, keys)
                else:
                    # One candidate: confident. Several: split evenly, i.e. unsure.
                    answers[q.id] = _choice(found[0], 0.95 if len(found) == 1 else 1 / len(found),
                                            keys)
        return answers

    @staticmethod
    def _offer(move: dict[str, Any], candidates: dict[str, Any]) -> tuple[float, float] | None:
        """(amount, equity %) of the move's offer, if one can be read."""
        if move.get("kind") == "structured_offer":
            return float(move["amount_eur"]), float(move["equity_percent"])
        amounts = list(candidates.get("amounts", {}).values())
        equities = list(candidates.get("equities", {}).values())
        if len(amounts) != 1 or len(equities) != 1:
            return None
        return float(amounts[0]["eur"]), float(equities[0]["percent"])

    @staticmethod
    def _ratio(offer: tuple[float, float] | None, investor: dict[str, Any], traits: str) -> float:
        """Player equity over investor equity, nudged by personality. 1.0 = same terms."""
        if offer is None or not investor:
            return 0.75
        ratio = offer[1] / float(investor["equity_percent"])
        if offer[0] > float(investor["amount_eur"]) * 1.2:
            ratio -= 0.15  # asking for more money makes the deal worse for the investor
        if "greedy" in traits or "skeptical" in traits or "impatient" in traits:
            ratio -= 0.08
        if "generous" in traits or "patient" in traits or "mission" in traits:
            ratio += 0.08
        return ratio

    @staticmethod
    def _accept_probability(ratio: float) -> float:
        return round(max(0.02, min(0.97, (ratio - 0.6) / 0.4)), 3)

    @staticmethod
    def _quality(ratio: float, offer: Any, investor: dict[str, Any]) -> int:
        if ratio >= 1.0:
            return 3
        if ratio >= 0.8:
            return 2
        if ratio >= 0.45:
            return 1
        return 0

    @staticmethod
    def _concession(ratio: float, traits: str) -> int:
        level = 2 if ratio >= 0.6 else 1
        if "greedy" in traits or "skeptical" in traits:
            level -= 1
        if "generous" in traits:
            level += 1
        return max(0, min(3, level))

    @staticmethod
    def _intent(text: str, candidates: dict[str, Any], manipulative: bool) -> tuple[str, float]:
        stripped = text.strip()
        if len(re.sub(r"[^a-z0-9]", "", stripped)) < 2:
            return "unclear", 0.4
        if candidates.get("amounts") or candidates.get("equities"):
            return "offer", 0.9
        if manipulative:
            return "argument", 0.6
        if _matches(text, WALK_PATTERNS):
            return "walk_away", 0.85
        if _matches(text, ACCEPT_PATTERNS):
            return "accept_current", 0.8
        if stripped.endswith("?"):
            return "question", 0.8
        if len(stripped) < 40 and not _contains(text, CONFIDENT_WORDS):
            return "small_talk", 0.7
        return "argument", 0.75
