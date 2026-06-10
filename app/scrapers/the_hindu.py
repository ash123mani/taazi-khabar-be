from bs4 import BeautifulSoup
from readability import Document

from app.scrapers.base import BaseScraper


class TheHinduScraper(BaseScraper):
    def __init__(self) -> None:
        super().__init__(
            rss_url="https://www.thehindu.com/news/national/?service=rss",
            rate_limit_delay=1.0,
        )

    def _extract_body_from_html(self, html: str) -> str:
        try:
            doc = Document(html)
            soup = BeautifulSoup(doc.summary(), "lxml")
            for tag in soup(["script", "style", "nav", "footer", "aside"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)
        except Exception:
            return ""
