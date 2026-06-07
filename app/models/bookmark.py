from uuid import uuid4, UUID
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.models.base import Base


class Bookmark(Base):
    __tablename__ = "bookmarks"

    id: UUID = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: UUID = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    article_id: UUID = Column(PG_UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "article_id", name="uq_user_article_bookmark"),
    )
