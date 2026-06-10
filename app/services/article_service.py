import asyncio
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from uuid import UUID
from typing import List, Tuple

from sqlalchemy import select, cast, Date, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.article import Article
from app.models.category import Category
from app.models.quiz import QuizArticle
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

    new_articles = [a for a in articles if a.url not in existing_urls]
    skipped = len(articles) - len(new_articles)

    if not new_articles:
        return 0, skipped, [], 0

    sem = asyncio.Semaphore(5)
    errors: List[str] = []

    # Phase 1: parallel filter
    async def check_article(a: ScrapedArticle) -> bool:
        if not article_filter:
            return True
        async with sem:
            try:
                return await article_filter(headline=a.headline, body_text=a.body_text)
            except Exception:
                return False

    filter_results = await asyncio.gather(*[check_article(a) for a in new_articles])
    filtered_articles = [a for a, ok in zip(new_articles, filter_results) if ok]
    filtered_out = sum(1 for ok in filter_results if not ok)

    if not filtered_articles:
        return 0, skipped, errors, filtered_out

    # Phase 2: batch insert
    created_articles = []
    for a in filtered_articles:
        db_article = Article(
            source=a.source, headline=a.headline, body_text=a.body_text,
            url=a.url, published_at=_parse_rss_date(a.published_at),
            image_url=a.image_url,
        )
        db.add(db_article)
        created_articles.append((db_article, a))
    await db.flush()

    # Phase 3: parallel summarize (no db passed — logging skipped for speed)
    async def summarize_one(a: ScrapedArticle) -> dict | None:
        if not summarizer:
            return None
        async with sem:
            try:
                return await summarizer(a.body_text)
            except Exception as e:
                errors.append(f"Summarization failed for {a.url}: {e}")
                return None

    summary_results = await asyncio.gather(*[
        summarize_one(a) for _, a in created_articles
    ])

    # Phase 4: apply summaries to DB (sequential)
    created = 0
    for (art, _), summary in zip(created_articles, summary_results):
        if not summary:
            continue
        art.gk_summary = summary.get("gk_gist")
        art.syllabus_tag = summary.get("syllabus_topic")
        art.key_terms = summary.get("key_terms")
        cat_name = summary.get("category")
        if cat_name:
            cat = await db.execute(
                select(Category).where(Category.name.ilike(cat_name.strip()))
            )
            cat_obj = cat.scalar_one_or_none()
            if cat_obj:
                art.category_id = cat_obj.id
        created += 1

    await db.commit()
    return created, skipped, errors, filtered_out


async def list_articles(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    source: str | None = None,
    category_id: UUID | None = None,
    article_date: date | None = None,
    search: str | None = None,
) -> tuple[List[Article], int]:
    query = select(Article).order_by(Article.published_at.desc())
    count_query = select(Article)

    if source:
        query = query.where(Article.source == source)
        count_query = count_query.where(Article.source == source)
    if category_id:
        query = query.where(Article.category_id == category_id)
        count_query = count_query.where(Article.category_id == category_id)
    if article_date:
        query = query.where(cast(Article.published_at, Date) == article_date)
        count_query = count_query.where(cast(Article.published_at, Date) == article_date)
    if search:
        search_filter = or_(
            Article.headline.ilike(f"%{search}%"),
            Article.gk_summary.ilike(f"%{search}%"),
            Article.syllabus_tag.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    articles = list(result.scalars().all())

    return articles, total


async def get_quizzed_article_ids(db: AsyncSession, article_date: date | None = None) -> set[UUID]:
    query = select(QuizArticle.article_id).distinct()
    if article_date:
        query = query.where(cast(Article.published_at, Date) == article_date)
    result = await db.execute(query)
    return {row[0] for row in result.fetchall()}


async def get_article_by_id(db: AsyncSession, article_id: UUID) -> Article | None:
    result = await db.execute(select(Article).where(Article.id == article_id))
    return result.scalar_one_or_none()


async def get_articles_by_ids(db: AsyncSession, article_ids: List[UUID]) -> List[Article]:
    result = await db.execute(select(Article).where(Article.id.in_(article_ids)))
    return list(result.scalars().all())
