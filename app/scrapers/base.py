import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass

import feedparser
import httpx


@dataclass
class ScrapedArticle:
    source: str
    headline: str
    body_text: str
    url: str
    published_at: str


class BaseScraper(ABC):
    def __init__(self, rss_url: str, rate_limit_delay: float = 1.0) -> None:
        self.rss_url = rss_url
        self.rate_limit_delay = rate_limit_delay

    async def fetch_rss(self) -> list[dict]:
        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, self.rss_url)
        entries = []
        for entry in feed.entries:
            entries.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "summary": entry.get("summary", ""),
            })
        return entries

    @abstractmethod
    async def extract_body(self, url: str, client: httpx.AsyncClient) -> str:
        ...

    async def scrape(self) -> list[ScrapedArticle]:
        entries = await self.fetch_rss()
        articles: list[ScrapedArticle] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for entry in entries:
                await asyncio.sleep(self.rate_limit_delay)
                body = await self.extract_body(entry["link"], client)
                if body:
                    articles.append(
                        ScrapedArticle(
                            source=self.__class__.__name__.lower().replace("scraper", ""),
                            headline=entry["title"],
                            body_text=body,
                            url=entry["link"],
                            published_at=entry["published"],
                        )
                    )

        return articles
