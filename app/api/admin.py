from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_admin_user
from app.models.user import User
from app.models.ai_interaction import AIInteraction
from app.ai.model_registry import registry
from app.services import training_service

router = APIRouter()


@router.get("/interactions", response_model=list[dict])
async def list_interactions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    persona: str | None = Query(None),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    interactions = await training_service.list_interactions(
        db=db, skip=skip, limit=limit, persona=persona
    )
    return [
        {
            "id": str(i.id),
            "persona": i.persona,
            "model_used": i.model_used,
            "tokens_used": i.tokens_used,
            "latency_ms": i.latency_ms,
            "user_id": str(i.user_id) if i.user_id else None,
            "created_at": i.created_at.isoformat(),
        }
        for i in interactions
    ]


@router.put("/interactions/{interaction_id}", response_model=dict)
async def update_interaction(
    interaction_id: UUID,
    data: dict,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        AIInteraction.__table__.select().where(AIInteraction.id == interaction_id)
    )
    interaction = result.scalar_one_or_none()
    if interaction is None:
        raise HTTPException(status_code=404, detail="Interaction not found")

    for key, value in data.items():
        if hasattr(interaction, key):
            setattr(interaction, key, value)

    await db.flush()
    return {"status": "updated", "id": str(interaction_id)}


@router.post("/datasets", response_model=dict)
async def create_dataset(
    persona: str = Query(...),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.ai.training.dataset_builder import build_dataset

    dataset_jsonl = await build_dataset(db=db, persona=persona)
    record_count = len([l for l in dataset_jsonl.split("\n") if l.strip()])

    dataset = await training_service.save_dataset(
        db=db,
        persona=persona,
        dataset_jsonl=dataset_jsonl,
        record_count=record_count,
    )

    return {
        "status": "created",
        "id": str(dataset.id),
        "persona": dataset.persona,
        "record_count": dataset.record_count,
    }


@router.get("/models", response_model=dict)
async def list_models(admin: User = Depends(get_admin_user)):
    return registry.list_models()


@router.put("/models", response_model=dict)
async def update_model(
    data: dict,
    admin: User = Depends(get_admin_user),
):
    persona = data.get("persona")
    model_name = data.get("model_name")
    if not persona or not model_name:
        raise HTTPException(status_code=400, detail="persona and model_name required")

    success = registry.set_active_model(persona, model_name)
    if not success:
        raise HTTPException(status_code=404, detail="Model not found for persona")
    return {"status": "updated", "persona": persona, "active_model": model_name}
