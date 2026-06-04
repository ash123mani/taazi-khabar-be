from bs4 import BeautifulSoup
from readability import Document

import httpx

from app.scrapers.base import BaseScraper


class TheHinduScraper(BaseScraper):
    def __init__(self) -> None:
        super().__init__(
            rss_url="https://www.thehindu.com/news/national/?service=rss",
            rate_limit_delay=1.0,
        )

    async def extract_body(self, url: str, client: httpx.AsyncClient) -> str:
        try:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; TaaziKhabar/1.0)"
            })
            response.raise_for_status()

            doc = Document(response.text)
            html = doc.summary()
            soup = BeautifulSoup(html, "lxml")

            for tag in soup(["script", "style", "nav", "footer", "aside"]):
                tag.decompose()

            body = soup.get_text(separator="\n", strip=True)
            return body
        except Exception:
            return ""
