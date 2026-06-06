from pathlib import Path
from uuid import UUID

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.model_registry import ModelRegistryEntry


class ModelConfig:
    def __init__(
        self,
        name: str,
        provider: str,
        max_tokens: int,
        temperature: float,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
    ) -> None:
        self.name = name
        self.provider = provider
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty


class ModelRegistry:
    def __init__(self, config_path: str | Path | None = None) -> None:
        self._config_path = Path(config_path or settings.models_config_path)
        self._models: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        with open(self._config_path) as f:
            data = yaml.safe_load(f)
        self._models = data.get("models", {})

    def get_active_model(self, persona: str) -> ModelConfig | None:
        persona_config = self._models.get(persona)
        if persona_config is None:
            return None
        active_name = persona_config.get("active")
        for candidate in persona_config.get("candidates", []):
            if candidate["name"] == active_name:
                return ModelConfig(
                    name=candidate["name"],
                    provider=candidate["provider"],
                    max_tokens=candidate.get("max_tokens", 512),
                    temperature=candidate.get("temperature", 0.3),
                    top_p=candidate.get("top_p", 1.0),
                    frequency_penalty=candidate.get("frequency_penalty", 0.0),
                    presence_penalty=candidate.get("presence_penalty", 0.0),
                )
        return None

    def list_models(self) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {}
        for persona, config in self._models.items():
            result[persona] = [
                {
                    "name": c["name"],
                    "provider": c["provider"],
                    "active": c["name"] == config.get("active"),
                }
                for c in config.get("candidates", [])
            ]
        return result

    def set_active_model(self, persona: str, model_name: str) -> bool:
        persona_config = self._models.get(persona)
        if persona_config is None:
            return False
        for candidate in persona_config.get("candidates", []):
            if candidate["name"] == model_name:
                persona_config["active"] = model_name
                self._save()
                return True
        return False

    def _save(self) -> None:
        with open(self._config_path, "w") as f:
            yaml.dump({"models": self._models}, f, default_flow_style=False)

    # --- DB-backed async methods ---

    async def db_get_active_model(
        self, db: AsyncSession, persona: str
    ) -> ModelConfig | None:
        result = await db.execute(
            select(ModelRegistryEntry).where(
                ModelRegistryEntry.persona == persona,
                ModelRegistryEntry.is_active == True,
            )
        )
        entry = result.scalar_one_or_none()
        if entry:
            return ModelConfig(
                name=entry.model_name,
                provider=entry.provider,
                max_tokens=entry.max_tokens,
                temperature=entry.temperature,
                top_p=entry.top_p,
                frequency_penalty=entry.frequency_penalty,
                presence_penalty=entry.presence_penalty,
            )
        return self.get_active_model(persona)

    async def db_list_models(self, db: AsyncSession) -> list[dict]:
        result = await db.execute(
            select(ModelRegistryEntry).order_by(ModelRegistryEntry.persona)
        )
        entries = result.scalars().all()
        if entries:
            model_list = []
            for e in entries:
                model_list.append(
                    {
                        "id": str(e.id),
                        "persona": e.persona,
                        "model_name": e.model_name,
                        "provider": e.provider,
                        "max_tokens": e.max_tokens,
                        "temperature": e.temperature,
                        "top_p": e.top_p,
                        "frequency_penalty": e.frequency_penalty,
                        "presence_penalty": e.presence_penalty,
                        "is_active": e.is_active,
                        "created_at": e.created_at.isoformat() if e.created_at else None,
                        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
                    }
                )
            return model_list
        yaml_data = self.list_models()
        model_list = []
        for persona, candidates in yaml_data.items():
            for c in candidates:
                model_list.append(
                    {
                        "persona": persona,
                        "model_name": c["name"],
                        "provider": c.get("provider", "nim"),
                        "is_active": c.get("active", False),
                    }
                )
        return model_list

    async def db_set_active_model(
        self,
        db: AsyncSession,
        persona: str,
        model_name: str,
    ) -> bool:
        result = await db.execute(
            select(ModelRegistryEntry).where(
                ModelRegistryEntry.persona == persona,
                ModelRegistryEntry.model_name == model_name,
            )
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return False
        await db.execute(
            select(ModelRegistryEntry).where(
                ModelRegistryEntry.persona == persona,
            )
        )
        all_entries = (await db.execute(
            select(ModelRegistryEntry).where(ModelRegistryEntry.persona == persona)
        )).scalars().all()
        for e in all_entries:
            e.is_active = (e.model_name == model_name)
        await db.flush()
        self.set_active_model(persona, model_name)
        return True

    async def db_seed_from_yaml(self, db: AsyncSession) -> int:
        existing = await db.execute(select(ModelRegistryEntry).limit(1))
        if existing.scalar_one_or_none() is not None:
            return 0
        count = 0
        for persona, config in self._models.items():
            active_name = config.get("active")
            for candidate in config.get("candidates", []):
                entry = ModelRegistryEntry(
                    persona=persona,
                    model_name=candidate["name"],
                    provider=candidate.get("provider", "nim"),
                    max_tokens=candidate.get("max_tokens", 512),
                    temperature=candidate.get("temperature", 0.3),
                    top_p=candidate.get("top_p", 1.0),
                    frequency_penalty=candidate.get("frequency_penalty", 0.0),
                    presence_penalty=candidate.get("presence_penalty", 0.0),
                    is_active=(candidate["name"] == active_name),
                )
                db.add(entry)
                count += 1
        await db.flush()
        return count


registry = ModelRegistry()
