import asyncio
import time
from typing import Any

import httpx

from app.ai.providers.base import BaseProvider, ProviderResponse
from app.config import settings


class NIMProvider(BaseProvider):
    def __init__(self, api_key: str = "", base_url: str = "") -> None:
        self._semaphore = asyncio.Semaphore(10)
        self._last_request_time = 0.0
        self._rate_limit_lock = asyncio.Lock()
        self.base_url = base_url or settings.nvidia_nim_base_url
        self.api_key = api_key or settings.nvidia_api_key.get_secret_value()
        self._client: httpx.AsyncClient | None = None
        self._current_base_url: str = ""

    async def _throttle(self) -> None:
        min_interval = 8.0
        async with self._rate_limit_lock:
            now = time.monotonic()
            since_last = now - self._last_request_time
            if since_last < min_interval:
                await asyncio.sleep(min_interval - since_last)
            self._last_request_time = time.monotonic()

    async def _get_client(self, base_url: str = "") -> httpx.AsyncClient:
        url = base_url or self.base_url
        if self._client is None or url != self._current_base_url:
            self._client = httpx.AsyncClient(base_url=url, timeout=60.0)
            self._current_base_url = url
        return self._client

    async def _request_with_retry(
        self, client: httpx.AsyncClient, payload: dict, headers: dict,
    ) -> ProviderResponse:
        last_exc: Exception | None = None
        for attempt in range(5):
            await self._throttle()
            start = time.monotonic()
            try:
                response = await client.post("/chat/completions", json=payload, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_exc = e
                if attempt < 4:
                    await asyncio.sleep(2 ** (attempt + 1))
                    continue
                raise
            elapsed = (time.monotonic() - start) * 1000.0
            if response.status_code == 429 and attempt < 4:
                try:
                    retry_after = float(response.headers.get("Retry-After", "5"))
                except (ValueError, TypeError):
                    retry_after = 5
                await asyncio.sleep(retry_after * (2 ** attempt))
                continue
            if response.status_code >= 500 and attempt < 4:
                await asyncio.sleep(2 ** (attempt + 1))
                continue
            response.raise_for_status()
            data = response.json()
            return ProviderResponse(
                text=data["choices"][0]["message"]["content"],
                tokens_used=data.get("usage", {}).get("total_tokens", 0),
                latency_ms=elapsed,
            )
        raise RuntimeError("Rate-limited after 5 retries")

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
        if not key:
            raise ValueError(
                "NVIDIA NIM API key is empty. "
                "Set NVIDIA_API_KEY (global) or NVIDIA_API_KEY_{persona} env var."
            )
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
        async with self._semaphore:
            return await self._request_with_retry(client, payload, headers)

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
        async with self._semaphore:
            return await self._request_with_retry(client, payload, headers)
