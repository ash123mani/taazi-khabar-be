"""
Usage: python -m app.scripts.filter_articles 2026-06-04 [2026-06-05 ...]

Fetches articles for given date(s) from DB, runs each through the AI
relevance filter, and deletes articles that are NOT UPSC-relevant.

Shows count of articles to be deleted and asks for confirmation
before proceeding.
"""

import asyncio
import sys
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.ai.orchestrator import AIOrchestrator


async def main():
    if len(sys.argv) < 2:
        print(f"Usage: python -m app.scripts.filter_articles YYYY-MM-DD [YYYY-MM-DD ...]")
        sys.exit(1)

    target_dates = []
    for d in sys.argv[1:]:
        try:
            target_dates.append(date.fromisoformat(d))
        except ValueError:
            print(f"Invalid date: {d}. Use YYYY-MM-DD.")
            sys.exit(1)

    engine = create_async_engine(settings.database_url)
    orchestrator = AIOrchestrator()

    all_to_delete = []

    for target_date in target_dates:
        date_str = target_date.isoformat()
        print(f"\n{'='*60}")
        print(f"Processing date: {date_str}")
        print(f"{'='*60}")

        async with engine.connect() as conn:
            rows = (await conn.execute(
                text("SELECT id, headline, body_text FROM articles WHERE CAST(published_at AS date) = :d ORDER BY published_at"),
                {"d": target_date},
            )).fetchall()

        if not rows:
            print(f"  No articles found for {date_str}")
            continue

        print(f"  Total articles: {len(rows)}")

        to_delete = []
        for article_id, headline, body_text in rows:
            print(f"  Filtering: {headline[:70]}...", end=" ")
            try:
                is_relevant = await orchestrator.filter_article(
                    headline=headline,
                    body_text=body_text,
                )
            except Exception as e:
                print(f"ERROR: {e}")
                continue

            if is_relevant:
                print("UPSC-relevant ✓")
            else:
                print("NOT relevant ✗ → will delete")
                to_delete.append(article_id)

        if not to_delete:
            print(f"\n  ✓ All {len(rows)} articles are UPSC-relevant. Nothing to delete.")
            continue

        print(f"\n  {'*'*50}")
        print(f"  {len(to_delete)} of {len(rows)} articles will be DELETED.")
        print(f"  {'*'*50}")

        confirm = input(f"  Delete {len(to_delete)} articles from {date_str}? [y/N]: ")
        if confirm.lower() != "y":
            print("  Skipped.")
            continue

        async with engine.begin() as conn:
            for aid in to_delete:
                await conn.execute(text("DELETE FROM quiz_articles WHERE article_id = :id"), {"id": aid})
                await conn.execute(text("DELETE FROM ai_interactions WHERE article_id = :id"), {"id": aid})
                await conn.execute(text("DELETE FROM articles WHERE id = :id"), {"id": aid})

        all_to_delete.extend(to_delete)
        print(f"  ✓ Deleted {len(to_delete)} non-UPSC articles from {date_str}")

    await engine.dispose()
    print(f"\nDone. Deleted {len(all_to_delete)} articles total.")


if __name__ == "__main__":
    asyncio.run(main())
