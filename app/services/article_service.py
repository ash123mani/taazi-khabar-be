import asyncio
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from uuid import UUID
from typing import List, Tuple, Optional

from sqlalchemy import select, cast, Date, func, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.article import Article
from app.models.category import Category
from app.models.quiz import QuizArticle
from app.models.cached_question import CachedQuestion
from app.scrapers.base import ScrapedArticle

_AI_TIMEOUT = 300.0  # max seconds per individual AI call


def _parse_rss_date(date_str: str) -> datetime:
    try:
        return parsedate_to_datetime(date_str)
    except (ValueError, TypeError):
        pass
    try:
        return datetime.fromisoformat(date_str.replace("+0000", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now()


async def bulk_upsert_articles(
    db: AsyncSession,
    articles: List[ScrapedArticle],
    summarizer=None,
    article_filter=None,
    question_setter=None,
) -> Tuple[int, int, List[str], int, List[str]]:
    urls = [a.url for a in articles]
    existing = await db.execute(select(Article.url).where(Article.url.in_(urls)))
    existing_urls = {row[0] for row in existing.fetchall()}

    new_articles = [a for a in articles if a.url not in existing_urls]
    skipped = len(articles) - len(new_articles)

    if not new_articles:
        return 0, skipped, [], 0, []

    errors: List[str] = []

    # Phase 1: parallel filter
    async def check_article(a: ScrapedArticle) -> bool:
        if not article_filter:
            return True
        if a.source == "pib":
            return True
        try:
            return await asyncio.wait_for(
                article_filter(headline=a.headline, body_text=a.body_text),
                timeout=_AI_TIMEOUT,
            )
        except Exception:
            return False

    filter_results = await asyncio.gather(*[check_article(a) for a in new_articles])
    filtered_articles = [a for a, ok in zip(new_articles, filter_results) if ok]
    filtered_out = sum(1 for ok in filter_results if not ok)
    filtered_headlines = [a.headline for a, ok in zip(new_articles, filter_results) if not ok]

    if not filtered_articles:
        return 0, skipped, errors, filtered_out, filtered_headlines

    # Phase 2: batch insert with ON CONFLICT DO NOTHING
    # Prevents UniqueViolationError race between URL check and insert
    stmt = insert(Article).values([
        {
            "source": a.source, "headline": a.headline, "body_text": a.body_text,
            "url": a.url, "published_at": _parse_rss_date(a.published_at),
            "image_url": a.image_url,
        }
        for a in filtered_articles
    ]).on_conflict_do_nothing(constraint="articles_url_key")
    await db.execute(stmt)
    await db.flush()

    # Query back the successfully inserted articles for use in subsequent phases
    urls = [a.url for a in filtered_articles]
    result = await db.execute(select(Article).where(Article.url.in_(urls)))
    art_map = {art.url: art for art in result.scalars().all()}
    created_articles = [(art_map[a.url], a) for a in filtered_articles if a.url in art_map]

    # Phase 3: parallel summarize (no db passed — logging skipped for speed)
    async def summarize_one(a: ScrapedArticle) -> dict | None:
        if not summarizer:
            return None
        try:
            return await asyncio.wait_for(
                summarizer(a.body_text),
                timeout=_AI_TIMEOUT,
            )
        except Exception as e:
            errors.append(f"Summarization failed for {a.url}: {e}")
            return None

    summary_results = await asyncio.gather(*[
        summarize_one(a) for _, a in created_articles
    ])

    # Phase 4: apply summaries to DB (sequential)
    cat_result = await db.execute(select(Category).where(Category.name == "Uncategorized"))
    unknown_cat = cat_result.scalar_one_or_none()
    if not unknown_cat:
        unknown_cat = Category(name="Uncategorized", description="Articles without a specific category")
        db.add(unknown_cat)
        await db.flush()

    created = 0
    for (art, _), summary in zip(created_articles, summary_results):
        if not summary:
            art.category_id = unknown_cat.id
            continue
        art.gk_summary = summary.get("gk_gist")
        art.syllabus_tag = summary.get("syllabus_topic")
        art.key_terms = summary.get("key_terms")
        cat_name = summary.get("category")
        if cat_name:
            cat = await db.execute(
                select(Category).where(Category.name.ilike(cat_name.strip()))
            )
            cat_obj = cat.scalar_one_or_none()
            art.category_id = cat_obj.id if cat_obj else unknown_cat.id
        else:
            art.category_id = unknown_cat.id
        created += 1

    # Phase 5: parallel question generation for summarized articles
    async def gen_questions(
        art: Article,
        article_body: str,
    ) -> list[dict]:
        if not question_setter or not art.gk_summary:
            return []
        try:
            return await asyncio.wait_for(
                question_setter(
                    article_id=art.id,
                    headline=art.headline,
                    summary=art.gk_summary,
                    syllabus_tag=art.syllabus_tag,
                    key_terms=art.key_terms,
                ),
                timeout=_AI_TIMEOUT,
            )
        except Exception as e:
            errors.append(f"Question generation failed for {art.headline[:60]}: {e}")
            return []

    if question_setter:
        q_articles: list[Article] = []
        q_coros = []
        for art, orig in created_articles:
            if art.gk_summary:
                q_articles.append(art)
                q_coros.append(gen_questions(art, orig.body_text))
        if q_coros:
            question_results = await asyncio.gather(*q_coros)
            for art, questions in zip(q_articles, question_results):
                if not questions:
                    continue
                existing = await db.execute(
                    select(CachedQuestion.id)
                    .where(CachedQuestion.article_id == art.id)
                    .limit(1)
                )
                if existing.scalar_one_or_none() is not None:
                    continue
                for q in questions:
                    db.add(CachedQuestion(
                        article_id=art.id,
                        question_text=q["question_text"],
                        options=q["options"],
                        correct_answer=q["correct_answer"],
                        explanation=q.get("explanation"),
                        difficulty=q.get("difficulty"),
                    ))
        await db.flush()

    await db.commit()
    return created, skipped, errors, filtered_out, filtered_headlines


async def list_articles(
    db: AsyncSession,
    skip: int = 0,
    limit: int | None = None,
    source: str | None = None,
    category_id: UUID | None = None,
    article_date: date | None = None,
    search: str | None = None,
) -> tuple[List[Article], int]:
    query = select(Article).order_by(Article.published_at.desc())
    count_query = select(Article)

    if source:
        query = query.where(Article.source == source)
        count_query = count_query.where(Article.source == source)
    if category_id:
        query = query.where(Article.category_id == category_id)
        count_query = count_query.where(Article.category_id == category_id)
    if article_date:
        query = query.where(cast(Article.published_at, Date) == article_date)
        count_query = count_query.where(cast(Article.published_at, Date) == article_date)
    if search:
        search_filter = or_(
            Article.headline.ilike(f"%{search}%"),
            Article.gk_summary.ilike(f"%{search}%"),
            Article.syllabus_tag.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    query = query.offset(skip)
    if limit is not None:
        query = query.limit(limit)
    result = await db.execute(query)
    articles = list(result.scalars().all())

    return articles, total


async def get_article_counts(
    db: AsyncSession,
    article_date: date | None = None,
    source: str | None = None,
) -> dict:
    from sqlalchemy import text

    date_filter = f"DATE(published_at) = '{article_date.isoformat()}'" if article_date else "TRUE"

    # Total
    total_q = text(f"SELECT COUNT(*) FROM articles WHERE {date_filter}")
    total = (await db.execute(total_q)).scalar() or 0

    # Source counts
    thehindu_q = text(f"SELECT COUNT(*) FROM articles WHERE source = 'thehindu' AND {date_filter}")
    thehindu = (await db.execute(thehindu_q)).scalar() or 0

    indianexpress_q = text(f"SELECT COUNT(*) FROM articles WHERE source = 'indianexpress' AND {date_filter}")
    indianexpress = (await db.execute(indianexpress_q)).scalar() or 0

    pib_q = text(f"SELECT COUNT(*) FROM articles WHERE source = 'pib' AND {date_filter}")
    pib = (await db.execute(pib_q)).scalar() or 0

    # Category counts
    source_filter = f"AND source = '{source}'" if source else ""
    cat_q = text(f"""
        SELECT category_id::text, COUNT(*) as cnt
        FROM articles
        WHERE category_id IS NOT NULL AND {date_filter} {source_filter}
        GROUP BY category_id
    """)
    cat_result = await db.execute(cat_q)
    categories = {row[0]: row[1] for row in cat_result.fetchall()}

    return {
        "total": total,
        "thehindu": thehindu,
        "indianexpress": indianexpress,
        "pib": pib,
        "categories": categories,
    }


async def get_quizzed_article_ids(db: AsyncSession, article_date: date | None = None) -> set[UUID]:
    query = select(QuizArticle.article_id).distinct()
    if article_date:
        query = query.where(cast(Article.published_at, Date) == article_date)
    result = await db.execute(query)
    return {row[0] for row in result.fetchall()}


async def get_article_by_id(db: AsyncSession, article_id: UUID) -> Article | None:
    result = await db.execute(select(Article).where(Article.id == article_id))
    return result.scalar_one_or_none()


async def get_articles_by_ids(db: AsyncSession, article_ids: List[UUID]) -> List[Article]:
    result = await db.execute(select(Article).where(Article.id.in_(article_ids)))
    return list(result.scalars().all())
