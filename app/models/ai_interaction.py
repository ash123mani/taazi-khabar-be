from uuid import uuid4, UUID
from datetime import datetime

from sqlalchemy import Column, String, Text, Integer, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.models.base import Base


class AIInteraction(Base):
    __tablename__ = "ai_interactions"

    id: UUID = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    persona: str = Column(String(50), nullable=False)
    model_used: str = Column(String(100), nullable=False)
    prompt_text: str = Column(Text, nullable=False)
    response_text: str = Column(Text, nullable=False)
    tokens_used: int = Column(Integer, nullable=True)
    latency_ms: float = Column(Float, nullable=True)
    user_id: UUID = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    article_id: UUID = Column(PG_UUID(as_uuid=True), ForeignKey("articles.id"), nullable=True)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())
