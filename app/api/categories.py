from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models.category import Category

router = APIRouter()


@router.get("")
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(Category.name))
    categories = result.scalars().all()
    return {
        "categories": [
            {
                "id": str(c.id),
                "name": c.name,
                "description": c.description,
                "created_at": c.created_at.isoformat(),
            }
            for c in categories
        ]
    }
