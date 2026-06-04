import time
from typing import Any

import httpx

from app.ai.providers.base import BaseProvider, ProviderResponse
from app.config import settings


class NIMProvider(BaseProvider):
    def __init__(self) -> None:
        self.base_url = settings.nvidia_nim_base_url
        self.api_key = settings.nvidia_api_key.get_secret_value()
        self._client: httpx.AsyncClient | None = None
        self._current_base_url: str = ""

    async def _get_client(self, base_url: str = "") -> httpx.AsyncClient:
        url = base_url or self.base_url
        if self._client is None or url != self._current_base_url:
            self._client = httpx.AsyncClient(base_url=url, timeout=60.0)
            self._current_base_url = url
        return self._client

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
        key = api_key or self.api_key
        client = await self._get_client(base_url)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
        }

        headers = {
            "Authorization": f"Bearer {key}",
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
        api_key: str = "",
        base_url: str = "",
    ) -> ProviderResponse:
        key = api_key or self.api_key
        client = await self._get_client(base_url)
        payload: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 512,
        }

        headers = {
            "Authorization": f"Bearer {key}",
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
