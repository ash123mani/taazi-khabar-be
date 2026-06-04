from pathlib import Path

import yaml

from app.config import settings


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
        raise NotImplementedError(
            "set_active_model is disabled. Use the admin API to update models via the database."
        )


registry = ModelRegistry()
