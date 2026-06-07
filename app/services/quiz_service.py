import hashlib
import math
from uuid import UUID
from typing import List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import Quiz, QuizArticle, QuizQuestion, QuizAnswer
from app.models.article import Article
from app.models.cached_question import CachedQuestion


def compute_article_set_hash(article_ids: List[UUID], num_questions: int) -> str:
    sorted_ids = sorted(article_ids)
    hash_input = ",".join(str(id) for id in sorted_ids) + f"|{num_questions}"
    return hashlib.md5(hash_input.encode()).hexdigest()


async def find_existing_quiz(db: AsyncSession, article_set_hash: str) -> Quiz | None:
    result = await db.execute(
        select(Quiz).where(Quiz.article_set_hash == article_set_hash)
    )
    return result.scalar_one_or_none()


async def get_cached_question_count(db: AsyncSession, article_id: UUID) -> int:
    result = await db.execute(
        select(func.count(CachedQuestion.id))
        .where(CachedQuestion.article_id == article_id)
    )
    return result.scalar() or 0


async def get_cached_questions_for_article(
    db: AsyncSession, article_id: UUID, limit: int
) -> List[CachedQuestion]:
    result = await db.execute(
        select(CachedQuestion)
        .where(CachedQuestion.article_id == article_id)
        .order_by(func.random())
        .limit(limit)
    )
    return list(result.scalars().all())


async def cache_questions(
    db: AsyncSession,
    article_id: UUID,
    questions_data: List[dict],
) -> List[CachedQuestion]:
    cached = []
    for q_data in questions_data:
        cq = CachedQuestion(
            article_id=article_id,
            question_text=q_data["question_text"],
            options=q_data["options"],
            correct_answer=q_data["correct_answer"],
            explanation=q_data.get("explanation"),
            difficulty=q_data.get("difficulty"),
        )
        db.add(cq)
        cached.append(cq)
    await db.flush()
    return cached


async def create_quiz(
    db: AsyncSession,
    user_id: UUID,
    article_set_hash: str,
    articles: List[Article],
    questions_data: List[dict],
    title: str | None = None,
    ai_interaction_id: UUID | None = None,
) -> Quiz:
    quiz = Quiz(
        user_id=user_id,
        title=title or f"Quiz on {len(articles)} articles",
        article_set_hash=article_set_hash,
        total_questions=len(questions_data),
    )
    db.add(quiz)
    await db.flush()

    for article in articles:
        quiz_article = QuizArticle(quiz_id=quiz.id, article_id=article.id)
        db.add(quiz_article)

    for q_data in questions_data:
        question = QuizQuestion(
            quiz_id=quiz.id,
            question_text=q_data["question_text"],
            options=q_data["options"],
            correct_answer=q_data["correct_answer"],
            explanation=q_data.get("explanation"),
            difficulty=q_data.get("difficulty"),
            ai_interaction_id=ai_interaction_id,
        )
        db.add(question)

    await db.flush()
    return quiz


async def get_quiz_by_id(db: AsyncSession, quiz_id: UUID) -> Quiz | None:
    result = await db.execute(select(Quiz).where(Quiz.id == quiz_id))
    return result.scalar_one_or_none()


async def get_quiz_questions(db: AsyncSession, quiz_id: UUID) -> List[QuizQuestion]:
    result = await db.execute(
        select(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id)
    )
    return list(result.scalars().all())


async def submit_answers(
    db: AsyncSession,
    user_id: UUID,
    quiz_id: UUID,
    answers: dict[UUID, str],
) -> tuple[int, int, List[dict]]:
    questions = await get_quiz_questions(db, quiz_id)
    question_map = {q.id: q for q in questions}

    score = 0
    total = len(questions)
    results = []

    for question_id, selected_answer in answers.items():
        question = question_map.get(question_id)
        if question is None:
            continue

        is_correct = selected_answer == question.correct_answer
        if is_correct:
            score += 1

        answer = QuizAnswer(
            user_id=user_id,
            question_id=question_id,
            selected_answer=selected_answer,
            is_correct=is_correct,
        )
        db.add(answer)

        results.append({
            "question_id": str(question_id),
            "correct_answer": question.correct_answer,
            "selected_answer": selected_answer,
            "is_correct": is_correct,
            "explanation": question.explanation,
        })

    quiz = await get_quiz_by_id(db, quiz_id)
    if quiz:
        quiz.score = score

    await db.flush()
    return score, total, results


async def list_user_quizzes(db: AsyncSession, user_id: UUID, skip: int = 0, limit: int = 20) -> List[Quiz]:
    result = await db.execute(
        select(Quiz)
        .where(Quiz.user_id == user_id)
        .order_by(Quiz.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())
