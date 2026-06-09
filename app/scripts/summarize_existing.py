"""Summarize remaining articles that lack gk_summary."""
import asyncio, time, sys

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

sys.path.insert(0, ".")
from app.config import settings
from app.models.article import Article
from app.models.ai_interaction import AIInteraction
from app.ai.model_registry import registry
from app.ai.providers.nim import NIMProvider
from app.ai.personas import summarizer


async def main():
    engine = create_async_engine(
        settings.database_url,
        connect_args={"statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    model_config = registry.get_active_model("summarizer")
    api_key, base_url = settings.get_persona_credentials("summarizer")
    provider = NIMProvider()

    db = session_factory()
    result = await db.execute(
        select(Article.id, Article.headline, Article.body_text)
        .where(Article.gk_summary.is_(None))
        .order_by(desc(Article.published_at))
    )
    rows = list(result.all())
    await db.close()
    print(f"Found {len(rows)} articles to summarize")

    for i, (article_id, headline, body_text) in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] Summarizing: {headline[:60]}...")
        try:
            system, prompt = summarizer.build_prompt(body_text)
            t0 = time.monotonic()
            response = await provider.complete(
                prompt=prompt,
                system=system,
                model=model_config.name,
                api_key=api_key,
                base_url=base_url,
                max_tokens=model_config.max_tokens,
                temperature=model_config.temperature,
                top_p=model_config.top_p,
                frequency_penalty=model_config.frequency_penalty,
                presence_penalty=model_config.presence_penalty,
            )
            elapsed = time.monotonic() - t0
            parsed = summarizer.parse_response(response.text)

            db2 = session_factory()
            article = await db2.get(Article, article_id)
            article.gk_summary = parsed.get("gk_gist", response.text[:500])
            article.key_terms = parsed.get("key_terms", [])
            article.syllabus_tag = parsed.get("syllabus_topic")
            interaction = AIInteraction(
                persona="summarizer",
                model_used=model_config.name,
                prompt_text=prompt,
                response_text=response.text,
                tokens_used=response.tokens_used,
                latency_ms=response.latency_ms,
                article_id=article_id,
            )
            db2.add(interaction)
            await db2.commit()
            await db2.close()
            print(f"  ✓ {elapsed:.1f}s | {response.tokens_used} tokens")
        except Exception as e:
            print(f"  ✗ {e}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
