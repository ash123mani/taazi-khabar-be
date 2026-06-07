from uuid import UUID
from datetime import datetime
from typing import List, Dict

from pydantic import BaseModel


class QuizGenerateRequest(BaseModel):
    article_ids: List[UUID]
    num_questions: int = 5


class QuizGenerateResponse(BaseModel):
    quiz_id: UUID
    cached: bool


class QuizQuestionResponse(BaseModel):
    id: UUID
    question_text: str
    options: Dict[str, str]
    difficulty: str | None

    class Config:
        from_attributes = True


class QuizDetailResponse(BaseModel):
    id: UUID
    title: str | None
    article_set_hash: str
    score: int | None
    total_questions: int
    time_taken_sec: int | None
    created_at: datetime
    questions: List[QuizQuestionResponse]
    articles: List | None = None

    class Config:
        from_attributes = True


class QuizHistoryQuestionResponse(BaseModel):
    id: UUID
    question_text: str
    options: Dict[str, str]
    difficulty: str | None
    correct_answer: str | None = None
    explanation: str | None = None
    selected_answer: str | None = None

    class Config:
        from_attributes = True


class QuizHistoryDetailResponse(BaseModel):
    id: UUID
    title: str | None
    article_set_hash: str
    score: int | None
    total_questions: int
    time_taken_sec: int | None
    created_at: datetime
    questions: List[QuizHistoryQuestionResponse]
    articles: List | None = None

    class Config:
        from_attributes = True


class QuizListItem(BaseModel):
    id: UUID
    title: str | None
    total_questions: int
    score: int | None
    created_at: datetime

    class Config:
        from_attributes = True


class QuizSubmitRequest(BaseModel):
    answers: Dict[UUID, str]


class QuizSubmitResponse(BaseModel):
    quiz_id: UUID
    score: int
    total_questions: int
    results: List[Dict]
