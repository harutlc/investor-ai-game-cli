"""Laya server compatibility, using the sample response from Laya's docs/http-api.md (v0.3.27)."""

import json

import httpx
import pytest
import respx

from investor_game.brain.base import Question
from investor_game.brain.investor import InvestorBrain
from investor_game.brain.systemone import SystemOneBackend, jev_scale_confidence, parse_answer
from investor_game.models import Move
from tests.test_brain import context, jev_responder

LAYA_URL = "http://localhost:8000/v1/systemone"

# Verbatim answers from Laya's documented /v1/systemone sample.
LAYA_CHOICE = {"type": "choice", "choice": "billing",
               "probabilities": {"billing": 0.9519, "tech": 0.0327, "other": 0.0154},
               "confidence": 0.797, "answer_confidence": 0.9519,
               "action": {"act_probability": 1.0}}
LAYA_SCORE = {"type": "score", "score": 1.6994,
              "legend": {"0": "calm", "1": "firm", "2": "angry", "3": "furious"},
              "probabilities": {"0": 0.0249, "1": 0.4136, "2": 0.3985, "3": 0.1629},
              "confidence": 0.1925, "answer_confidence": 0.4136,
              "action": {"act_probability": 1.0}}
CHOICE_Q = Question("queue", "choice", "Which team?", "Which team?",
                    criteria={"billing": "b", "tech": "t", "other": "o"})
SCORE_Q = Question("urgency", "score", "How urgent?", "How urgent?",
                   criteria=["calm", "firm", "angry", "furious"],
                   levels=("calm", "firm", "angry", "furious"))


# --- confidence -------------------------------------------------------------


def test_jev_formula_matches_typesafe_examples():
    # TypeSafe's documented answers: 0.81 and 0.92 for these distributions.
    assert jev_scale_confidence({"a": 0.88, "b": 0.12, "c": 0.0}, "a") == pytest.approx(0.82)
    assert jev_scale_confidence({"0": 0.0, "1": 0.95, "2": 0.05}, "1") == pytest.approx(0.925)


def test_laya_choice_confidence_recomputed():
    raw = parse_answer(LAYA_CHOICE, CHOICE_Q, recompute_confidence=True)
    assert raw.confidence == pytest.approx(0.928, abs=5e-4)


def test_laya_score_confidence_recomputed_and_uncertain():
    raw = parse_answer(LAYA_SCORE, SCORE_Q, recompute_confidence=True)
    assert raw.level == 1
    assert raw.confidence == pytest.approx(0.218, abs=5e-4)


def test_jev_confidence_passes_through():
    jev = {"type": "choice", "choice": "billing",
           "probabilities": {"billing": 0.88, "tech": 0.12, "other": 0.0}, "confidence": 0.81}
    assert parse_answer(jev, CHOICE_Q).confidence == 0.81


def test_missing_probabilities_fall_back():
    data = {"type": "choice", "choice": "billing", "confidence": 0.3, "answer_confidence": 0.7}
    assert parse_answer(data, CHOICE_Q, recompute_confidence=True).confidence == 0.7
    data.pop("answer_confidence")
    assert parse_answer(data, CHOICE_Q, recompute_confidence=True).confidence == 0.3


def test_noul_unaffected():
    q = Question("insult", "noul", "Insult?", "Insult?")
    raw = parse_answer({"type": "noul", "noul": 0.12, "confidence": 0.88}, q, True)
    assert raw.noul == 0.12 and raw.confidence is None


# --- request shape ----------------------------------------------------------


def laya_responder(request):
    """Answer every question like laya-serve does (full payload, extra keys included)."""
    body = json.loads(request.content)
    answers = {}
    for qid, q in body["questions"].items():
        if q["type"] == "noul":
            answers[qid] = {"type": "noul", "noul": 0.1, "confidence": 0.9,
                            "answer_confidence": 0.9, "action": {"act_probability": 1.0}}
        elif q["type"] == "choice":
            keys = list(q["criteria"])
            probs = {k: (0.4 if i == 0 else 0.6 / (len(keys) - 1)) for i, k in enumerate(keys)}
            answers[qid] = {"type": "choice", "choice": keys[0], "probabilities": probs,
                            "confidence": 0.05, "answer_confidence": 0.4}
        else:
            n = len(q["criteria"])
            probs = {str(i): (0.7 if i == 1 else 0.3 / (n - 1)) for i in range(n)}
            answers[qid] = {"type": "score", "score": 1.0, "probabilities": probs,
                            "legend": {str(i): c for i, c in enumerate(q["criteria"])},
                            "confidence": 0.3, "answer_confidence": 0.7}
    return httpx.Response(200, json={
        "model": "laya-rl-agent", "answers": answers,
        "usage": {"input_tokens": 80, "output_tokens": 0},
        "routing": {"model": "english", "repo": "convaiinnovations/laya",
                    "reason": "English Latin text"}})


@respx.mock
def test_no_model_field_by_default():
    route = respx.post(LAYA_URL).mock(side_effect=laya_responder)
    InvestorBrain(SystemOneBackend.laya()).judge(context(), Move.make_offer(500_000, 200))
    body = json.loads(route.calls.last.request.content)
    assert "model" not in body
    assert set(body) == {"state", "questions"}


@respx.mock
def test_configured_model_sent():
    route = respx.post(LAYA_URL).mock(side_effect=laya_responder)
    InvestorBrain(SystemOneBackend.laya(model="english")).judge(
        context(), Move.make_offer(500_000, 200))
    assert json.loads(route.calls.last.request.content)["model"] == "english"


@respx.mock
def test_jev_body_unchanged():
    route = respx.post("https://api.typesafe.ai/v1/systemone").mock(side_effect=jev_responder)
    InvestorBrain(SystemOneBackend.jev("k")).judge(context(), Move.make_offer(500_000, 200))
    assert json.loads(route.calls.last.request.content)["model"] == "jev-latest"


@respx.mock
def test_bearer_only_with_key():
    route = respx.post(LAYA_URL).mock(side_effect=laya_responder)
    InvestorBrain(SystemOneBackend.laya()).judge(context(), Move.make_offer(500_000, 200))
    assert "authorization" not in route.calls.last.request.headers
    InvestorBrain(SystemOneBackend.laya(api_key="local-secret")).judge(
        context(), Move.make_offer(500_000, 200))
    assert route.calls.last.request.headers["authorization"] == "Bearer local-secret"


@respx.mock
def test_full_payload_parsed_with_jev_scale_insights():
    respx.post(LAYA_URL).mock(side_effect=laya_responder)
    result = InvestorBrain(SystemOneBackend.laya()).judge(
        context(), Move.message("Please, €500k for 18%?"))
    insights = {a.id: a for a in result.answers}
    # 7 intents, p=0.4 -> (7*0.4-1)/6 = 0.3, not Laya's 0.05 entropy value.
    assert insights["intent"].confidence == pytest.approx(0.3)
    assert insights["intent"].uncertain
    # 4 levels, p=0.7 -> (4*0.7-1)/3 = 0.6
    assert insights["quality"].confidence == pytest.approx(0.6)
    assert not insights["quality"].uncertain
    assert result.backend == "laya"


# --- configuration ----------------------------------------------------------


def test_laya_settings():
    from investor_game.config import Settings, build_brain

    settings = Settings.build("laya", "stub", env={})
    assert settings.missing() == []
    assert settings.backends()["brain"] == {"backend": "laya", "model": "auto"}
    assert settings.secrets() == []
    backend = build_brain(settings).backend
    assert backend.model is None and backend.jev_confidence
    assert "authorization" not in backend._client.headers

    settings = Settings.build("laya", "stub", env={"LAYA_API_KEY": "local-secret",
                                                    "LAYA_MODEL": "english",
                                                    "LAYA_BASE_URL": "http://gpu:9000"})
    assert settings.secrets() == ["local-secret"]
    assert settings.backends()["brain"]["model"] == "english"
    backend = build_brain(settings).backend
    assert backend._client.headers["authorization"] == "Bearer local-secret"
    assert str(backend._client.base_url) == "http://gpu:9000"
    assert backend.model == "english"


# --- logging ----------------------------------------------------------------


@respx.mock
def test_laya_key_redacted_in_logs(tmp_path):
    from investor_game import llmlog
    from investor_game.config import Settings, build_brain, build_log_root

    respx.post(LAYA_URL).mock(side_effect=laya_responder)
    settings = Settings.build("laya", "stub", log_dir=tmp_path,
                              env={"LAYA_API_KEY": "local-secret"})
    game_log = build_log_root(settings).start_game(1, "rex", settings.backends())
    with llmlog.scope(game_log, 1, "offer"):
        build_brain(settings).judge(context(), Move.make_offer(500_000, 200))
    [path] = sorted((game_log.folder / "brain-laya").iterdir())
    text = path.read_text(encoding="utf-8")
    doc = json.loads(text)
    assert doc["request"]["headers"]["authorization"] == "[REDACTED]"
    assert doc["model"] == "auto"
    assert doc["response"]["body"]["routing"]["model"] == "english"  # raw payload kept
    assert "local-secret" not in text
    assert "local-secret" not in (game_log.folder / "game.json").read_text(encoding="utf-8")
