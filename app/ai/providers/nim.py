import time
from typing import Any

import httpx

from app.ai.providers.base import BaseProvider, ProviderResponse
from app.config import settings


class NIMProvider(BaseProvider):
    def __init__(self) -> None:
        self.base_url = settings.nvidia_nim_base_url
        self.api_key = settings.nvidia_api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=60.0,
            )
        return self._client

    async def complete(
        self,
        prompt: str,
        system: str,
        max_tokens: int = 512,
        temperature: float = 0.3,
    ) -> ProviderResponse:
        client = await self._get_client()
        payload: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        start = time.monotonic()
        response = await client.post("/chat/completions", json=payload, headers=headers)
        elapsed = (time.monotonic() - start) * 1000.0
        response.raise_for_status()
        data = response.json()

        return ProviderResponse(
            text=data["choices"][0]["message"]["content"],
            tokens_used=data.get("usage", {}).get("total_tokens", 0),
            latency_ms=elapsed,
        )

    async def complete_with_lora(
        self,
        prompt: str,
        system: str,
        lora_adapter: str,
    ) -> ProviderResponse:
        client = await self._get_client()
        payload: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 512,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "NVCF_LORA_ADAPTER": lora_adapter,
        }

        start = time.monotonic()
        response = await client.post("/chat/completions", json=payload, headers=headers)
        elapsed = (time.monotonic() - start) * 1000.0
        response.raise_for_status()
        data = response.json()

        return ProviderResponse(
            text=data["choices"][0]["message"]["content"],
            tokens_used=data.get("usage", {}).get("total_tokens", 0),
            latency_ms=elapsed,
        )
