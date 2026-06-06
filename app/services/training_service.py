from uuid import UUID
from typing import List

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training_dataset import TrainingDataset
from app.models.ai_interaction import AIInteraction


async def get_dataset_by_id(db: AsyncSession, dataset_id: UUID) -> TrainingDataset | None:
    return await db.get(TrainingDataset, dataset_id)


async def list_datasets(db: AsyncSession, skip: int = 0, limit: int = 20) -> List[TrainingDataset]:
    result = await db.execute(
        select(TrainingDataset).order_by(desc(TrainingDataset.created_at)).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def save_dataset(
    db: AsyncSession,
    persona: str,
    dataset_jsonl: str,
    record_count: int,
) -> TrainingDataset:
    dataset = TrainingDataset(
        persona=persona,
        format="alpaca",
        dataset_jsonl=dataset_jsonl,
        record_count=record_count,
    )
    db.add(dataset)
    await db.flush()
    return dataset


async def list_interactions(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    persona: str | None = None,
) -> List[AIInteraction]:
    query = select(AIInteraction).order_by(desc(AIInteraction.created_at))
    if persona:
        query = query.where(AIInteraction.persona == persona)
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all())
