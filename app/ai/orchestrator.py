from uuid import UUID
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.model_registry import registry, ModelConfig
from app.ai.providers.nim import NIMProvider
from app.ai.personas import summarizer, question_setter
from app.ai.training.collector import log_interaction


class AIOrchestrator:
    def __init__(self) -> None:
        self._provider = NIMProvider()

    async def summarize_article(
        self,
        article_body: str,
        user_id: UUID | None = None,
        article_id: UUID | None = None,
        db: AsyncSession | None = None,
    ) -> dict[str, Any]:
        model_config = registry.get_active_model("summarizer")
        if model_config is None:
            raise ValueError("No active model configured for summarizer")

        system, prompt = summarizer.build_prompt(article_body)
        response = await self._provider.complete(
            prompt=prompt,
            system=system,
            max_tokens=model_config.max_tokens,
            temperature=model_config.temperature,
        )
        parsed = summarizer.parse_response(response.text)

        if db:
            await log_interaction(
                db=db,
                persona="summarizer",
                model_used=model_config.name,
                prompt_text=prompt,
                response_text=response.text,
                tokens_used=response.tokens_used,
                latency_ms=response.latency_ms,
                user_id=user_id,
                article_id=article_id,
            )

        return parsed

    async def generate_mcq(
        self,
        articles: list[dict[str, Any]],
        num_questions: int = 5,
        user_id: UUID | None = None,
        db: AsyncSession | None = None,
    ) -> list[dict[str, Any]]:
        model_config = registry.get_active_model("question_setter")
        if model_config is None:
            raise ValueError("No active model configured for question_setter")

        system, prompt = question_setter.build_prompt(articles, num_questions)
        response = await self._provider.complete(
            prompt=prompt,
            system=system,
            max_tokens=model_config.max_tokens,
            temperature=model_config.temperature,
        )
        parsed = question_setter.parse_response(response.text)

        if db:
            await log_interaction(
                db=db,
                persona="question_setter",
                model_used=model_config.name,
                prompt_text=prompt,
                response_text=response.text,
                tokens_used=response.tokens_used,
                latency_ms=response.latency_ms,
                user_id=user_id,
            )

        return parsed
