from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.quiz import QuizListItem, QuizDetailResponse, QuizQuestionResponse
from app.services import quiz_service

router = APIRouter()


@router.get("", response_model=list[QuizListItem])
async def list_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    quizzes = await quiz_service.list_user_quizzes(
        db=db, user_id=user.id, skip=skip, limit=limit
    )
    return [QuizListItem.model_validate(q) for q in quizzes]


@router.get("/{quiz_id}", response_model=QuizDetailResponse)
async def get_history_item(
    quiz_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    quiz = await quiz_service.get_quiz_by_id(db, quiz_id)
    if quiz is None or quiz.user_id != user.id:
        raise HTTPException(status_code=404, detail="History entry not found")

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
