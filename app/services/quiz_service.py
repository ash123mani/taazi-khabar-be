import hashlib
import math
from datetime import date as DateType
from uuid import UUID
from typing import List, Optional

from sqlalchemy import select, func, and_, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import Quiz, QuizArticle, QuizQuestion, QuizAnswer
from app.models.article import Article
from app.models.category import Category
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


def compute_date_hash(date: DateType, category_id: Optional[UUID], user_id: UUID, retry: int = 0) -> str:
    hash_input = f"{date.isoformat()}|{category_id or 'all'}|{user_id}|{retry}"
    return hashlib.md5(hash_input.encode()).hexdigest()


async def get_daily_quiz_summary(
    db: AsyncSession, article_date: DateType
) -> list[dict]:
    result = await db.execute(
        select(
            Category.id,
            Category.name,
            func.count(func.distinct(Article.id)),
            func.count(CachedQuestion.id),
        )
        .select_from(Article)
        .join(CachedQuestion, CachedQuestion.article_id == Article.id)
        .join(Category, Category.id == Article.category_id)
        .where(cast(Article.published_at, Date) == article_date)
        .group_by(Category.id, Category.name)
        .order_by(Category.name)
    )
    categories = []
    for row in result.fetchall():
        cat_id = row[0]
        art_result = await db.execute(
            select(Article.id, Article.headline, Article.source, Article.url, Article.image_url)
            .where(
                cast(Article.published_at, Date) == article_date,
                Article.category_id == cat_id,
                Article.gk_summary.isnot(None),
            )
            .order_by(Article.published_at)
        )
        articles = [
            {
                "id": str(a[0]),
                "headline": a[1],
                "source": a[2],
                "url": a[3],
                "image_url": a[4],
            }
            for a in art_result.fetchall()
        ]
        categories.append({
            "id": str(cat_id),
            "name": row[1],
            "article_count": row[2],
            "question_count": row[3],
            "articles": articles,
        })
    return categories


async def get_cached_questions_for_date(
    db: AsyncSession,
    article_date: DateType,
    category_id: Optional[UUID] = None,
) -> tuple[list[Article], list[dict]]:
    query = (
        select(Article)
        .where(
            cast(Article.published_at, Date) == article_date,
            Article.category_id.isnot(None),
            Article.gk_summary.isnot(None),
        )
        .order_by(Article.published_at)
    )
    if category_id:
        query = query.where(Article.category_id == category_id)

    result = await db.execute(query)
    articles = list(result.scalars().all())

    questions_data = []
    for article in articles:
        cq_result = await db.execute(
            select(CachedQuestion)
            .where(CachedQuestion.article_id == article.id)
            .order_by(CachedQuestion.created_at)
        )
        for cq in cq_result.scalars().all():
            questions_data.append({
                "question_text": cq.question_text,
                "options": cq.options,
                "correct_answer": cq.correct_answer,
                "explanation": cq.explanation,
                "difficulty": cq.difficulty,
                "article_id": article.id,
            })

    return articles, questions_data


async def create_daily_quiz(
    db: AsyncSession,
    user_id: UUID,
    article_date: DateType,
    category_id: Optional[UUID] = None,
) -> Quiz:
    base_hash = compute_date_hash(article_date, category_id, user_id)
    prefix = base_hash[:20]

    # Return existing unfinished quiz so user can continue
    existing_result = await db.execute(
        select(Quiz).where(
            Quiz.article_set_hash.like(f"{prefix}%"),
            Quiz.user_id == user_id,
            Quiz.score.is_(None),
        ).order_by(Quiz.created_at.desc()).limit(1)
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        return existing

    # Count existing attempts to make a unique hash per retake
    count_result = await db.execute(
        select(func.count()).select_from(Quiz).where(
            Quiz.article_set_hash.like(f"{prefix}%"),
            Quiz.user_id == user_id,
        )
    )
    retry = count_result.scalar() or 0
    date_hash = compute_date_hash(article_date, category_id, user_id, retry)

    articles, questions_data = await get_cached_questions_for_date(
        db, article_date, category_id
    )

    cat_label = ""
    if category_id:
        cat_result = await db.execute(
            select(Category).where(Category.id == category_id)
        )
        cat_obj = cat_result.scalar_one_or_none()
        if cat_obj:
            cat_label = f" - {cat_obj.name}"

    quiz = await create_quiz(
        db=db,
        user_id=user_id,
        article_set_hash=date_hash,
        articles=articles,
        questions_data=questions_data,
        title=f"Daily Quiz {article_date.isoformat()}{cat_label}",
    )
    return quiz
