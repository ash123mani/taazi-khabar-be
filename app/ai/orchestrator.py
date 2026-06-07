from uuid import UUID
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.model_registry import registry
from app.ai.providers.nim import NIMProvider
from app.ai.personas import summarizer, question_setter, article_filter
from app.ai.training.collector import log_interaction
from app.config import settings


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
        api_key, base_url = settings.get_persona_credentials("summarizer")

        system, prompt = summarizer.build_prompt(article_body)
        response = await self._provider.complete(
            prompt=prompt,
            system=system,
            model=model_config.name,
            api_key=api_key,
            base_url=base_url,
            max_tokens=model_config.max_tokens,
            temperature=model_config.temperature,
            top_p=model_config.top_p,
            frequency_penalty=model_config.frequency_penalty,
            presence_penalty=model_config.presence_penalty,
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

    async def filter_article(
        self,
        headline: str,
        body_text: str,
        user_id: UUID | None = None,
        db: AsyncSession | None = None,
    ) -> bool:
        model_config = registry.get_active_model("article_filter")
        if model_config is None:
            return True
        api_key, base_url = settings.get_persona_credentials("article_filter")

        system, prompt = article_filter.build_prompt(headline, body_text)
        response = await self._provider.complete(
            prompt=prompt,
            system=system,
            model=model_config.name,
            api_key=api_key,
            base_url=base_url,
            max_tokens=model_config.max_tokens,
            temperature=model_config.temperature,
            top_p=model_config.top_p,
        )
        is_relevant = article_filter.parse_response(response.text)

        if db:
            await log_interaction(
                db=db,
                persona="article_filter",
                model_used=model_config.name,
                prompt_text=prompt,
                response_text=response.text,
                tokens_used=response.tokens_used,
                latency_ms=response.latency_ms,
                user_id=user_id,
            )

        return is_relevant

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
        api_key, base_url = settings.get_persona_credentials("question_setter")

        system, prompt = question_setter.build_prompt(articles, num_questions)
        response = await self._provider.complete(
            prompt=prompt,
            system=system,
            model=model_config.name,
            api_key=api_key,
            base_url=base_url,
            max_tokens=model_config.max_tokens,
            temperature=model_config.temperature,
            top_p=model_config.top_p,
            frequency_penalty=model_config.frequency_penalty,
            presence_penalty=model_config.presence_penalty,
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

    async def generate_mcq_for_article(
        self,
        article: dict[str, Any],
        num_questions: int = 3,
        user_id: UUID | None = None,
        db: AsyncSession | None = None,
    ) -> list[dict[str, Any]]:
        return await self.generate_mcq(
            articles=[article],
            num_questions=num_questions,
            user_id=user_id,
            db=db,
        )
