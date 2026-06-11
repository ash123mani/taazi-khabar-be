"""
Standalone cron script for scheduled RSS scraping.

Runs in GitHub Actions (or any cron). Reads config from env vars,
connects directly to PostgreSQL (Supabase), scrapes both sources,
runs AI summarization + filtering, upserts articles.

Usage:
    DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db \
    NIM_SUMMARIZER_API_KEY=... \
    NIM_QUESTION_SETTER_API_KEY=... \
    python -m app.scripts.cron_scrape
"""

import asyncio
import logging
import os
import sys
import time
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.scrapers.the_hindu import TheHinduScraper
from app.scrapers.indian_express import IndianExpressScraper
from app.services.article_service import bulk_upsert_articles
from app.ai.orchestrator import AIOrchestrator
from app.ai.model_registry import registry
from app.config import settings

logger = logging.getLogger("cron_scrape")


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
    logging.getLogger("asyncio").setLevel(logging.WARNING)


async def run():
    cst = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    logger.info("=" * 60)
    logger.info("CRON SCRAPE START")
    logger.info("Local time: %s", cst)

    db_url = os.environ.get("DATABASE_URL") or str(settings.database_url)
    if not db_url:
        logger.fatal("DATABASE_URL not set")
        sys.exit(1)
    if "postgresql" in db_url and "+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    logger.info("Database URL scheme: %s", db_url.split("@")[0].split("://")[0] + "://")

    logger.info("Connecting to database ...")
    engine = create_async_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=2,
        connect_args={"statement_cache_size": 0},
    )
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as db:
        try:
            await registry.db_seed_from_yaml(db)
            await db.commit()
            logger.info("Model registry seeded")
        except Exception as e:
            logger.warning("Model registry seed skipped: %s", e)

    scrapers: list[tuple[str, str]] = [
        ("TheHindu", "thehindu"),
        ("IndianExpress", "indianexpress"),
    ]

    async def fetch_one(name: str, source: str) -> tuple[list, str | None]:
        scraper_cls = TheHinduScraper if source == "thehindu" else IndianExpressScraper
        logger.info("--- Scraping %s ---", name)
        t0 = time.time()
        try:
            articles = await scraper_cls().scrape()
            elapsed = time.time() - t0
            logger.info("  %s: %d articles fetched in %.1fs", name, len(articles), elapsed)
            for a in articles:
                logger.info("  · [%s] %s", a.source, a.headline[:100])
            return articles, None
        except Exception as e:
            logger.error("  %s FAILED: %s", name, e)
            return [], f"{name}: {e}"

    results = await asyncio.gather(*[fetch_one(n, s) for n, s in scrapers])
    all_articles = []
    errors = []
    for articles, err in results:
        all_articles.extend(articles)
        if err:
            errors.append(err)

    if not all_articles:
        logger.warning("No articles scraped. Nothing to do.")
        result = {
            "articles_found": 0,
            "articles_created": 0,
            "articles_skipped": 0,
            "articles_filtered_out": 0,
            "errors": errors,
        }
        await engine.dispose()
        return result

    logger.info("=" * 60)
    logger.info(
        "Processing %d articles (AI summarization + filtering) ...",
        len(all_articles),
    )

    orchestrator = AIOrchestrator()

    async def summarize(body: str):
        return await orchestrator.summarize_article(
            article_body=body, article_id=None, db=None,
        )

    async def filterer(headline: str, body_text: str):
        return await orchestrator.filter_article(
            headline=headline, body_text=body_text, db=None,
        )

    async def question_setter(
        article_id: UUID,
        headline: str,
        summary: str,
        syllabus_tag: str | None,
        key_terms: list[str] | None,
    ):
        article_dict = {
            "id": str(article_id),
            "headline": headline,
            "gk_summary": summary,
            "syllabus_tag": syllabus_tag or "",
            "key_terms": key_terms or [],
        }
        return await orchestrator.generate_mcq_for_article(
            article=article_dict, num_questions=3,
        )

    t0 = time.time()
    async with async_session() as db:
        created, skipped, summary_errors, filtered_out = await bulk_upsert_articles(
            db=db,
            articles=all_articles,
            summarizer=summarize,
            article_filter=filterer,
            question_setter=question_setter,
        )
        await db.commit()
        errors.extend(summary_errors)

    elapsed = time.time() - t0

    result = {
        "articles_found": len(all_articles),
        "articles_created": created,
        "articles_skipped": skipped,
        "articles_filtered_out": filtered_out,
        "errors": errors,
    }

    logger.info("=" * 60)
    logger.info("RESULTS")
    logger.info("  Articles found:     %d", result["articles_found"])
    logger.info("  Articles created:   %d", result["articles_created"])
    logger.info("  Articles skipped:   %d (already in DB)", result["articles_skipped"])
    logger.info("  Articles filtered:  %d (not UPSC-relevant)", result["articles_filtered_out"])
    logger.info("  Questions generated for each article (via question_setter)")
    logger.info("  AI processing time: %.1fs", elapsed)

    if summary_errors:
        logger.warning("Summarization errors: %d", len(summary_errors))
        for e in summary_errors[:10]:
            logger.warning("  - %s", e)
    if errors:
        logger.warning("Total errors: %d", len(errors))
        for e in errors[:10]:
            logger.warning("  - %s", e)

    logger.info("=" * 60)
    await engine.dispose()
    return result


if __name__ == "__main__":
    setup_logging()
    start = time.time()
    result = asyncio.run(run())
    elapsed = time.time() - start
    logger.info("Total duration: %.1fs", elapsed)
    sys.exit(0 if result["articles_created"] > 0 or result["errors"] else 1)
