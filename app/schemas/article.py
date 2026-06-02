from uuid import UUID
from datetime import datetime
from typing import List

from pydantic import BaseModel


class ArticleResponse(BaseModel):
    id: UUID
    source: str
    headline: str
    body_text: str
    url: str
    published_at: datetime
    scraped_at: datetime
    gk_summary: str | None
    key_terms: List[str] | None
    syllabus_tag: str | None
    category_id: UUID | None

    class Config:
        from_attributes = True


class ArticleListResponse(BaseModel):
    articles: List[ArticleResponse]
    total: int
