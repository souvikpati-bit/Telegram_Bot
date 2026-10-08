import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

import db
import review
from conftest import MEERA, add_text_note


class FakeMessage:
    is_accessible = True

    def __init__(self) -> None:
        self.replies: list[str] = []
        self.markup_removed = False

    async def reply_text(self, text: str, **kwargs: Any) -> None:
        self.replies.append(text)

    async def edit_reply_markup(self, reply_markup: Any = None) -> None:
        self.markup_removed = True


class FakeQuery:
    def __init__(self, data: str, user_id: int) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = FakeMessage()
        self.answers: list[tuple[str | None, bool]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append((text, show_alert))


def press(data: str, user_id: int = MEERA) -> FakeQuery:
    query = FakeQuery(data, user_id)
    update = SimpleNamespace(callback_query=query)
    asyncio.run(review.handle_callback(update, SimpleNamespace(bot=None)))
    return query


def make_draft() -> int:
    note_id = add_text_note("a note that was drafted")
    return db.add_draft(note_id, "The AI draft body.", "model-x", [1], None, None, None)


def test_only_meera_can_press_buttons() -> None:
    draft_id = make_draft()
    query = press(f"approve:{draft_id}", user_id=999)
    assert query.answers == [(review.NOT_AUTHORISED, True)]
    assert db.get_draft(draft_id).status == "pending_review"


def test_approve_returns_copy_ready_text_once() -> None:
    draft_id = make_draft()
    query = press(f"approve:{draft_id}")
    assert db.get_draft(draft_id).status == "approved"
    assert "The AI draft body." in query.message.replies[0]
    assert query.message.markup_removed
    assert press(f"approve:{draft_id}").answers == [(review.ALREADY_HANDLED, False)]


def test_reject_shelves_the_note() -> None:
    draft_id = make_draft()
    press(f"reject:{draft_id}")
    d = db.get_draft(draft_id)
    assert d.status == "discarded"
    assert db.get_note(d.note_id).status == "shelved"


def test_edit_then_full_rewrite_is_kept_verbatim(bot) -> None:
    draft_id = make_draft()
    press(f"edit:{draft_id}")
    rewrite = "My own version, word for word. " * 10
    message = SimpleNamespace(text=rewrite, from_user=SimpleNamespace(id=MEERA),
                              chat=SimpleNamespace(id=MEERA), reply_text=FakeMessage().reply_text)
    asyncio.run(review.handle_review_message(SimpleNamespace(message=message), SimpleNamespace(bot=bot)))
    new = db.get_draft(draft_id + 1)
    assert new.body == rewrite.strip() and new.model == db.MEERA_EDIT_MODEL
    assert bot.sent and "your edit" in bot.sent[0]["text"]


def test_draft_message_never_implies_auto_posting() -> None:
    d = db.get_draft(make_draft())
    text = review.format_for_review(d, db.get_note(d.note_id))
    assert "Nothing is posted anywhere unless you post it yourself." in text


def test_undelivered_drafts_are_retried(bot) -> None:
    draft_id = make_draft()
    bot.fail = True
    assert asyncio.run(review.deliver_waiting(bot)) == 0
    bot.fail = False
    assert asyncio.run(review.deliver_waiting(bot)) == 1
    assert db.get_draft(draft_id).review_message_id is not None
    assert asyncio.run(review.deliver_waiting(bot)) == 0
