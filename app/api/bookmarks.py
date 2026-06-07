from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.deps import get_db, get_current_user
from app.models.user import User
from app.models.bookmark import Bookmark
from app.models.article import Article
from app.schemas.article import ArticleResponse

router = APIRouter()


@router.get("")
async def list_bookmarked_ids(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Bookmark.article_id).where(Bookmark.user_id == user.id)
    )
    return {"bookmarked_ids": [str(row[0]) for row in result.fetchall()]}


@router.get("/articles", response_model=list[ArticleResponse])
async def list_bookmarked_articles(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Article).join(Bookmark, Article.id == Bookmark.article_id)
        .where(Bookmark.user_id == user.id)
        .order_by(Bookmark.created_at.desc())
    )
    return [ArticleResponse.model_validate(a) for a in list(result.scalars().all())]


@router.post("/{article_id}")
async def toggle_bookmark(
    article_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    existing = await db.execute(
        select(Bookmark).where(
            Bookmark.user_id == user.id,
            Bookmark.article_id == article_id,
        )
    )
    existing_bookmark = existing.scalar_one_or_none()

    if existing_bookmark:
        await db.delete(existing_bookmark)
        await db.flush()
        return {"bookmarked": False}
    else:
        bookmark = Bookmark(user_id=user.id, article_id=article_id)
        db.add(bookmark)
        await db.flush()
        return {"bookmarked": True}
