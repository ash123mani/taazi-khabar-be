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
import os
import sys
import time

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.scrapers.the_hindu import TheHinduScraper
from app.scrapers.indian_express import IndianExpressScraper
from app.services.article_service import bulk_upsert_articles
from app.ai.orchestrator import AIOrchestrator
from app.ai.model_registry import registry
from app.config import settings


async def run():
    db_url = os.environ.get("DATABASE_URL") or str(settings.database_url)
    if not db_url:
        print("FATAL: DATABASE_URL not set")
        sys.exit(1)

    engine = create_async_engine(db_url, pool_pre_ping=True, pool_size=2)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as db:
        try:
            await registry.db_seed_from_yaml(db)
            await db.commit()
        except Exception as e:
            print(f"WARN: model registry seed skipped ({e})")

    scrapers = [TheHinduScraper(), IndianExpressScraper()]
    all_articles = []
    errors = []

    for scraper in scrapers:
        name = scraper.__class__.__name__.replace("Scraper", "")
        print(f"\n--- Scraping {name} ---")
        try:
            articles = await scraper.scrape()
            print(f"  RSS entries: {len(articles)}")
            all_articles.extend(articles)
        except Exception as e:
            msg = f"{name}: {e}"
            print(f"  FAILED: {msg}")
            errors.append(msg)

    if not all_articles:
        print("\nNo articles scraped. Nothing to do.")
        return {"articles_created": 0, "articles_skipped": 0, "articles_filtered_out": 0, "errors": errors}

    orchestrator = AIOrchestrator()

    async def summarize(body: str, article_id=None, db=None):
        return await orchestrator.summarize_article(article_body=body, article_id=article_id, db=db)

    async def filterer(headline: str, body_text: str):
        return await orchestrator.filter_article(headline=headline, body_text=body_text, db=None)

    async with async_session() as db:
        created, skipped, summary_errors, filtered_out = await bulk_upsert_articles(
            db=db,
            articles=all_articles,
            summarizer=summarize,
            article_filter=filterer,
        )
        await db.commit()
        errors.extend(summary_errors)

    result = {
        "articles_found": len(all_articles),
        "articles_created": created,
        "articles_skipped": skipped,
        "articles_filtered_out": filtered_out,
        "errors": errors,
    }

    print(f"\n{'='*50}")
    print(f"Results:")
    print(f"  Found:     {result['articles_found']}")
    print(f"  Created:   {result['articles_created']}")
    print(f"  Skipped:   {result['articles_skipped']}")
    print(f"  Filtered:  {result['articles_filtered_out']}")
    if errors:
        print(f"  Errors ({len(errors)}):")
        for e in errors[:10]:
            print(f"    - {e}")
    print(f"{'='*50}")

    await engine.dispose()
    return result


if __name__ == "__main__":
    start = time.time()
    result = asyncio.run(run())
    elapsed = time.time() - start
    print(f"\nDuration: {elapsed:.1f}s")
