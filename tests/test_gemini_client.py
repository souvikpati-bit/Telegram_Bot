import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors

import gemini_client

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


class FakeModels:
    def __init__(self, replies: list[Any]) -> None:
        self.replies = list(replies)
        self.calls: list[Any] = []

    async def generate_content(self, model: str, contents: Any, config: Any) -> SimpleNamespace:
        self.calls.append(contents)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(text=reply)


@pytest.fixture
def fake_models(monkeypatch: pytest.MonkeyPatch):
    def install(replies: list[Any]) -> FakeModels:
        models = FakeModels(replies)
        monkeypatch.setattr(gemini_client, "_get_client", lambda: SimpleNamespace(aio=SimpleNamespace(models=models)))
        return models

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(gemini_client.asyncio, "sleep", no_sleep)
    return install


def server_error() -> errors.ServerError:
    return errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "overloaded"}})


def test_success(fake_models) -> None:
    fake_models(['{"ok": true}'])
    assert asyncio.run(gemini_client.generate_json("p", SCHEMA, "m")) == {"ok": True}


def test_retries_server_errors_then_succeeds(fake_models) -> None:
    models = fake_models([server_error(), server_error(), '{"ok": true}'])
    assert asyncio.run(gemini_client.generate_json("p", SCHEMA, "m")) == {"ok": True}
    assert len(models.calls) == 3


def test_invalid_json_gets_one_repair(fake_models) -> None:
    models = fake_models(["not json", '{"ok": false}'])
    assert asyncio.run(gemini_client.generate_json("p", SCHEMA, "m")) == {"ok": False}
    assert "not json" in models.calls[1]


def test_invalid_json_twice_fails(fake_models) -> None:
    fake_models(["nope", '{"missing": 1}'])
    with pytest.raises(gemini_client.GeminiError):
        asyncio.run(gemini_client.generate_json("p", SCHEMA, "m"))


def test_gives_up_after_max_retries(fake_models) -> None:
    models = fake_models([server_error()] * (gemini_client.MAX_RETRIES + 1))
    with pytest.raises(gemini_client.GeminiError, match="after 3 retries"):
        asyncio.run(gemini_client.generate_json("p", SCHEMA, "m"))
    assert len(models.calls) == gemini_client.MAX_RETRIES + 1


def test_client_errors_are_not_retried_and_hide_the_key(fake_models) -> None:
    models = fake_models([errors.ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                                             "message": "bad key test-gemini-key-not-real"}})])
    with pytest.raises(gemini_client.GeminiError) as caught:
        asyncio.run(gemini_client.generate_json("p", SCHEMA, "m"))
    assert "test-gemini-key-not-real" not in str(caught.value)
    assert len(models.calls) == 1


def test_empty_transcript_is_its_own_error(fake_models) -> None:
    fake_models(['{"transcript": "  ", "clarity": "low", "languages": []}'])
    with pytest.raises(gemini_client.EmptyTranscript):
        asyncio.run(gemini_client.transcribe_audio(b"ogg", "audio/ogg", "m"))


def test_transcript_unclear_ratio() -> None:
    t = gemini_client.Transcript("one [unclear] three four", "medium", ["English"])
    assert t.unclear_ratio == 0.25


def test_render_leaves_other_braces_alone() -> None:
    assert gemini_client.render("{a} and {\"json\": 1}", a="x") == 'x and {"json": 1}'
