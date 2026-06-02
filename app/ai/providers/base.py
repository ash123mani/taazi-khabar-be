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
        max_tokens: int = 512,
        temperature: float = 0.3,
    ) -> ProviderResponse:
        ...

    @abstractmethod
    async def complete_with_lora(
        self,
        prompt: str,
        system: str,
        lora_adapter: str,
    ) -> ProviderResponse:
        ...
