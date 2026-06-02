from unittest.mock import patch, AsyncMock

import httpx
import pytest

from app.scrapers.base import BaseScraper, ScrapedArticle


class ConcreteScraper(BaseScraper):
    async def extract_body(self, url: str, client: httpx.AsyncClient) -> str:
        return f"Extracted body from {url}"


class _MockFeed:
    def __init__(self, entries=None):
        self.entries = entries or []


class TestBaseScraper:
    @pytest.mark.asyncio
    async def test_fetch_rss_parses_entries(self):
        scraper = ConcreteScraper(rss_url="http://example.com/feed.xml")
        mock_feed = _MockFeed([
            {"title": "Test Article", "link": "http://example.com/article1", "published": "Mon, 01 Jan 2024 00:00:00 GMT", "summary": "Summary text"},
        ])
        with patch("feedparser.parse", return_value=mock_feed):
            entries = await scraper.fetch_rss()
            assert len(entries) == 1
            assert entries[0]["title"] == "Test Article"

    @pytest.mark.asyncio
    async def test_fetch_rss_empty_feed(self):
        scraper = ConcreteScraper(rss_url="http://example.com/feed.xml")
        with patch("feedparser.parse", return_value=_MockFeed([])):
            entries = await scraper.fetch_rss()
            assert entries == []

    @pytest.mark.asyncio
    async def test_fetch_rss_missing_fields(self):
        scraper = ConcreteScraper(rss_url="http://example.com/feed.xml")
        mock_feed = _MockFeed([{"title": "No Link"}, {}, {"link": "http://example.com/3"}])
        with patch("feedparser.parse", return_value=mock_feed):
            entries = await scraper.fetch_rss()
            assert len(entries) == 3
            assert entries[0]["title"] == "No Link"
            assert entries[0]["link"] == ""
            assert entries[1]["title"] == ""

    @pytest.mark.asyncio
    async def test_scrape_returns_scraped_articles(self):
        scraper = ConcreteScraper(rss_url="http://example.com/feed.xml")
        mock_feed = _MockFeed([
            {"title": "Article 1", "link": "http://example.com/1", "published": "Mon, 01 Jan 2024 00:00:00 GMT", "summary": "Summary 1"},
            {"title": "Article 2", "link": "http://example.com/2", "published": "Tue, 02 Jan 2024 00:00:00 GMT", "summary": "Summary 2"},
        ])
        with patch("feedparser.parse", return_value=mock_feed):
            with patch("asyncio.sleep"):
                articles = await scraper.scrape()
                assert len(articles) == 2
                assert all(isinstance(a, ScrapedArticle) for a in articles)
                assert articles[0].headline == "Article 1"

    @pytest.mark.asyncio
    async def test_scrape_skips_empty_body(self):
        class EmptyBodyScraper(BaseScraper):
            async def extract_body(self, url: str, client: httpx.AsyncClient) -> str:
                return ""

        scraper = EmptyBodyScraper(rss_url="http://example.com/feed.xml")
        mock_feed = _MockFeed([
            {"title": "Skip Me", "link": "http://example.com/1", "published": "Mon, 01 Jan 2024 00:00:00 GMT", "summary": ""},
        ])
        with patch("feedparser.parse", return_value=mock_feed):
            with patch("asyncio.sleep"):
                articles = await scraper.scrape()
                assert articles == []

    @pytest.mark.asyncio
    async def test_scrape_source_name_derived_from_class(self):
        class CustomScraper(BaseScraper):
            async def extract_body(self, url, client):
                return "Body"

        scraper = CustomScraper(rss_url="http://example.com/feed.xml")
        mock_feed = _MockFeed([
            {"title": "Test", "link": "http://example.com/1", "published": "Mon, 01 Jan 2024 00:00:00 GMT", "summary": ""},
        ])
        with patch("feedparser.parse", return_value=mock_feed):
            with patch("asyncio.sleep"):
                articles = await scraper.scrape()
                assert articles[0].source == "custom"

    @pytest.mark.asyncio
    async def test_scrape_rate_limit_respected(self):
        scraper = ConcreteScraper(rss_url="http://example.com/feed.xml", rate_limit_delay=0.5)
        mock_feed = _MockFeed([
            {"title": "A", "link": "http://example.com/1", "published": "", "summary": ""},
            {"title": "B", "link": "http://example.com/2", "published": "", "summary": ""},
        ])
        with patch("feedparser.parse", return_value=mock_feed):
            with patch("asyncio.sleep") as mock_sleep:
                await scraper.scrape()
                assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_extract_body_http_error_returns_empty(self):
        class FailingScraper(BaseScraper):
            async def extract_body(self, url: str, client: httpx.AsyncClient) -> str:
                raise httpx.HTTPStatusError("Error", request=AsyncMock(), response=AsyncMock())

        scraper = FailingScraper(rss_url="http://example.com/feed.xml")
        mock_feed = _MockFeed([
            {"title": "Fail", "link": "http://example.com/fail", "published": "", "summary": ""},
        ])
        with patch("feedparser.parse", return_value=mock_feed):
            with patch("asyncio.sleep"):
                articles = await scraper.scrape()
                assert articles == []


class TestTheHinduScraper:
    def test_import_and_defaults(self):
        from app.scrapers.the_hindu import TheHinduScraper
        scraper = TheHinduScraper()
        assert "thehindu.com" in scraper.rss_url
        assert scraper.rate_limit_delay == 1.0

    @pytest.mark.asyncio
    async def test_extract_body_parses_html(self):
        from app.scrapers.the_hindu import TheHinduScraper
        scraper = TheHinduScraper()
        mock_response = AsyncMock()
        mock_response.text = "<html><body><article><p>Test content</p></article></body></html>"
        mock_response.raise_for_status = AsyncMock()
        client = AsyncMock()
        client.get = AsyncMock(return_value=mock_response)
        body = await scraper.extract_body("http://example.com", client)
        assert isinstance(body, str)

    @pytest.mark.asyncio
    async def test_extract_body_http_error_returns_empty(self):
        from app.scrapers.the_hindu import TheHinduScraper
        scraper = TheHinduScraper()
        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.HTTPStatusError("Error", request=AsyncMock(), response=AsyncMock()))
        body = await scraper.extract_body("http://example.com", client)
        assert body == ""


class TestIndianExpressScraper:
    def test_import_and_defaults(self):
        from app.scrapers.indian_express import IndianExpressScraper
        scraper = IndianExpressScraper()
        assert "indianexpress.com" in scraper.rss_url
        assert scraper.rate_limit_delay == 1.0

    @pytest.mark.asyncio
    async def test_extract_body_timeout_returns_empty(self):
        from app.scrapers.indian_express import IndianExpressScraper
        scraper = IndianExpressScraper()
        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        body = await scraper.extract_body("http://example.com", client)
        assert body == ""
