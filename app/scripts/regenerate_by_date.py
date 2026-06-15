"""Regenerate summaries for articles on a given date (new prompt format).

Usage:
    DATABASE_URL=postgresql+asyncpg://... python app/scripts/regenerate_by_date.py [YYYY-MM-DD]

If no date given, defaults to yesterday.
"""
import asyncio, time, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta
from sqlalchemy import select, cast, Date
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.models.article import Article
from app.models.ai_interaction import AIInteraction
from app.ai.model_registry import registry
from app.ai.providers.nim import NIMProvider
from app.ai.personas import summarizer

sem = asyncio.Semaphore(3)

async def process_one(session_factory, model_config, api_key, base_url, i, total, article_id, headline, body_text):
    async with sem:
        print(f"[{i}/{total}] {headline[:70]}...")
        try:
            t0 = time.monotonic()
            provider = NIMProvider()
            system, prompt = summarizer.build_prompt(body_text)
            response = await provider.complete(
                prompt=prompt, system=system, model=model_config.name,
                api_key=api_key, base_url=base_url,
                max_tokens=model_config.max_tokens,
                temperature=model_config.temperature,
                top_p=model_config.top_p,
                frequency_penalty=model_config.frequency_penalty,
                presence_penalty=model_config.presence_penalty,
            )
            elapsed = time.monotonic() - t0
            parsed = summarizer.parse_response(response.text)

            db = session_factory()
            article = await db.get(Article, article_id)
            article.gk_summary = parsed.get("gk_gist", response.text[:500])
            article.key_terms = parsed.get("key_terms", [])
            article.syllabus_tag = parsed.get("syllabus_topic")
            db.add(AIInteraction(
                persona="summarizer", model_used=model_config.name,
                prompt_text=prompt, response_text=response.text,
                tokens_used=response.tokens_used,
                latency_ms=response.latency_ms, article_id=article_id,
            ))
            await db.commit()
            await db.close()
            print(f"  ✓ {elapsed:.1f}s | {response.tokens_used} tokens")
        except Exception as e:
            print(f"  ✗ {type(e).__name__}: {e}")

async def main():
    target = date.today() - timedelta(days=1)
    if len(sys.argv) > 1:
        target = date.fromisoformat(sys.argv[1])
    print(f"Regenerating summaries for articles on {target}")

    engine = create_async_engine(
        settings.database_url, connect_args={"statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    model_config = registry.get_active_model("summarizer")
    api_key, base_url = settings.get_persona_credentials("summarizer")

    db = session_factory()
    result = await db.execute(
        select(Article.id, Article.headline, Article.body_text)
        .where(cast(Article.published_at, Date) == target)
    )
    rows = list(result.all())
    await db.close()

    total = len(rows)
    print(f"Found {total} articles\n")

    tasks = []
    for i, (article_id, headline, body_text) in enumerate(rows, 1):
        tasks.append(process_one(
            session_factory, model_config, api_key, base_url,
            i, total, article_id, headline, body_text,
        ))

    await asyncio.gather(*tasks)
    await engine.dispose()
    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(main())
