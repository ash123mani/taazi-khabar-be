from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from app.deps import get_db, get_current_user
from app.models.user import User
from app.models.quiz import Quiz, QuizQuestion, QuizAnswer, QuizArticle
from app.models.article import Article


router = APIRouter()


@router.get("/performance")
async def get_performance(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(
            Article.syllabus_tag,
            func.count(QuizAnswer.id).label("total"),
            func.sum(
                text("CASE WHEN quiz_answers.is_correct THEN 1 ELSE 0 END")
            ).label("correct"),
        )
        .select_from(QuizAnswer)
        .join(QuizQuestion, QuizAnswer.question_id == QuizQuestion.id)
        .join(QuizArticle, QuizQuestion.quiz_id == QuizArticle.quiz_id)
        .join(Article, QuizArticle.article_id == Article.id)
        .where(
            QuizAnswer.user_id == user.id,
            QuizAnswer.is_correct.isnot(None),
            Article.syllabus_tag.isnot(None),
            Article.syllabus_tag != '',
        )
        .group_by(Article.syllabus_tag)
        .order_by(func.count(QuizAnswer.id).desc())
    )

    rows = result.fetchall()
    topics = []
    total_correct = 0
    total_questions = 0
    for row in rows:
        tag = row[0]
        total = row[1]
        correct = row[2] or 0
        topics.append({
            "topic": tag,
            "total": total,
            "correct": correct,
            "accuracy": round((correct / total) * 100, 1) if total > 0 else 0,
        })
        total_correct += correct
        total_questions += total

    count_result = await db.execute(
        select(func.count(Quiz.id)).where(Quiz.user_id == user.id, Quiz.score.isnot(None))
    )
    total_quizzes = count_result.scalar() or 0

    return {
        "topics": topics,
        "total_questions": total_questions,
        "total_correct": total_correct,
        "overall_accuracy": round((total_correct / total_questions) * 100, 1) if total_questions > 0 else 0,
        "total_quizzes": total_quizzes,
    }
