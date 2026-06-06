import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class ModelRegistryEntry(Base):
    __tablename__ = "model_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    persona = Column(String(100), nullable=False)
    model_name = Column(String(200), nullable=False)
    provider = Column(String(50), nullable=False, default="nim")
    max_tokens = Column(Integer, nullable=False, default=512)
    temperature = Column(Float, nullable=False, default=0.3)
    top_p = Column(Float, nullable=False, default=1.0)
    frequency_penalty = Column(Float, nullable=False, default=0.0)
    presence_penalty = Column(Float, nullable=False, default=0.0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
