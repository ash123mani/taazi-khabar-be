import json
from uuid import UUID
from typing import List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_interaction import AIInteraction
from app.models.article import Article


async def build_dataset(
    db: AsyncSession,
    persona: str | None = None,
    interaction_ids: List[UUID] | None = None,
) -> str:
    records: list[str] = []

    if persona == "article_summarizer":
        query = select(Article).where(
            and_(Article.body_text.isnot(None), Article.gk_summary.isnot(None))
        )
        result = await db.execute(query)
        articles = result.scalars().all()

        for article in articles:
            instruction = (
                "Summarize the following UPSC current affairs article in a concise GK summary. "
                "Include key terms and a syllabus tag."
            )
            record = {
                "instruction": instruction,
                "input": article.body_text[:2000],
                "output": article.gk_summary,
                "source": f"article:{article.source}",
                "headline": article.headline,
                "key_terms": article.key_terms or [],
                "syllabus_tag": article.syllabus_tag or "",
            }
            records.append(json.dumps(record))

    query = select(AIInteraction)

    if persona:
        query = query.where(AIInteraction.persona == persona)
    if interaction_ids:
        query = query.where(AIInteraction.id.in_(interaction_ids))

    result = await db.execute(query)
    interactions = result.scalars().all()

    seen_outputs = {r.get("output") for r in (json.loads(r) for r in records)}

    for interaction in interactions:
        if interaction.response_text in seen_outputs:
            continue
        seen_outputs.add(interaction.response_text)
        record = {
            "instruction": interaction.prompt_text[:500],
            "input": "",
            "output": interaction.response_text,
            "source": interaction.persona,
            "model": interaction.model_used,
        }
        records.append(json.dumps(record))

    return "\n".join(records)
