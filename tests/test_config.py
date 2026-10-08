import pytest

import config
from conftest import TEST_ENV


def env(**overrides: str) -> dict[str, str]:
    return {**TEST_ENV, **overrides}


def test_missing_required_vars_are_named() -> None:
    with pytest.raises(config.ConfigError, match="GEMINI_API_KEY"):
        config.load_settings(env(GEMINI_API_KEY=""))


def test_capture_chat_must_be_a_channel_id() -> None:
    with pytest.raises(config.ConfigError, match="-100"):
        config.load_settings(env(TELEGRAM_CHAT_ID="12345"))


def test_webhook_mode_needs_https_and_secret() -> None:
    with pytest.raises(config.ConfigError, match="WEBHOOK_SECRET"):
        config.load_settings(env(PUBLIC_URL="https://example.com"))
    settings = config.load_settings(env(PUBLIC_URL="https://example.com/", WEBHOOK_SECRET="a" * 32))
    assert settings.webhook_mode and settings.public_url == "https://example.com"


def test_vercel_requires_database_and_cron_secret() -> None:
    with pytest.raises(config.ConfigError, match="DATABASE_URL"):
        config.load_settings(env(VERCEL="1", WEBHOOK_SECRET="a" * 32, CRON_SECRET="b" * 32))


def test_secrets_are_masked() -> None:
    text = repr(config.load_settings(env()))
    assert TEST_ENV["TELEGRAM_BOT_TOKEN"] not in text
    assert TEST_ENV["GEMINI_API_KEY"] not in text


def test_defaults_apply() -> None:
    settings = config.load_settings(env())
    assert settings.triage_threshold == 8.0
    assert settings.draft_min_chars == 200 and settings.draft_max_chars == 3000
