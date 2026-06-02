from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_interaction import AIInteraction


async def log_interaction(
    db: AsyncSession,
    persona: str,
    model_used: str,
    prompt_text: str,
    response_text: str,
    tokens_used: int | None = None,
    latency_ms: float | None = None,
    user_id: UUID | None = None,
    article_id: UUID | None = None,
) -> AIInteraction:
    interaction = AIInteraction(
        persona=persona,
        model_used=model_used,
        prompt_text=prompt_text,
        response_text=response_text,
        tokens_used=tokens_used,
        latency_ms=latency_ms,
        user_id=user_id,
        article_id=article_id,
    )
    db.add(interaction)
    await db.flush()
    return interaction
