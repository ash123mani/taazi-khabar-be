from uuid import UUID
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article


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
