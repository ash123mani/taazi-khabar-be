from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.article import ArticleResponse, ArticleListResponse
from app.services import article_service

router = APIRouter()


@router.get("", response_model=ArticleListResponse)
async def list_articles(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    source: str | None = Query(None),
    category_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    articles, total = await article_service.list_articles(
        db=db, skip=skip, limit=limit, source=source, category_id=category_id
    )
    return ArticleListResponse(
        articles=[ArticleResponse.model_validate(a) for a in articles],
        total=total,
    )


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article(article_id: UUID, db: AsyncSession = Depends(get_db)):
    article = await article_service.get_article_by_id(db, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleResponse.model_validate(article)
