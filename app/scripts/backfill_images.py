"""Backfill image_url for articles that are missing it.

Usage: python -m app.scripts.backfill_images [--limit N]
"""
import asyncio
import sys
import time

from bs4 import BeautifulSoup
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

sys.path.insert(0, ".")
from app.config import settings
from app.models.article import Article


def extract_og_image(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for selector in [
        ("meta", {"property": "og:image"}),
        ("meta", {"name": "twitter:image"}),
        ("meta", {"property": "og:image:secure_url"}),
    ]:
        tag = soup.find(*selector)
        if tag and tag.get("content"):
            return tag["content"]
    img = soup.find("img", class_=lambda c: c and "lead" in str(c).lower())
    if img and img.get("src", "").startswith("http"):
        return img["src"]
    return None


async def main():
    limit = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--limit" and i < len(sys.argv):
            limit = int(sys.argv[i + 1])

    engine = create_async_engine(
        settings.database_url,
        connect_args={"statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    db = session_factory()
    query = select(Article).where(Article.image_url.is_(None)).order_by(Article.published_at.desc())
    if limit:
        query = query.limit(limit)
    result = await db.execute(query)
    articles = list(result.scalars().all())
    await db.close()
    print(f"Found {len(articles)} articles without image_url")

    found = 0
    async with httpx.AsyncClient(
        timeout=15.0,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TaaziKhabar/1.0)"},
    ) as client:
        for i, article in enumerate(articles, 1):
            print(f"[{i}/{len(articles)}] {article.headline[:60]}...", end=" ")
            try:
                resp = await client.get(article.url, follow_redirects=True)
                resp.raise_for_status()
                image_url = extract_og_image(resp.text)
            except Exception as e:
                print(f"✗ {e}")
                continue

            if image_url:
                print(f"✓")
                found += 1
                db2 = session_factory()
                article = await db2.get(Article, article.id)
                article.image_url = image_url
                await db2.commit()
                await db2.close()
            else:
                print("(no image found)")

            await asyncio.sleep(0.5)

    print(f"\nDone. Updated {found}/{len(articles)} articles.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
