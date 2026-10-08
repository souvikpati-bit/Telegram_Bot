import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

import db
import gemini_client
import news
import pipeline
from conftest import add_text_note
from test_draft import GOOD_BODY
from test_triage import model_output

NOTES = json.loads((Path(__file__).parent / "fixtures" / "sample_notes.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_news(monkeypatch: pytest.MonkeyPatch) -> None:
    async def none(keywords: str, now: Any = None) -> list[news.NewsItem]:
        return []
    monkeypatch.setattr(news, "fetch_news", none)


def fake_gemini(score: float):
    async def generate_json(prompt: str, schema: dict[str, Any], model: str, **_: Any) -> dict[str, Any]:
        props = schema["properties"]
        if "parameters" in props:
            return model_output(NOTES["batch14"], score)
        if "findings" in props:
            return {"findings": [], "changes_meera_idea": False, "idea_note": "", "voice_issues": []}
        if "suggestions" in props:
            return {"suggestions": [{"topic": "T", "why_it_fits": "w", "question": "q?",
                                     "category": "Founder Story", "news_url": ""}]}
        return {"body": GOOD_BODY, "used_source_url": "", "news_relevance": "",
                "self_check": {"invented_stats": False, "on_voice": True}}
    return generate_json


def test_qualified_note_ends_as_a_draft_for_review(monkeypatch: pytest.MonkeyPatch, bot) -> None:
    monkeypatch.setattr(gemini_client, "generate_json", fake_gemini(9))
    note_id = add_text_note(NOTES["batch14"])
    assert asyncio.run(pipeline.process_note(bot, note_id)) == "drafted"
    assert db.get_note(note_id).status == "drafted"
    texts = bot.texts()
    assert "QUALIFIED FOR DRAFT" in texts[0] and "PUBLISHABILITY SCORECARD" in texts[1]
    assert texts[2].startswith("LINKEDIN DRAFT") and GOOD_BODY in texts[2]
    assert bot.sent[2]["reply_markup"] is not None
    # Telegram redelivery or a sweep must not draft it twice.
    assert asyncio.run(pipeline.process_note(bot, note_id)) == "skipped"
    assert len(bot.sent) == 3


def test_low_score_gets_scorecard_and_suggestions_only(monkeypatch: pytest.MonkeyPatch, bot) -> None:
    monkeypatch.setattr(gemini_client, "generate_json", fake_gemini(5))
    note_id = add_text_note(NOTES["clean_beauty"])
    assert asyncio.run(pipeline.process_note(bot, note_id)) == "rejected"
    assert db.get_note(note_id).status == "shelved"
    assert "Topics that would suit you better" in bot.texts()[-1]
    assert not any(t.startswith("LINKEDIN DRAFT") for t in bot.texts())


def test_gemini_down_leaves_note_for_retry_with_a_quiet_notice(monkeypatch: pytest.MonkeyPatch, bot) -> None:
    async def down(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise gemini_client.GeminiError("model call failed: ServerError 503 UNAVAILABLE")

    monkeypatch.setattr(gemini_client, "generate_json", down)
    note_id = add_text_note(NOTES["batch14"])
    assert asyncio.run(pipeline.process_note(bot, note_id)) == "error"
    assert db.get_note(note_id).status == "new"
    assert bot.texts() == [pipeline.NOTICE_AI_DOWN]

    monkeypatch.setattr(gemini_client, "generate_json", fake_gemini(9))
    assert asyncio.run(pipeline.run_sweep(bot, "sweep-test")) == "drafted"
    assert db.get_note(note_id).status == "drafted"


def test_undeliverable_scorecard_keeps_note_retryable(monkeypatch: pytest.MonkeyPatch, bot) -> None:
    monkeypatch.setattr(gemini_client, "generate_json", fake_gemini(9))
    bot.fail = True
    note_id = add_text_note(NOTES["batch14"])
    assert asyncio.run(pipeline.process_note(bot, note_id)) == "error"
    assert db.get_note(note_id).status == "new"


def test_sweep_slot_runs_once(bot) -> None:
    assert asyncio.run(pipeline.run_sweep(bot, "sweep-2026-09-25-0900")) == "no_candidate"
    assert asyncio.run(pipeline.run_sweep(bot, "sweep-2026-09-25-0900")) == "skipped"
