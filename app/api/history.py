from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.deps import get_db, get_current_user
from app.models.user import User
from app.models.quiz import Quiz, QuizQuestion, QuizAnswer, QuizArticle
from app.models.article import Article
from app.schemas.quiz import QuizListItem, QuizHistoryDetailResponse, QuizHistoryQuestionResponse
from app.schemas.article import ArticleResponse
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


@router.get("/{quiz_id}", response_model=QuizHistoryDetailResponse)
async def get_history_item(
    quiz_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    quiz = await quiz_service.get_quiz_by_id(db, quiz_id)
    if quiz is None or quiz.user_id != user.id:
        raise HTTPException(status_code=404, detail="History entry not found")

    questions_result = await db.execute(
        select(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id)
    )
    questions = list(questions_result.scalars().all())

    answers_result = await db.execute(
        select(QuizAnswer).where(
            QuizAnswer.user_id == user.id,
            QuizAnswer.question_id.in_([q.id for q in questions]),
        )
    )
    answer_map = {a.question_id: a for a in list(answers_result.scalars().all())}

    articles_result = await db.execute(
        select(Article).join(QuizArticle, Article.id == QuizArticle.article_id)
        .where(QuizArticle.quiz_id == quiz_id)
    )
    articles = [ArticleResponse.model_validate(a) for a in list(articles_result.scalars().all())]

    question_responses = []
    for q in questions:
        answer = answer_map.get(q.id)
        question_responses.append(QuizHistoryQuestionResponse(
            id=q.id,
            question_text=q.question_text,
            options=q.options,
            difficulty=q.difficulty,
            correct_answer=q.correct_answer,
            explanation=q.explanation,
            selected_answer=answer.selected_answer if answer else None,
        ))

    return QuizHistoryDetailResponse(
        id=quiz.id,
        title=quiz.title,
        article_set_hash=quiz.article_set_hash,
        score=quiz.score,
        total_questions=quiz.total_questions,
        time_taken_sec=quiz.time_taken_sec,
        created_at=quiz.created_at,
        questions=question_responses,
        articles=articles,
    )
