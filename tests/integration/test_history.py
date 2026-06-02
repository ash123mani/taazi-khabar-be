from __future__ import annotations

from uuid import uuid4
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header
from tests.integration.test_quiz import seed_article, MOCK_QUESTIONS


class TestListHistory:
    async def test_list_empty(self, client: AsyncClient, user_token: dict):
        res = await client.get("/api/history", headers=auth_header(user_token["token"]))
        assert res.status_code == 200
        assert res.json() == []

    async def test_list_with_data(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        article = await seed_article(db_session)
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            await client.post(
                "/api/quizzes/generate",
                json={"article_ids": [str(article.id)], "num_questions": 2},
                headers=auth_header(user_token["token"]),
            )
        res = await client.get("/api/history", headers=auth_header(user_token["token"]))
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["total_questions"] == 2

    async def test_list_pagination(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        article = await seed_article(db_session)
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            for _ in range(3):
                await client.post(
                    "/api/quizzes/generate",
                    json={"article_ids": [str(article.id)], "num_questions": 2},
                    headers=auth_header(user_token["token"]),
                )
        res = await client.get("/api/history?skip=0&limit=2", headers=auth_header(user_token["token"]))
        assert len(res.json()) == 2

    async def test_list_other_user_isolated(self, client: AsyncClient, db_session: AsyncSession, user_token: dict, second_user_token: dict):
        article = await seed_article(db_session)
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            await client.post(
                "/api/quizzes/generate",
                json={"article_ids": [str(article.id)], "num_questions": 2},
                headers=auth_header(user_token["token"]),
            )
        res = await client.get("/api/history", headers=auth_header(second_user_token["token"]))
        assert res.json() == []

    async def test_list_no_auth(self, client: AsyncClient):
        res = await client.get("/api/history")
        assert res.status_code == 403


class TestGetHistoryDetail:
    async def test_get_detail_success(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        article = await seed_article(db_session)
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            gen = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": [str(article.id)], "num_questions": 2},
                headers=auth_header(user_token["token"]),
            )
        quiz_id = gen.json()["quiz_id"]
        res = await client.get(f"/api/history/{quiz_id}", headers=auth_header(user_token["token"]))
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == quiz_id
        assert len(data["questions"]) == 2

    async def test_get_detail_not_found(self, client: AsyncClient, user_token: dict):
        res = await client.get(f"/api/history/{uuid4()}", headers=auth_header(user_token["token"]))
        assert res.status_code == 404

    async def test_get_detail_other_user_forbidden(self, client: AsyncClient, db_session: AsyncSession, user_token: dict, second_user_token: dict):
        article = await seed_article(db_session)
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            gen = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": [str(article.id)], "num_questions": 2},
                headers=auth_header(second_user_token["token"]),
            )
        res = await client.get(f"/api/history/{gen.json()['quiz_id']}", headers=auth_header(user_token["token"]))
        assert res.status_code == 404

    async def test_get_detail_no_auth(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        article = await seed_article(db_session)
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            gen = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": [str(article.id)], "num_questions": 2},
                headers=auth_header(user_token["token"]),
            )
        res = await client.get(f"/api/history/{gen.json()['quiz_id']}")
        assert res.status_code == 403

    async def test_get_detail_invalid_uuid(self, client: AsyncClient, user_token: dict):
        res = await client.get("/api/history/not-a-uuid", headers=auth_header(user_token["token"]))
        assert res.status_code == 422

    async def test_get_detail_shows_score_after_submit(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        article = await seed_article(db_session)
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            gen = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": [str(article.id)], "num_questions": 2},
                headers=auth_header(user_token["token"]),
            )
        quiz_id = gen.json()["quiz_id"]
        get_before = await client.get(f"/api/history/{quiz_id}", headers=auth_header(user_token["token"]))
        assert get_before.json()["score"] is None

        get_q = await client.get(f"/api/quizzes/{quiz_id}", headers=auth_header(user_token["token"]))
        questions = get_q.json()["questions"]
        await client.post(
            f"/api/quizzes/{quiz_id}/submit",
            json={"answers": {q["id"]: "B" for q in questions}},
            headers=auth_header(user_token["token"]),
        )
        get_after = await client.get(f"/api/history/{quiz_id}", headers=auth_header(user_token["token"]))
        assert get_after.json()["score"] == 2
