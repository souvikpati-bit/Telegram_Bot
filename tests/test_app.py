import asyncio
import json
import logging
from typing import Any

import app
import config


def call(method: str, path: str, headers: dict[str, str] | None = None, body: bytes = b"") -> tuple[int, str]:
    sent: list[dict[str, Any]] = []
    scope = {"type": "http", "method": method, "path": path,
             "headers": [(k.encode(), v.encode()) for k, v in (headers or {}).items()]}

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(app.asgi_app(scope, receive, send))
    return sent[0]["status"], sent[1]["body"].decode()


def test_health_and_unknown_routes() -> None:
    assert call("GET", "/healthz") == (200, "ok")
    assert call("GET", "/anything")[0] == 404


def test_webhook_requires_the_secret_header(monkeypatch) -> None:
    secret = "s" * 32
    monkeypatch.setattr(config, "settings", config.load_settings({**__import__("conftest").TEST_ENV,
                                                                  "WEBHOOK_SECRET": secret}))
    assert app.parse_webhook(None, b"{}", None)[0] == 403
    assert app.parse_webhook("wrong", b"{}", None)[0] == 403
    assert app.parse_webhook(secret, b"not json", None)[0] == 400
    status, update = app.parse_webhook(secret, json.dumps({"update_id": 5}).encode(), None)
    assert status == 200 and update.update_id == 5


def test_secrets_are_redacted_from_logs() -> None:
    record = logging.LogRecord("x", logging.INFO, "", 0, "token=%s", ("123456:TEST-TOKEN-not-real",), None)
    app.RedactSecrets(["123456:TEST-TOKEN-not-real"]).filter(record)
    assert record.getMessage() == "token=***"


def test_assets_are_present() -> None:
    app.check_assets()
