import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import draft
import gemini_client
import news

NOTES = json.loads((Path(__file__).parent / "fixtures" / "sample_notes.json").read_text(encoding="utf-8"))
NOTE = NOTES["batch14"]
NO_ISSUES = {"invented_stats": False, "on_voice": True}

GOOD_BODY = (
    "Batch fourteen of our barrier cream came back from stability testing with the pH down by 0.4 units. "
    "The only thing we had changed was the preservative supplier. Same preservative, same percentage on paper.\n\n"
    "Their grade turned out to carry a different buffer. Nobody would ever see that on the label, because the "
    "ingredient list is identical. That is the part I keep thinking about.\n\n"
    "I'm not saying ingredient lists are useless. I'm saying they tell you what is in the jar, not which grade, "
    "which supplier or which raw material specification it came from. If you want to know more, ask the brand "
    "how they qualify a change of supplier."
)


def test_good_body_passes() -> None:
    assert draft.validate(GOOD_BODY, "", NO_ISSUES, NOTE, []) == []


def test_fabricated_statistic_is_caught() -> None:
    body = GOOD_BODY.replace("That is the part", "A 2026 study of 5,000 women found 38% react to it. That is the part")
    problems = draft.validate(body, "", NO_ISSUES, NOTE, [])
    assert any("numbers not in the note" in p and "5,000" in p and "38" in p for p in problems)
    assert any("cites research" in p for p in problems)


def test_spoken_numbers_in_the_note_are_allowed() -> None:
    assert draft.known_numbers("batch fourteen and a drop of zero point four") >= {"14", "0.4"}
    assert "4" not in draft.known_numbers("zero point four")


def test_invented_timing_is_caught() -> None:
    body = GOOD_BODY.replace("Batch fourteen", "Last week, batch fourteen")
    assert any("timing" in p for p in draft.validate(body, "", NO_ISSUES, NOTE, []))


def test_source_url_must_be_one_that_was_fetched() -> None:
    problems = draft.validate(GOOD_BODY, "https://invented.example/story", NO_ISSUES, NOTE, [])
    assert any("never invent a source" in p for p in problems)


def test_cited_headline_licenses_its_numbers() -> None:
    item = news.NewsItem("CDSCO flags 12 cosmetic brands", "Mint", "https://example.com/a", datetime.now(UTC))
    body = GOOD_BODY + "\n\nMint reported that the regulator flagged 12 brands."
    assert draft.validate(body, item.url, NO_ISSUES, NOTE, [item]) == []


@pytest.mark.parametrize("extra, expected", [
    (" Love this ✨", "emoji"),
    (" #skincare", "hashtags"),
    (" See www.example.com", "link"),
    (" Let me know what you think.", "call to action"),
    (" This is a game-changer.", "cliché"),
])
def test_negative_voice_rules(extra: str, expected: str) -> None:
    problems = draft.validate(GOOD_BODY + extra, "", NO_ISSUES, NOTE, [])
    assert any(expected in p for p in problems)


def test_self_check_and_length() -> None:
    assert any("invented" in p for p in draft.validate(GOOD_BODY, "", {"invented_stats": True}, NOTE, []))
    assert any("length" in p for p in draft.validate("Too short.", "", NO_ISSUES, NOTE, []))


def test_lists_and_one_liners_are_rejected() -> None:
    listed = GOOD_BODY + "\n\n- first point\n- second point"
    assert any("lists" in p for p in draft.validate(listed, "", NO_ISSUES, NOTE, []))


def test_normalise_fixes_spelling_dashes_and_bold() -> None:
    assert draft.normalise("**Color** — the moisturizer") == "Colour - the moisturiser"


def test_exemplars_prefer_category_and_include_linkedin() -> None:
    picked = draft.pick_exemplars("Brand Philosophy")
    assert picked[0].category == "Brand Philosophy"
    assert any(p.format == "linkedin" for p in picked)
    assert len(picked) == draft.EXEMPLAR_COUNT


def test_newsletter_greeting_and_signoff_are_stripped() -> None:
    piece = next(p for p in draft.load_corpus() if p.format == "newsletter")
    text = draft.format_exemplar(piece)
    assert "\nHi,\n" not in text and not text.rstrip().endswith("Meera")


def test_draft_prompt_has_no_unfilled_placeholders() -> None:
    prompt = draft.build_prompt(NOTE, "Industry Transparency", "angle", draft.pick_exemplars(None), [])
    for name in ("voice_skill", "category", "angle", "core_idea", "exemplars", "note", "news", "feedback"):
        assert "{" + name + "}" not in prompt


class ScriptedModel:
    """Draft replies in order; QA always passes."""

    def __init__(self, bodies: list[str]) -> None:
        self.bodies = list(bodies)
        self.prompts: list[str] = []

    async def __call__(self, prompt: str, schema: dict[str, Any], model: str, **_: Any) -> dict[str, Any]:
        if "findings" in schema["properties"]:
            return {"findings": [], "changes_meera_idea": False, "idea_note": "same idea", "voice_issues": []}
        self.prompts.append(prompt)
        return {"body": self.bodies.pop(0), "used_source_url": "", "news_relevance": "", "self_check": NO_ISSUES}


def test_redraft_gets_the_exact_problems_then_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ScriptedModel([GOOD_BODY + " In 2019, 62% of brands did this.", GOOD_BODY])
    monkeypatch.setattr(gemini_client, "generate_json", fake)
    result = asyncio.run(draft.make_draft(NOTE, None, "", draft.pick_exemplars(None)))
    assert result is not None and result.body == GOOD_BODY and result.qa["passed"]
    assert "62" in fake.prompts[1] and "rejected" in fake.prompts[1]


def test_fails_closed_when_every_attempt_is_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = GOOD_BODY + " Research shows 90% of people agree."
    monkeypatch.setattr(gemini_client, "generate_json", ScriptedModel([bad] * 5))
    assert asyncio.run(draft.make_draft(NOTE, None, "", draft.pick_exemplars(None))) is None


def test_blocking_fact_check_finding_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    async def qa(prompt: str, schema: dict[str, Any], model: str, **_: Any) -> dict[str, Any]:
        return {"findings": [{"claim": "the buffer was citrate", "severity": "blocking", "why": "not in note"},
                             {"claim": "framing", "severity": "unclear", "why": "?"}],
                "changes_meera_idea": False, "idea_note": "", "voice_issues": []}

    monkeypatch.setattr(gemini_client, "generate_json", qa)
    problems, record = asyncio.run(draft.fact_check(GOOD_BODY, NOTE))
    assert len(problems) == 2  # anything not clearly "minor" is blocking
    assert not record["passed"]
