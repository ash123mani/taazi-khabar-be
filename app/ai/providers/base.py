from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProviderResponse:
    text: str
    tokens_used: int
    latency_ms: float


class BaseProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system: str,
        model: str = "",
        api_key: str = "",
        base_url: str = "",
        max_tokens: int = 512,
        temperature: float = 0.3,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
    ) -> ProviderResponse:
        ...

    @abstractmethod
    async def complete_with_lora(
        self,
        prompt: str,
        system: str,
        lora_adapter: str,
        api_key: str = "",
        base_url: str = "",
    ) -> ProviderResponse:
        ...
