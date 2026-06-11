from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.deps import get_db
from app.models.article import Article
from app.models.bookmark import Bookmark
from app.schemas.article import ArticleResponse, ArticleListResponse
from app.services import article_service

router = APIRouter()


@router.get("", response_model=ArticleListResponse)
async def list_articles(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    source: str | None = Query(None),
    category_id: UUID | None = Query(None),
    date_str: str | None = Query(None, alias="date"),
    search: str | None = Query(None),
    user_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    article_date: date | None = None
    if date_str:
        try:
            article_date = date.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")

    articles, total = await article_service.list_articles(
        db=db, skip=skip, limit=limit, source=source,
        category_id=category_id, article_date=article_date,
        search=search,
    )

    quizzed_ids = await article_service.get_quizzed_article_ids(db, article_date)

    bookmarked_ids: set[UUID] = set()
    if user_id:
        bm_result = await db.execute(
            select(Bookmark.article_id).where(Bookmark.user_id == user_id)
        )
        bookmarked_ids = {row[0] for row in bm_result.fetchall()}

    article_responses = []
    for a in articles:
        resp = ArticleResponse.model_validate(a)
        resp.has_quiz = a.id in quizzed_ids
        resp.is_bookmarked = a.id in bookmarked_ids
        article_responses.append(resp)

    return ArticleListResponse(
        articles=article_responses,
        total=total,
    )


@router.get("/counts")
async def get_article_counts(
    date_str: str | None = Query(None, alias="date"),
    source: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date as date_type
    article_date: date_type | None = None
    if date_str:
        try:
            article_date = date_type.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
    return await article_service.get_article_counts(db, article_date=article_date, source=source)


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article(article_id: UUID, db: AsyncSession = Depends(get_db)):
    article = await article_service.get_article_by_id(db, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleResponse.model_validate(article)
