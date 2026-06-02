from uuid import uuid4, UUID
from datetime import datetime

from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.models.base import Base


class Quiz(Base):
    __tablename__ = "quizzes"

    id: UUID = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: UUID = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title: str = Column(String(200), nullable=True)
    article_set_hash: str = Column(String(32), unique=True, nullable=False)
    score: int = Column(Integer, nullable=True)
    total_questions: int = Column(Integer, nullable=False)
    time_taken_sec: int = Column(Integer, nullable=True)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())


class QuizArticle(Base):
    __tablename__ = "quiz_articles"

    quiz_id: UUID = Column(PG_UUID(as_uuid=True), ForeignKey("quizzes.id"), primary_key=True)
    article_id: UUID = Column(PG_UUID(as_uuid=True), ForeignKey("articles.id"), primary_key=True)


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: UUID = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    quiz_id: UUID = Column(PG_UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False)
    question_text: str = Column(Text, nullable=False)
    options: dict = Column(JSONB, nullable=False)
    correct_answer: str = Column(String(10), nullable=False)
    explanation: str = Column(Text, nullable=True)
    difficulty: str = Column(String(10), nullable=True)
    ai_interaction_id: UUID = Column(PG_UUID(as_uuid=True), ForeignKey("ai_interactions.id"), nullable=True)


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"

    id: UUID = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: UUID = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    question_id: UUID = Column(PG_UUID(as_uuid=True), ForeignKey("quiz_questions.id"), nullable=False)
    selected_answer: str = Column(String(10), nullable=True)
    is_correct: bool = Column(Boolean, nullable=True)
    time_taken_sec: int = Column(Integer, nullable=True)
