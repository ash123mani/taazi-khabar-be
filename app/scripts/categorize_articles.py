"""Assign categories to articles based on syllabus_tag.

Usage: python -m app.scripts.categorize_articles
"""
import asyncio
import re
import sys

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

sys.path.insert(0, ".")
from app.config import settings
from app.models.article import Article
from app.models.category import Category


SUBJECT_MAP: dict[str, str] = {
    "polity & governance": "Polity",
    "polity": "Polity",
    "governance": "Polity",
    "history": "History",
    "culture": "History",
    "geography": "Geography",
    "geophysics": "Geography",
    "environment & ecology": "Environment",
    "environment": "Environment",
    "science & technology": "Science & Tech",
    "science & tech": "Science & Tech",
    "economy": "Economy",
    "economic": "Economy",
    "infrastructure": "Economy",
    "industry": "Economy",
    "agriculture": "Economy",
    "international relations": "International Relations",
    "india's foreign policy": "International Relations",
    "internal security": "Security",
    "security": "Security",
    "social issues": "Social Issues",
    "social justice": "Social Issues",
    "society": "Social Issues",
    "indian society": "Social Issues",
    "health": "Social Issues",
}

SUBJECT_PATTERN = re.compile(r"GS Paper\s+\d\s*[—–-]\s*([^:]+)(?::|$)")


def extract_subject(syllabus_tag: str) -> str | None:
    m = SUBJECT_PATTERN.search(syllabus_tag)
    if not m:
        return None
    subject = m.group(1).strip().lower()
    for key, val in SUBJECT_MAP.items():
        if key in subject:
            return val
    return None


async def main():
    engine = create_async_engine(
        settings.database_url,
        connect_args={"statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    db = session_factory()
    cats = {c.name: c.id for c in (await db.execute(select(Category))).scalars().all()}
    print(f"Categories in DB: {list(cats.keys())}")

    articles = (
        await db.execute(
            select(Article).where(
                Article.category_id.is_(None),
                Article.syllabus_tag.isnot(None),
            )
        )
    ).scalars().all()
    print(f"Found {len(articles)} articles with syllabus_tag but no category")

    assigned = 0
    for article in articles:
        cat_name = extract_subject(article.syllabus_tag)
        if cat_name and cat_name in cats:
            await db.execute(
                update(Article)
                .where(Article.id == article.id)
                .values(category_id=cats[cat_name])
            )
            assigned += 1
    await db.commit()
    print(f"Assigned {assigned}/{len(articles)} articles to categories")

    remaining = (
        await db.execute(
            select(Article).where(Article.category_id.is_(None))
        )
    ).scalars().all()
    print(f"Remaining uncategorized: {len(remaining)}")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
