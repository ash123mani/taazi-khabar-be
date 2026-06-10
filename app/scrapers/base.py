import asyncio
import time
from abc import ABC
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

    def _extract_og_image(self, html: str, page_url: str = "") -> str | None:
        from urllib.parse import urljoin
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        for selector in [
            ("meta", {"property": "og:image"}),
            ("meta", {"name": "twitter:image"}),
            ("meta", {"property": "og:image:secure_url"}),
        ]:
            tag = soup.find(*selector)
            if tag and tag.get("content"):
                url = tag["content"]
                if url.startswith("http"):
                    return url
                if page_url:
                    return urljoin(page_url, url)
        img = soup.find("img", class_=lambda c: c and "lead" in str(c).lower())
        if img and img.get("src", "").startswith("http"):
            return img["src"]
        return None

    async def scrape(self) -> list[ScrapedArticle]:
        entries = await self.fetch_rss()
        sem = asyncio.Semaphore(3)

        async def process_entry(entry: dict) -> ScrapedArticle | None:
            async with sem:
                await asyncio.sleep(self.rate_limit_delay)
                async with httpx.AsyncClient(timeout=30.0) as client:
                    # Single fetch: extract og:image from same response
                    try:
                        resp = await client.get(
                            entry["link"],
                            headers={"User-Agent": "Mozilla/5.0 (compatible; TaaziKhabar/1.0)"},
                        )
                        resp.raise_for_status()
                    except httpx.HTTPError:
                        return None

                    raw_html = resp.text
                    body = self._extract_body_from_html(raw_html)
                    if not body:
                        return None

                    image_url = entry.get("image_url")
                    if not image_url:
                        image_url = self._extract_og_image(raw_html, entry["link"])

                    return ScrapedArticle(
                        source=self.__class__.__name__.lower().replace("scraper", ""),
                        headline=entry["title"],
                        body_text=body,
                        url=entry["link"],
                        published_at=entry["published"],
                        image_url=image_url,
                    )

        results = await asyncio.gather(*[process_entry(e) for e in entries])
        return [r for r in results if r is not None]

    def _extract_body_from_html(self, html: str) -> str:
        """Default body extraction using readability. Subclasses should override."""
        from readability import Document
        from bs4 import BeautifulSoup

        doc = Document(html)
        soup = BeautifulSoup(doc.summary(), "lxml")
        for tag in soup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
