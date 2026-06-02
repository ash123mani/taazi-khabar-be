from uuid import uuid4, UUID
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.models.base import Base


class ExamQuestion(Base):
    __tablename__ = "exam_questions"

    id: UUID = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_exam: str = Column(String(50), nullable=False)
    year: str = Column(String(4), nullable=False)
    subject: str = Column(String(100), nullable=False)
    question_text: str = Column(Text, nullable=False)
    options: dict = Column(JSONB, nullable=False)
    correct_answer: str = Column(String(10), nullable=False)
    explanation: str = Column(Text, nullable=True)
    topic: str = Column(String(200), nullable=True)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())
