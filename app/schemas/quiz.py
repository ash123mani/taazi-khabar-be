from uuid import UUID
from datetime import date, datetime
from typing import List, Dict, Optional

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


class DailyQuizArticleItem(BaseModel):
    id: UUID
    headline: str
    source: str
    url: str
    image_url: str | None = None


class DailyQuizCategoryItem(BaseModel):
    id: UUID
    name: str
    article_count: int
    question_count: int
    articles: List[DailyQuizArticleItem] = []


class DailyQuizSummaryResponse(BaseModel):
    date: date
    categories: List[DailyQuizCategoryItem]
    total_articles: int
    total_questions: int


class DailyQuizStartRequest(BaseModel):
    date: date
    category_id: Optional[UUID] = None


class DailyQuizStartResponse(BaseModel):
    quiz_id: UUID
    cached: bool
