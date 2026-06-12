"""
Standalone batch script for GitHub Actions. Runs two operations:

1. CATEGORY BACKFILL: For articles without category_id, ask AI to determine
   the UPSC category from the gk_summary / headline, then update the DB.

2. QUESTION GENERATION: For every article that doesn't already have 3 cached
   MCQs, generate 3 UPSC Prelims-style questions using the new prompt and
   store them in the cached_questions table.

Both steps run concurrently with rate-limited AI calls.

Usage:
    DATABASE_URL=postgresql+asyncpg://... \
    NVIDIA_API_KEY=... \
    python -m app.scripts.batch_generate_all
"""

import asyncio
import logging
import os
import sys
import time
from uuid import UUID

import httpx
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config import settings
from app.models.article import Article
from app.models.category import Category
from app.models.cached_question import CachedQuestion
from app.ai.personas import question_setter as qs_persona
from app.ai.orchestrator import AIOrchestrator

logger = logging.getLogger("batch_generate_all")


def setup_logging():
    fmt = "%(asctime)s  %(levelname)-8s  %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


CATEGORIES = [
    "Polity", "History", "Geography", "Economy",
    "Environment", "Science & Tech", "International Relations",
    "Social Issues", "Security",
]

CATEGORY_PROMPT = """You are a UPSC category classifier. From this article headline and key facts, pick the single best category.

Categories: Polity, History, Geography, Economy, Environment, Science & Tech, International Relations, Social Issues, Security

Reply with ONLY the category name — one word only.

Headline: {headline}
Keywords: {keywords}
Context: {context}"""


class NIMClient:
    """Minimal rate-limited NIM API client for standalone batch scripts."""

    def __init__(self, api_key: str, base_url: str = "https://integrate.api.nvidia.com/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self._semaphore = asyncio.Semaphore(5)
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def _throttle(self):
        async with self._lock:
            now = time.monotonic()
            since = now - self._last_request
            if since < 1.5:
                await asyncio.sleep(1.5 - since)
            self._last_request = time.monotonic()

    async def _request(self, payload: dict) -> str | None:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=300.0) as client:
            for attempt in range(3):
                await self._throttle()
                try:
                    resp = await client.post("/chat/completions", json=payload, headers=headers)
                    if resp.status_code == 429 and attempt < 2:
                        retry = float(resp.headers.get("Retry-After", "5"))
                        await asyncio.sleep(retry * (2 ** attempt))
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
                except Exception as e:
                    logger.warning("NIM API attempt %d/3 failed: %s", attempt + 1, e)
                    if attempt < 2:
                        await asyncio.sleep(5 * (2 ** attempt))
        return None

    async def categorize(self, headline: str, keywords: str, context: str) -> str | None:
        payload = {
            "model": "mistralai/ministral-14b-instruct-2512",
            "messages": [
                {"role": "user", "content": CATEGORY_PROMPT.format(
                    headline=headline[:120],
                    keywords=keywords[:200],
                    context=context[:300],
                )},
            ],
            "temperature": 0.05,
            "max_tokens": 16,
        }
        async with self._semaphore:
            content = await self._request(payload)
        if content and content.strip() in CATEGORIES:
            return content.strip()
        return None

    async def generate_questions(self, article: dict) -> list[dict]:
        system, prompt = qs_persona.build_prompt([article], 3)
        payload = {
            "model": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 2048,
            "top_p": 0.9,
        }
        async with self._semaphore:
            content = await self._request(payload)
        if not content:
            return []
        parsed = qs_persona.parse_response(content)
        return parsed[:3]


async def run():
    t_start = time.time()
    logger.info("=" * 60)
    logger.info("BATCH GENERATE ALL — START")

    # --- DB connection ---
    db_url = os.environ.get("DATABASE_URL") or str(settings.database_url)
    if not db_url:
        logger.fatal("DATABASE_URL not set")
        sys.exit(1)
    if "postgresql" in db_url and "+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=3,
        connect_args={"statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # --- API client ---
    api_key = os.environ.get("NVIDIA_API_KEY") or str(settings.nvidia_api_key)
    if not api_key:
        logger.fatal("NVIDIA_API_KEY not set")
        sys.exit(1)
    nim = NIMClient(api_key)

    async with session_factory() as db:
        # Load category map
        cat_rows = (await db.execute(select(Category))).scalars().all()
        cat_map = {c.name: c.id for c in cat_rows}
        logger.info("Loaded %d categories: %s", len(cat_map), list(cat_map.keys()))

        # --- STEP 1: Category backfill ---
        uncategorized = (
            await db.execute(
                select(Article).where(Article.category_id.is_(None))
            )
        ).scalars().all()
        logger.info("STEP 1 — Uncategorized articles: %d", len(uncategorized))

        if uncategorized:
            cat_sem = asyncio.Semaphore(3)
            cat_errors = 0

            async def categorize_article(article: Article):
                nonlocal cat_errors
                async with cat_sem:
                    keywords = ", ".join((article.key_terms or [])[:6])
                    gk = (article.gk_summary or "")
                    cat_name = await nim.categorize(article.headline, keywords, gk)
                    if cat_name and cat_name in cat_map:
                        await db.execute(
                            update(Article)
                            .where(Article.id == article.id)
                            .values(category_id=cat_map[cat_name])
                        )
                        logger.info("  → %s → %s", article.headline[:60], cat_name)
                    else:
                        cat_errors += 1
                        logger.warning("  ? Could not categorize: %s (AI said: %s)", article.headline[:60], cat_name)

            await asyncio.gather(*[categorize_article(a) for a in uncategorized])
            await db.commit()
            logger.info("  Done. Errors: %d", cat_errors)

        # --- STEP 2: Question generation ---
        all_articles = (
            await db.execute(
                select(Article).order_by(Article.published_at.desc())
            )
        ).scalars().all()
        logger.info("STEP 2 — Total articles: %d", len(all_articles))

        # Check which articles already have enough cached questions
        article_ids = [a.id for a in all_articles]
        if article_ids:
            count_rows = await db.execute(
                select(
                    CachedQuestion.article_id,
                    func.count(CachedQuestion.id)
                ).where(
                    CachedQuestion.article_id.in_(article_ids)
                ).group_by(CachedQuestion.article_id)
            )
            existing_counts = {row[0]: row[1] for row in count_rows.fetchall()}
        else:
            existing_counts = {}

        to_generate = [
            a for a in all_articles
            if existing_counts.get(a.id, 0) < 3
        ]
        logger.info("  Already have 3 questions: %d", len(all_articles) - len(to_generate))
        logger.info("  Need questions: %d", len(to_generate))

        q_sem = asyncio.Semaphore(5)
        gen_ok = 0
        gen_errors = 0

        orchestrator = AIOrchestrator()

        async def generate_for_article(article: Article):
            nonlocal gen_ok, gen_errors
            gk = (article.gk_summary or article.body_text or "")[:1500]
            article_dict = {
                "id": str(article.id),
                "headline": article.headline,
                "gk_summary": gk,
                "syllabus_tag": article.syllabus_tag or "",
                "key_terms": article.key_terms or [],
            }

            async with q_sem:
                questions =  await orchestrator.generate_mcq_for_article(
                  article=article_dict, num_questions=3,
                )

            if not questions:
                gen_errors += 1
                logger.warning("  ✗ No questions for: %s", article.headline[:60])
                return

            existing_q = await db.execute(
                select(CachedQuestion.id)
                .where(CachedQuestion.article_id == article.id)
                .limit(1)
            )
            if existing_q.scalar_one_or_none() is not None:
                logger.info("  Already has questions (race condition): %s", article.headline[:60])
                return

            for q in questions:
                db.add(CachedQuestion(
                    article_id=article.id,
                    question_text=q["question_text"],
                    options=q["options"],
                    correct_answer=q["correct_answer"],
                    explanation=q.get("explanation"),
                    difficulty=q.get("difficulty"),
                ))
            gen_ok += 1
            logger.info("  ✓ %d questions for: %s", len(questions), article.headline[:60])

        batch_size = 20
        for i in range(0, len(to_generate), batch_size):
            batch = to_generate[i:i + batch_size]
            await asyncio.gather(*[generate_for_article(a) for a in batch])
            await db.commit()
            logger.info("  Batch %d/%d committed", i // batch_size + 1, (len(to_generate) + batch_size - 1) // batch_size)
            await asyncio.sleep(2)

        await db.commit()
        logger.info("STEP 2 done — Generated: %d, Errors: %d", gen_ok, gen_errors)

    await engine.dispose()
    elapsed = time.time() - t_start
    logger.info("=" * 60)
    logger.info("TOTAL DURATION: %.1fs", elapsed)
    logger.info("BATCH GENERATE ALL — DONE")
    return gen_ok > 0


if __name__ == "__main__":
    setup_logging()
    success = asyncio.run(run())
    sys.exit(0 if success else 1)
