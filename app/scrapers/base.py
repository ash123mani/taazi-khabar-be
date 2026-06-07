import asyncio
import time
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
    image_url: str | None = None


class BaseScraper(ABC):
    def __init__(self, rss_url: str, rate_limit_delay: float = 1.0) -> None:
        self.rss_url = rss_url
        self.rate_limit_delay = rate_limit_delay

    async def fetch_rss(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(self.rss_url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; TaaziKhabar/1.0)"
            })
            response.raise_for_status()

        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, response.text)
        entries = []
        for entry in feed.entries:
            image_url = None
            if hasattr(entry, "media_content") and entry.media_content:
                for media in entry.media_content:
                    if media.get("type", "").startswith("image"):
                        image_url = media.get("url")
                        break
            if not image_url and hasattr(entry, "enclosures"):
                for enc in entry.enclosures:
                    if enc.get("type", "").startswith("image"):
                        image_url = enc.get("href") or enc.get("url")
                        break
            pub_struct = entry.get("published_parsed")
            if pub_struct:
                published_iso = time.strftime("%Y-%m-%dT%H:%M:%S", pub_struct) + "+0000"
            else:
                published_iso = entry.get("published", "")
            entries.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": published_iso,
                "summary": entry.get("summary", ""),
                "image_url": image_url,
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
                try:
                    body = await self.extract_body(entry["link"], client)
                except (httpx.HTTPStatusError, httpx.TimeoutException):
                    continue
                if body:
                    articles.append(
                        ScrapedArticle(
                            source=self.__class__.__name__.lower().replace("scraper", ""),
                            headline=entry["title"],
                            body_text=body,
                            url=entry["link"],
                            published_at=entry["published"],
                            image_url=entry.get("image_url"),
                        )
                    )

        return articles
