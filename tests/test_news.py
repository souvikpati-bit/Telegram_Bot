import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

import news

NOW = datetime(2026, 9, 25, 9, 0, tzinfo=UTC)


def rss(*items: tuple[str, str, str, datetime]) -> bytes:
    entries = "".join(
        f"<item><title>{title} - {source}</title><link>{url}</link>"
        f"<pubDate>{format_datetime(published)}</pubDate><source url=\"https://x\">{source}</source></item>"
        for title, source, url, published in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{entries}</channel></rss>'.encode()


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch):
    def install(handler) -> None:
        monkeypatch.setattr(news, "_transport", httpx.MockTransport(handler))
    return install


def test_keeps_only_recent_credible_relevant_items(transport) -> None:
    body = rss(
        ("Sunscreen labelling rules tightened for SPF claims", "Mint", "https://a.example/1", NOW - timedelta(days=2)),
        ("Sunscreen brand launches SPF range", "Some Press Wire", "https://a.example/2", NOW - timedelta(days=1)),
        ("Sunscreen testing standards under review", "Reuters", "https://a.example/3", NOW - timedelta(days=40)),
        ("Cricket scores", "Mint", "https://a.example/4", NOW),
    )
    transport(lambda request: httpx.Response(200, content=body))
    items = asyncio.run(news.fetch_news("sunscreen labelling", now=NOW))
    assert [i.url for i in items] == ["https://a.example/1"]
    assert items[0].title == "Sunscreen labelling rules tightened for SPF claims"


def test_failure_degrades_to_no_news(transport, monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(news.asyncio, "sleep", no_sleep)
    transport(lambda request: httpx.Response(503))
    assert asyncio.run(news.fetch_news("sunscreen labelling", now=NOW)) == []


def test_generic_keywords_make_no_request(transport) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")
    transport(handler)
    assert asyncio.run(news.fetch_news("india news", now=NOW)) == []
