import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import db
import ingest
from conftest import CAPTURE_CHAT


def message(text: str | None = None, chat_id: int = CAPTURE_CHAT, message_id: int = 1, **media: Any) -> SimpleNamespace:
    fields = {"voice": None, "audio": None, "video_note": None, "document": None, "caption": None}
    fields.update(media)
    return SimpleNamespace(text=text, chat=SimpleNamespace(id=chat_id), message_id=message_id,
                           date=datetime(2026, 9, 25, tzinfo=UTC), from_user=None, author_signature=None,
                           sender_chat=SimpleNamespace(id=chat_id), **fields)


def post(msg: SimpleNamespace) -> int | None:
    update = SimpleNamespace(channel_post=msg, update_id=1)
    return asyncio.run(ingest.handle_channel_post(update, SimpleNamespace(bot=None)))


def test_text_post_becomes_a_new_note_once() -> None:
    note_id = post(message("An idea about preservative grades"))
    assert db.get_note(note_id).status == "new"
    assert post(message("An idea about preservative grades")) is None  # redelivery


def test_other_chats_are_ignored() -> None:
    assert post(message("hello", chat_id=-100999)) is None
    assert db.get_new_notes() == []


def test_blank_text_is_skipped_and_stickers_are_unsupported() -> None:
    assert post(message("   ")) is None
    assert post(message(None, message_id=2)) is None
    assert ingest.extract_note(message(None)).content_type == "unsupported"


def test_voice_note_waits_for_transcription() -> None:
    voice = SimpleNamespace(file_id="file-1", mime_type="audio/ogg")
    note = ingest.extract_note(message(None, voice=voice))
    assert (note.content_type, note.status, note.tg_file_id) == ("voice", "pending_transcription", "file-1")
