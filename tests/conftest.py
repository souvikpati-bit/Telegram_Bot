"""Shared test setup. config reads the environment at import, so fake values are set first."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

TEST_ENV = {
    "TELEGRAM_BOT_TOKEN": "123456:TEST-TOKEN-not-real",
    "TELEGRAM_CHAT_ID": "-1001234567890",
    "TELEGRAM_REVIEW_CHAT_ID": "4242",
    "MEERA_USER_ID": "4242",
    "GEMINI_API_KEY": "test-gemini-key-not-real",
    "PUBLIC_URL": "",
    "DATABASE_URL": "",
    "VERCEL": "",
}
for _name, _value in TEST_ENV.items():
    os.environ[_name] = _value

import db  # noqa: E402  (must follow the environment setup)

CAPTURE_CHAT = int(TEST_ENV["TELEGRAM_CHAT_ID"])
MEERA = int(TEST_ENV["MEERA_USER_ID"])
NOW = datetime(2026, 9, 25, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path) -> None:
    db.init_db(tmp_path / "test.db")


class FakeBot:
    """Records every message instead of calling Telegram."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.fail = False

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> SimpleNamespace:
        if self.fail:
            from telegram.error import Forbidden
            raise Forbidden("bot was blocked by the user")
        self.sent.append({"chat_id": chat_id, "text": text, **kwargs})
        return SimpleNamespace(message_id=1000 + len(self.sent))

    def texts(self) -> list[str]:
        return [m["text"] for m in self.sent]


@pytest.fixture
def bot() -> FakeBot:
    return FakeBot()


def add_text_note(text: str, message_id: int = 1) -> int:
    note_id = db.add_note(message_id, CAPTURE_CHAT, text, NOW)
    assert note_id is not None
    return note_id
