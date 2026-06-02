import json
from uuid import UUID
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_interaction import AIInteraction


async def build_dataset(
    db: AsyncSession,
    persona: str | None = None,
    interaction_ids: List[UUID] | None = None,
) -> str:
    query = select(AIInteraction)

    if persona:
        query = query.where(AIInteraction.persona == persona)
    if interaction_ids:
        query = query.where(AIInteraction.id.in_(interaction_ids))

    result = await db.execute(query)
    interactions = result.scalars().all()

    records: list[str] = []
    for interaction in interactions:
        record = {
            "instruction": interaction.prompt_text[:500],
            "input": "",
            "output": interaction.response_text,
            "source": interaction.persona,
            "model": interaction.model_used,
        }
        records.append(json.dumps(record))

    return "\n".join(records)
