import asyncio
import math
import random
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_current_user, get_optional_user
from app.models.user import User
from app.models.article import Article
from app.schemas.quiz import (
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizDetailResponse,
    QuizQuestionResponse,
    QuizSubmitRequest,
    QuizSubmitResponse,
    DailyQuizSummaryResponse,
    DailyQuizCategoryItem,
    DailyQuizStartRequest,
    DailyQuizStartResponse,
)
from app.services import article_service, quiz_service
from app.ai.orchestrator import AIOrchestrator

router = APIRouter()


def _get_orchestrator() -> AIOrchestrator:
    return AIOrchestrator()


@router.post("/generate", response_model=QuizGenerateResponse)
async def generate_quiz(
    req: QuizGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    orchestrator: AIOrchestrator = Depends(_get_orchestrator),
):
    article_set_hash = quiz_service.compute_article_set_hash(
        req.article_ids, req.num_questions
    )

    existing = await quiz_service.find_existing_quiz(db, article_set_hash)
    if existing:
        return QuizGenerateResponse(quiz_id=existing.id, cached=True)

    articles = await article_service.get_articles_by_ids(db, req.article_ids)
    num_articles = len(articles)
    if num_articles == 0:
        raise HTTPException(status_code=400, detail="No articles found")

    questions_per_article = max(1, math.ceil(req.num_questions / num_articles))

    articles_dicts = [
        {
            "id": a.id,
            "headline": a.headline,
            "body_text": a.body_text,
            "gk_summary": a.gk_summary,
        }
        for a in articles
    ]

    all_questions_data: list[dict] = []
    articles_needing_llm: list[tuple[dict, int]] = []

    for a_dict in articles_dicts:
        cached_count = await quiz_service.get_cached_question_count(db, a_dict["id"])
        needed = questions_per_article
        if cached_count >= needed:
            cached = await quiz_service.get_cached_questions_for_article(
                db, a_dict["id"], needed
            )
            for cq in cached:
                all_questions_data.append({
                    "question_text": cq.question_text,
                    "options": cq.options,
                    "correct_answer": cq.correct_answer,
                    "explanation": cq.explanation,
                    "difficulty": cq.difficulty,
                })
        else:
            articles_needing_llm.append((a_dict, needed))

    if articles_needing_llm:
        async def generate_for_article(
            article_dict: dict, n: int
        ) -> list[dict]:
            qs = await orchestrator.generate_mcq_for_article(
                article=article_dict,
                num_questions=n,
                user_id=user.id,
                db=db,
            )
            await quiz_service.cache_questions(db, article_dict["id"], qs)
            return qs

        results = await asyncio.gather(
            *[generate_for_article(a, n) for a, n in articles_needing_llm]
        )
        for qs in results:
            all_questions_data.extend(qs)

    random.shuffle(all_questions_data)
    all_questions_data = all_questions_data[:req.num_questions]

    quiz = await quiz_service.create_quiz(
        db=db,
        user_id=user.id,
        article_set_hash=article_set_hash,
        articles=articles,
        questions_data=all_questions_data,
    )

    return QuizGenerateResponse(quiz_id=quiz.id, cached=False)


@router.get("/by-date", response_model=DailyQuizSummaryResponse)
async def daily_quiz_summary(
    date_str: str | None = None,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date
    quiz_date = date.fromisoformat(date_str) if date_str else date.today()
    categories = await quiz_service.get_daily_quiz_summary(db, quiz_date)
    total_articles = sum(c["article_count"] for c in categories)
    total_questions = sum(c["question_count"] for c in categories)
    return DailyQuizSummaryResponse(
        date=quiz_date,
        categories=[DailyQuizCategoryItem(**c) for c in categories],
        total_articles=total_articles,
        total_questions=total_questions,
    )


@router.post("/daily-start", response_model=DailyQuizStartResponse)
async def start_daily_quiz(
    req: DailyQuizStartRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    quiz = await quiz_service.create_daily_quiz(
        db=db,
        user_id=user.id,
        article_date=req.date,
        category_id=req.category_id,
    )
    await db.commit()
    return DailyQuizStartResponse(quiz_id=quiz.id, cached=True)


@router.get("/{quiz_id}", response_model=QuizDetailResponse)
async def get_quiz(
    quiz_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    quiz = await quiz_service.get_quiz_by_id(db, quiz_id)
    if quiz is None or quiz.user_id != user.id:
        raise HTTPException(status_code=404, detail="Quiz not found")

    questions = await quiz_service.get_quiz_questions(db, quiz_id)
    return QuizDetailResponse(
        id=quiz.id,
        title=quiz.title,
        article_set_hash=quiz.article_set_hash,
        score=quiz.score,
        total_questions=quiz.total_questions,
        time_taken_sec=quiz.time_taken_sec,
        created_at=quiz.created_at,
        questions=[QuizQuestionResponse.model_validate(q) for q in questions],
    )


@router.post("/{quiz_id}/submit", response_model=QuizSubmitResponse)
async def submit_quiz(
    quiz_id: UUID,
    req: QuizSubmitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    quiz = await quiz_service.get_quiz_by_id(db, quiz_id)
    if quiz is None or quiz.user_id != user.id:
        raise HTTPException(status_code=404, detail="Quiz not found")
    if quiz.score is not None:
        raise HTTPException(status_code=400, detail="Quiz already submitted")

    score, total, results = await quiz_service.submit_answers(
        db=db,
        user_id=user.id,
        quiz_id=quiz_id,
        answers=req.answers,
    )

    return QuizSubmitResponse(
        quiz_id=quiz_id,
        score=score,
        total_questions=total,
        results=results,
    )
