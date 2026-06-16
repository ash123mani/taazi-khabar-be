import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from readability import Document

from app.scrapers.base import BaseScraper, ScrapedArticle
import httpx
import asyncio


class PibScraper(BaseScraper):
    def __init__(self) -> None:
        super().__init__(
            rss_url="https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=1&reg=1",
            rate_limit_delay=1.5,
        )

    async def fetch_rss(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(self.rss_url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; TaaziKhabar/1.0)"
            })
            response.raise_for_status()

        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(None, (
            lambda: __import__("feedparser").parse(response.text)
        ))
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "+0000"
        entries = []
        for entry in feed.entries:
            link = (entry.get("link") or "").replace(
                "PressReleaseIframePage.aspx", "PressReleasePage.aspx"
            )
            entries.append({
                "title": entry.get("title", ""),
                "link": link,
                "published": now_iso,
                "summary": entry.get("summary", ""),
                "image_url": None,
            })
        return entries

    async def scrape(self) -> list[ScrapedArticle]:
        entries = await self.fetch_rss()
        sem = asyncio.Semaphore(3)

        async def process_entry(entry: dict) -> ScrapedArticle | None:
            async with sem:
                await asyncio.sleep(self.rate_limit_delay)
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
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

                    published_at = self._extract_date_from_html(raw_html) or entry["published"]

                    image_url = entry.get("image_url")
                    if not image_url:
                        image_url = self._extract_og_image(raw_html, entry["link"])

                    return ScrapedArticle(
                        source="pib",
                        headline=entry["title"],
                        body_text=body,
                        url=entry["link"],
                        published_at=published_at,
                        image_url=image_url,
                    )

        results = await asyncio.gather(*[process_entry(e) for e in entries])
        return [r for r in results if r is not None]

    def _extract_date_from_html(self, html: str) -> str | None:
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text()
        # Match "प्रविष्टि तिथि: 16 JUN 2026 10:12PM by PIB Delhi"
        match = re.search(
            r"(\d{1,2}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{4})",
            text, re.I,
        )
        if not match:
            return None
        from datetime import datetime as dt
        try:
            parsed = dt.strptime(match.group(1), "%d %b %Y")
            return parsed.strftime("%Y-%m-%dT%H:%M:%S") + "+0000"
        except ValueError:
            return None

    def _extract_body_from_html(self, html: str) -> str:
        try:
            doc = Document(html)
            soup = BeautifulSoup(doc.summary(), "lxml")
            for tag in soup(["script", "style", "nav", "footer", "aside"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)
        except Exception:
            return ""

    def _extract_og_image(self, html: str, page_url: str = "") -> str | None:
        soup = BeautifulSoup(html, "lxml")
        for selector in [
            ("meta", {"property": "og:image"}),
            ("meta", {"name": "twitter:image"}),
            ("meta", {"property": "og:image:secure_url"}),
        ]:
            tag = soup.find(*selector)
            if tag and tag.get("content"):
                url = tag["content"]
                if url.startswith("https:/") and not url.startswith("https://"):
                    url = "https://" + url[len("https:/"):]
                return url
        return None
