import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

import db
import gemini_client
import triage
from conftest import add_text_note

NOTES = json.loads((Path(__file__).parent / "fixtures" / "sample_notes.json").read_text(encoding="utf-8"))


def model_output(note: str, score: float, guardrail: str = "pass", evidence: str | None = None,
                 flags: list[dict[str, str]] | None = None) -> dict[str, Any]:
    quote = evidence if evidence is not None else " ".join(note.split()[:6])
    return {
        "summary": {"core_idea": "idea", "founder_perspective": "fp", "intended_audience": "aud",
                    "main_insight": "insight", "topic": "topic"},
        "parameters": [{"key": k, "score": score, "reason": "r", "evidence": quote, "gap": f"gap {k}",
                        "guardrail": guardrail, "guardrail_note": ""} for k in triage.PARAMETER_KEYS],
        "hard_flags": flags or [],
        "category": "Industry Transparency",
        "suggested_angle": "angle",
        "news_keywords": "preservative supplier; skincare!",
    }


def test_every_prompt_placeholder_is_filled() -> None:
    prompt = triage.build_prompt(NOTES["batch14"])
    for placeholder in ("{parameters}", "{flag_types}", "{categories}", "{published}", "{note}"):
        assert placeholder not in prompt


def test_weighted_overall_is_reproducible() -> None:
    note = db.get_note(add_text_note(NOTES["batch14"]))
    result = triage.parse_assessment(note, model_output(note.content, 9), "m")
    assert result.overall == 9.0
    assert result.decision == triage.QUALIFIED


def test_threshold_is_strictly_above() -> None:
    assert triage.decide(8.0, []) == triage.REJECTED
    assert triage.decide(8.1, []) == triage.QUALIFIED
    assert triage.decide(9.9, [{"type": "defamatory"}]) == triage.HUMAN_REVIEW


def test_unverified_evidence_caps_the_score() -> None:
    note = db.get_note(add_text_note(NOTES["batch14"]))
    result = triage.parse_assessment(note, model_output(note.content, 10, evidence="words she never said at all"), "m")
    assert all(p.score == triage.EVIDENCE_CAP for p in result.parameters)
    assert result.decision == triage.REJECTED


def test_guardrail_caps_apply() -> None:
    note = db.get_note(add_text_note(NOTES["batch14"]))
    result = triage.parse_assessment(note, model_output(note.content, 10, guardrail="warn"), "m")
    assert result.overall == 6.0


def test_personal_data_forces_human_review() -> None:
    text = NOTES["layering"] + " Her number is 98765 43210 if we need to follow up."
    note = db.get_note(add_text_note(text))
    result = triage.parse_assessment(note, model_output(note.content, 10), "m")
    assert result.decision == triage.HUMAN_REVIEW
    assert result.hard_flags[0]["type"] == "personal_data_detected"


def test_incomplete_model_output_is_rejected() -> None:
    note = db.get_note(add_text_note(NOTES["batch14"]))
    data = model_output(note.content, 9)
    data["parameters"] = data["parameters"][:-1]
    assert triage.parse_assessment(note, data, "m") is None


def test_keywords_are_sanitised() -> None:
    assert triage.clean_keywords("preservative supplier; skincare!") == "preservative supplier skincare"


def test_short_note_is_rejected_without_a_model_call(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("no model call expected")

    monkeypatch.setattr(gemini_client, "generate_json", boom)
    note = db.get_note(add_text_note("too short"))
    result = asyncio.run(triage.assess_note(note))
    assert result.decision == triage.REJECTED and result.model == "code"


def test_assessment_is_stored_and_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    async def fake(prompt: str, schema: dict[str, Any], model: str) -> dict[str, Any]:
        calls.append(prompt)
        return model_output(NOTES["batch14"], 9)

    monkeypatch.setattr(gemini_client, "generate_json", fake)
    note = db.get_note(add_text_note(NOTES["batch14"]))
    first = asyncio.run(triage.assess_note(note))
    second = asyncio.run(triage.assess_note(db.get_note(note.id)))
    assert len(calls) == 1
    assert first.overall == second.overall == 9.0
    assert db.get_note(note.id).category == "Industry Transparency"


def test_suggestions_only_keep_fetched_news_urls() -> None:
    import news
    headline = news.NewsItem("Sunscreen rules tighten", "Mint", "https://example.com/real", None)
    data = {"suggestions": [
        {"topic": "A", "why_it_fits": "w", "question": "q?", "category": "Founder Story", "news_url": "https://example.com/real"},
        {"topic": "B", "why_it_fits": "w", "question": "q?", "category": "Made Up", "news_url": "https://fake.example/x"},
        {"topic": "", "why_it_fits": "w", "question": "q?", "category": "Founder Story", "news_url": ""},
    ]}
    parsed = triage.parse_suggestions(data, [headline])
    assert [s["topic"] for s in parsed] == ["A", "B"]
    assert parsed[0]["news_source"] == "Mint"
    assert parsed[1]["news_url"] == "" and parsed[1]["category"] == ""
