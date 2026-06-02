"""Tests for scraper base class and implementations."""
from unittest.mock import patch

import httpx
import pytest

from app.scrapers.base import BaseScraper, ScrapedArticle


class ConcreteScraper(BaseScraper):
    async def extract_body(self, url: str, client: httpx.AsyncClient) -> str:
        return f"Extracted body from {url}"


class _MockFeed:
    def __init__(self, entries):
        self.entries = entries


class TestBaseScraper:
    @pytest.mark.asyncio
    async def test_fetch_rss_parses_entries(self):
        scraper = ConcreteScraper(rss_url="http://example.com/feed.xml")

        mock_feed = _MockFeed([
            {
                "title": "Test Article",
                "link": "http://example.com/article1",
                "published": "Mon, 01 Jan 2024 00:00:00 GMT",
                "summary": "Summary text",
            }
        ])

        with patch("feedparser.parse", return_value=mock_feed):
            entries = await scraper.fetch_rss()
            assert len(entries) == 1
            assert entries[0]["title"] == "Test Article"
            assert entries[0]["link"] == "http://example.com/article1"

    @pytest.mark.asyncio
    async def test_scrape_returns_scraped_articles(self):
        scraper = ConcreteScraper(rss_url="http://example.com/feed.xml")

        mock_feed = _MockFeed([
            {
                "title": "Article 1",
                "link": "http://example.com/1",
                "published": "Mon, 01 Jan 2024 00:00:00 GMT",
                "summary": "Summary 1",
            },
            {
                "title": "Article 2",
                "link": "http://example.com/2",
                "published": "Tue, 02 Jan 2024 00:00:00 GMT",
                "summary": "Summary 2",
            },
        ])

        with patch("feedparser.parse", return_value=mock_feed):
            with patch("asyncio.sleep"):
                articles = await scraper.scrape()
                assert len(articles) == 2
                assert all(isinstance(a, ScrapedArticle) for a in articles)
                assert articles[0].headline == "Article 1"
                assert articles[1].headline == "Article 2"
                assert articles[0].body_text == "Extracted body from http://example.com/1"


class TestTheHinduScraper:
    def test_import(self):
        from app.scrapers.the_hindu import TheHinduScraper  # noqa: F811
        scraper = TheHinduScraper()
        assert "thehindu.com" in scraper.rss_url


class TestIndianExpressScraper:
    def test_import(self):
        from app.scrapers.indian_express import IndianExpressScraper  # noqa: F811
        scraper = IndianExpressScraper()
        assert "indianexpress.com" in scraper.rss_url
