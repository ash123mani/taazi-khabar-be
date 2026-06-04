from uuid import uuid4, UUID
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.models.base import Base


class Article(Base):
    __tablename__ = "articles"

    id: UUID = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source: str = Column(String(50), nullable=False)
    headline: str = Column(Text, nullable=False)
    body_text: str = Column(Text, nullable=False)
    url: str = Column(Text, unique=True, nullable=False)
    published_at: datetime = Column(DateTime(timezone=True), nullable=False)
    scraped_at: datetime = Column(DateTime(timezone=True), server_default=func.now())
    gk_summary: str = Column(Text, nullable=True)
    key_terms: list = Column(ARRAY(Text), nullable=True)
    syllabus_tag: str = Column(String(200), nullable=True)
    category_id: UUID = Column(PG_UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
