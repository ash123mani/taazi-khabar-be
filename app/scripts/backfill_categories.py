"""Backfill category_id and syllabus_tag for articles missing them.

Usage: python -m app.scripts.backfill_categories [--limit N] [--date YYYY-MM-DD]
"""
import asyncio
from datetime import date
import re
import sys

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

sys.path.insert(0, ".")
from app.ai.model_registry import registry
from app.ai.providers.nim import NIMProvider
from app.config import settings
from app.models.article import Article
from app.models.category import Category


EXTRACT_SYSTEM = "You are a UPSC current affairs analyst. Extract the syllabus tag and category from the article."
EXTRACT_PROMPT = """Based on this UPSC news article body, output exactly two lines:

Syllabus Tag: GS Paper number — Topic name (e.g. "GS Paper 2 — Polity & Governance: Constitutional Bodies")
Category: One word from: Polity, History, Geography, Economy, Environment, Science & Tech, International Relations, Social Issues, Security

Article body:
{body}"""


async def main():
    limit = None
    target_date = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--limit" and i < len(sys.argv):
            limit = int(sys.argv[i + 1])
        if arg == "--date" and i < len(sys.argv):
            target_date = sys.argv[i + 1]

    engine = create_async_engine(
        settings.database_url,
        connect_args={"statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        await registry.db_seed_from_yaml(db)
        await db.commit()

    # Get model config for summarizer (same model used for extraction)
    model_config = registry.get_active_model("summarizer")
    if model_config is None:
        print("ERROR: No active model configured for summarizer")
        await engine.dispose()
        return
    api_key, base_url = settings.get_persona_credentials("summarizer")
    provider = NIMProvider()

    async with session_factory() as db:
        if target_date:
            from datetime import date
            target = date.fromisoformat(target_date)
            query = text("""
                SELECT id, body_text, headline
                FROM articles
                WHERE category_id IS NULL
                AND DATE(scraped_at AT TIME ZONE 'UTC') = :target_date
            """)
            result = await db.execute(query, {"target_date": target})
        else:
            query = text("""
                SELECT id, body_text, headline
                FROM articles
                WHERE category_id IS NULL
            """)
            result = await db.execute(query)
        rows = result.all()
        if limit:
            rows = rows[:limit]
        print(f"Found {len(rows)} articles without category_id")

    if not rows:
        print("Nothing to do.")
        await engine.dispose()
        return

    async with session_factory() as db:
        cats = (await db.execute(select(Category))).scalars().all()
        cat_map = {c.name.lower(): c.id for c in cats}
        print(f"Known categories: {list(cat_map.keys())}")

    updated = 0
    errors = 0

    for row in rows:
        article_id, body_text, headline = row
        print(f"\n[{updated + errors + 1}/{len(rows)}] {headline[:70]}...", end=" ")

        try:
            prompt = EXTRACT_PROMPT.format(body=body_text[:3000])
            response = await provider.complete(
                prompt=prompt,
                system=EXTRACT_SYSTEM,
                model=model_config.name,
                api_key=api_key,
                base_url=base_url,
                max_tokens=128,
                temperature=0.05,
                top_p=1.0,
            )

            syllabus_tag = None
            category_name = None
            resp_text = response.text.strip()
            m = re.search(r"(?:syllabus\s+tag)[:\s]+(.+)", resp_text, re.IGNORECASE)
            if m:
                syllabus_tag = m.group(1).replace("*", "").strip()
            m = re.search(r"(?:category)[:\s]+(.+)", resp_text, re.IGNORECASE)
            if m:
                category_name = m.group(1).replace("*", "").strip()

            if not syllabus_tag and not category_name:
                print(f"✗ (no tag/category returned) — response: {response.text[:200]}")
                errors += 1
                continue

            # Handle edge cases: multi-category (pick first), Culture → History
            resolved_cat = category_name
            if category_name:
                if "/" in category_name:
                    resolved_cat = category_name.split("/")[0].strip()
                lookup = cat_map.get(resolved_cat.lower())
                if not lookup and resolved_cat.lower() == "culture":
                    resolved_cat = "history"
                    lookup = cat_map.get(resolved_cat)

            async with session_factory() as db2:
                art = await db2.get(Article, article_id)
                if syllabus_tag:
                    art.syllabus_tag = syllabus_tag
                if resolved_cat and lookup:
                    art.category_id = lookup
                elif category_name and not lookup:
                    print(f"⚠ (no match for '{category_name}' → '{resolved_cat}')")
                await db2.commit()

            updated += 1
            print(f"✓ tag={syllabus_tag}, cat={resolved_cat or category_name}")

        except Exception as e:
            print(f"✗ {e}")
            errors += 1

    print(f"\nDone. Updated {updated}/{len(rows)} articles ({errors} errors).")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
