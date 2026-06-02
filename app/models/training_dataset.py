from uuid import uuid4, UUID
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.models.base import Base


class TrainingDataset(Base):
    __tablename__ = "training_datasets"

    id: UUID = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    persona: str = Column(String(50), nullable=False)
    format: str = Column(String(50), nullable=False, default="alpaca")
    record_count: int = Column(Integer, nullable=False, default=0)
    dataset_jsonl: str = Column(Text, nullable=False)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())
