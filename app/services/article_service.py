from datetime import datetime
from email.utils import parsedate_to_datetime
from uuid import UUID
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.scrapers.base import ScrapedArticle


def _parse_rss_date(date_str: str) -> datetime:
    try:
        return parsedate_to_datetime(date_str)
    except (ValueError, TypeError):
        return datetime.now()


async def bulk_upsert_articles(
    db: AsyncSession,
    articles: List[ScrapedArticle],
    summarizer=None,
    article_filter=None,
) -> Tuple[int, int, List[str], int]:
    urls = [a.url for a in articles]
    existing = await db.execute(select(Article.url).where(Article.url.in_(urls)))
    existing_urls = {row[0] for row in existing.fetchall()}

    created = 0
    skipped = 0
    filtered_out = 0
    errors: List[str] = []

    for article in articles:
        if article.url in existing_urls:
            skipped += 1
            continue

        if article_filter:
            try:
                is_relevant = await article_filter(headline=article.headline, body_text=article.body_text)
                if not is_relevant:
                    filtered_out += 1
                    existing_urls.add(article.url)
                    continue
            except Exception as e:
                errors.append(f"Filter failed for {article.url}: {e}")
                existing_urls.add(article.url)
                continue

        db_article = Article(
            source=article.source,
            headline=article.headline,
            body_text=article.body_text,
            url=article.url,
            published_at=_parse_rss_date(article.published_at),
            image_url=article.image_url,
        )
        db.add(db_article)
        await db.flush()

        if summarizer:
            try:
                summary = await summarizer(article.body_text, article_id=db_article.id, db=db)
                db_article.gk_summary = summary.get("gk_gist")
                db_article.syllabus_tag = summary.get("syllabus_topic")
                db_article.key_terms = summary.get("key_terms")
            except Exception as e:
                errors.append(f"Summarization failed for {article.url}: {e}")

        existing_urls.add(article.url)
        created += 1

    await db.commit()
    return created, skipped, errors, filtered_out


async def list_articles(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    source: str | None = None,
    category_id: UUID | None = None,
) -> tuple[List[Article], int]:
    query = select(Article).order_by(Article.published_at.desc())
    count_query = select(Article)

    if source:
        query = query.where(Article.source == source)
        count_query = count_query.where(Article.source == source)
    if category_id:
        query = query.where(Article.category_id == category_id)
        count_query = count_query.where(Article.category_id == category_id)

    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    articles = list(result.scalars().all())

    return articles, total


async def get_article_by_id(db: AsyncSession, article_id: UUID) -> Article | None:
    result = await db.execute(select(Article).where(Article.id == article_id))
    return result.scalar_one_or_none()


async def get_articles_by_ids(db: AsyncSession, article_ids: List[UUID]) -> List[Article]:
    result = await db.execute(select(Article).where(Article.id.in_(article_ids)))
    return list(result.scalars().all())
