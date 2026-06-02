from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.quiz import (
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizDetailResponse,
    QuizQuestionResponse,
    QuizSubmitRequest,
    QuizSubmitResponse,
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
    articles_dicts = [
        {
            "headline": a.headline,
            "body_text": a.body_text,
            "gk_summary": a.gk_summary,
        }
        for a in articles
    ]

    questions_data = await orchestrator.generate_mcq(
        articles=articles_dicts,
        num_questions=req.num_questions,
        user_id=user.id,
        db=db,
    )

    quiz = await quiz_service.create_quiz(
        db=db,
        user_id=user.id,
        article_set_hash=article_set_hash,
        articles=articles,
        questions_data=questions_data,
    )

    return QuizGenerateResponse(quiz_id=quiz.id, cached=False)


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
