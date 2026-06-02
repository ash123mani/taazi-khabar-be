from __future__ import annotations

from uuid import uuid4
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header
from app.models.article import Article
from app.models.user import User


async def seed_article(db: AsyncSession) -> Article:
    article = Article(
        source="the_hindu",
        headline="Test Quiz Article",
        body_text="Body text for quiz testing. " * 30,
        url="https://example.com/quiz-article",
        published_at="2026-06-01T00:00:00+00:00",
        gk_summary="GK summary for quiz testing.",
    )
    db.add(article)
    await db.flush()
    await db.refresh(article)
    return article


MOCK_QUESTIONS = [
    {
        "question_text": "What is the capital of India?",
        "options": {"A": "Mumbai", "B": "New Delhi", "C": "Kolkata", "D": "Chennai"},
        "correct_answer": "B",
        "explanation": "New Delhi is the capital of India.",
        "difficulty": "Easy",
    },
    {
        "question_text": "Which river is longest?",
        "options": {"A": "Ganga", "B": "Yamuna", "C": "Brahmaputra", "D": "Godavari"},
        "correct_answer": "A",
        "explanation": "The Ganga is the longest river in India.",
        "difficulty": "Medium",
    },
]


class TestGenerateQuiz:
    async def test_generate_success(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        article = await seed_article(db_session)
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            res = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": [str(article.id)], "num_questions": 2},
                headers=auth_header(user_token["token"]),
            )
        assert res.status_code == 200, res.text
        data = res.json()
        assert "quiz_id" in data
        assert data["cached"] is False

    async def test_generate_no_auth(self, client: AsyncClient, db_session: AsyncSession):
        article = await seed_article(db_session)
        res = await client.post(
            "/api/quizzes/generate",
            json={"article_ids": [str(article.id)], "num_questions": 2},
        )
        assert res.status_code == 403

    async def test_generate_empty_article_ids(self, client: AsyncClient, user_token: dict):
        res = await client.post(
            "/api/quizzes/generate",
            json={"article_ids": [], "num_questions": 5},
            headers=auth_header(user_token["token"]),
        )
        assert res.status_code == 200

    async def test_generate_invalid_article_ids(self, client: AsyncClient, user_token: dict):
        res = await client.post(
            "/api/quizzes/generate",
            json={"article_ids": [str(uuid4())], "num_questions": 5},
            headers=auth_header(user_token["token"]),
        )
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=[]):
            res = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": [str(uuid4())], "num_questions": 5},
                headers=auth_header(user_token["token"]),
            )
        assert res.status_code == 200

    async def test_generate_invalid_uuid(self, client: AsyncClient, user_token: dict):
        res = await client.post(
            "/api/quizzes/generate",
            json={"article_ids": ["not-a-uuid"], "num_questions": 5},
            headers=auth_header(user_token["token"]),
        )
        assert res.status_code == 422

    async def test_generate_num_questions_zero(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        article = await seed_article(db_session)
        res = await client.post(
            "/api/quizzes/generate",
            json={"article_ids": [str(article.id)], "num_questions": 0},
            headers=auth_header(user_token["token"]),
        )
        assert res.status_code == 200

    async def test_generate_negative_num_questions(self, client: AsyncClient, user_token: dict):
        res = await client.post(
            "/api/quizzes/generate",
            json={"article_ids": [str(uuid4())], "num_questions": -1},
            headers=auth_header(user_token["token"]),
        )
        assert res.status_code == 422


class TestQuizCaching:
    async def test_same_input_returns_cached(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        article = await seed_article(db_session)
        ids = [str(article.id)]
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            res1 = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": ids, "num_questions": 2},
                headers=auth_header(user_token["token"]),
            )
        data1 = res1.json()
        assert data1["cached"] is False

        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq") as mock_gen:
            res2 = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": ids, "num_questions": 2},
                headers=auth_header(user_token["token"]),
            )
        data2 = res2.json()
        assert data2["cached"] is True
        assert data2["quiz_id"] == data1["quiz_id"]
        mock_gen.assert_not_called()

    async def test_different_articles_different_quiz(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        article1 = await seed_article(db_session)
        article2 = Article(
            source="the_hindu",
            headline="Second Article",
            body_text="Body of second article. " * 30,
            url="https://example.com/second-article",
            published_at="2026-06-02T00:00:00+00:00",
        )
        db_session.add(article2)
        await db_session.flush()
        await db_session.refresh(article2)

        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            res1 = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": [str(article1.id)], "num_questions": 2},
                headers=auth_header(user_token["token"]),
            )
            res2 = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": [str(article2.id)], "num_questions": 2},
                headers=auth_header(user_token["token"]),
            )
        assert res1.json()["quiz_id"] != res2.json()["quiz_id"]

    async def test_different_question_count_different_hash(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        article = await seed_article(db_session)
        ids = [str(article.id)]
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS[:1]):
            res1 = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": ids, "num_questions": 1},
                headers=auth_header(user_token["token"]),
            )
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            res2 = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": ids, "num_questions": 2},
                headers=auth_header(user_token["token"]),
            )
        assert res1.json()["quiz_id"] != res2.json()["quiz_id"]


class TestGetQuiz:
    async def test_get_quiz_success(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        article = await seed_article(db_session)
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            gen = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": [str(article.id)], "num_questions": 2},
                headers=auth_header(user_token["token"]),
            )
        quiz_id = gen.json()["quiz_id"]
        res = await client.get(f"/api/quizzes/{quiz_id}", headers=auth_header(user_token["token"]))
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == quiz_id
        assert data["total_questions"] == 2
        assert len(data["questions"]) == 2
        assert "correct_answer" not in data["questions"][0]

    async def test_get_quiz_not_found(self, client: AsyncClient, user_token: dict):
        res = await client.get(f"/api/quizzes/{uuid4()}", headers=auth_header(user_token["token"]))
        assert res.status_code == 404

    async def test_get_quiz_no_auth(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        article = await seed_article(db_session)
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            gen = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": [str(article.id)], "num_questions": 2},
                headers=auth_header(user_token["token"]),
            )
        res = await client.get(f"/api/quizzes/{gen.json()['quiz_id']}")
        assert res.status_code == 403

    async def test_get_quiz_other_user_forbidden(self, client: AsyncClient, db_session: AsyncSession, user_token: dict, second_user_token: dict):
        article = await seed_article(db_session)
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            gen = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": [str(article.id)], "num_questions": 2},
                headers=auth_header(second_user_token["token"]),
            )
        res = await client.get(f"/api/quizzes/{gen.json()['quiz_id']}", headers=auth_header(user_token["token"]))
        assert res.status_code == 404

    async def test_get_quiz_invalid_uuid(self, client: AsyncClient, user_token: dict):
        res = await client.get("/api/quizzes/not-a-uuid", headers=auth_header(user_token["token"]))
        assert res.status_code == 422


class TestSubmitQuiz:
    async def _create_and_get_quiz(self, client, token, db_session):
        article = await seed_article(db_session)
        with patch("app.ai.orchestrator.AIOrchestrator.generate_mcq", return_value=MOCK_QUESTIONS):
            gen = await client.post(
                "/api/quizzes/generate",
                json={"article_ids": [str(article.id)], "num_questions": 2},
                headers=auth_header(token),
            )
        quiz_id = gen.json()["quiz_id"]
        get = await client.get(f"/api/quizzes/{quiz_id}", headers=auth_header(token))
        questions = get.json()["questions"]
        return quiz_id, questions

    async def test_submit_all_correct(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        quiz_id, questions = await self._create_and_get_quiz(client, user_token["token"], db_session)
        answers = {q["id"]: "B" for q in questions}
        res = await client.post(
            f"/api/quizzes/{quiz_id}/submit",
            json={"answers": answers},
            headers=auth_header(user_token["token"]),
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["score"] == 2
        assert data["total_questions"] == 2
        assert len(data["results"]) == 2

    async def test_submit_all_wrong(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        quiz_id, questions = await self._create_and_get_quiz(client, user_token["token"], db_session)
        answers = {q["id"]: "A" for q in questions}
        res = await client.post(
            f"/api/quizzes/{quiz_id}/submit",
            json={"answers": answers},
            headers=auth_header(user_token["token"]),
        )
        data = res.json()
        assert data["score"] == 0
        assert all(r["is_correct"] is False for r in data["results"])

    async def test_submit_partial(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        quiz_id, questions = await self._create_and_get_quiz(client, user_token["token"], db_session)
        answers = {questions[0]["id"]: "B"}
        res = await client.post(
            f"/api/quizzes/{quiz_id}/submit",
            json={"answers": answers},
            headers=auth_header(user_token["token"]),
        )
        data = res.json()
        assert data["score"] == 1
        assert len(data["results"]) == 1

    async def test_submit_no_auth(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        quiz_id, questions = await self._create_and_get_quiz(client, user_token["token"], db_session)
        res = await client.post(
            f"/api/quizzes/{quiz_id}/submit",
            json={"answers": {questions[0]["id"]: "B"}},
        )
        assert res.status_code == 403

    async def test_submit_not_found(self, client: AsyncClient, user_token: dict):
        res = await client.post(
            f"/api/quizzes/{uuid4()}/submit",
            json={"answers": {}},
            headers=auth_header(user_token["token"]),
        )
        assert res.status_code == 404

    async def test_submit_other_user_forbidden(self, client: AsyncClient, db_session: AsyncSession, user_token: dict, second_user_token: dict):
        quiz_id, questions = await self._create_and_get_quiz(client, second_user_token["token"], db_session)
        res = await client.post(
            f"/api/quizzes/{quiz_id}/submit",
            json={"answers": {questions[0]["id"]: "B"}},
            headers=auth_header(user_token["token"]),
        )
        assert res.status_code == 404

    async def test_submit_already_submitted(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        quiz_id, questions = await self._create_and_get_quiz(client, user_token["token"], db_session)
        answers = {q["id"]: "B" for q in questions}
        res1 = await client.post(
            f"/api/quizzes/{quiz_id}/submit",
            json={"answers": answers},
            headers=auth_header(user_token["token"]),
        )
        assert res1.status_code == 200
        res2 = await client.post(
            f"/api/quizzes/{quiz_id}/submit",
            json={"answers": answers},
            headers=auth_header(user_token["token"]),
        )
        assert res2.status_code == 400
        assert "already submitted" in res2.json()["detail"].lower()

    async def test_submit_updates_quiz_score(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        quiz_id, questions = await self._create_and_get_quiz(client, user_token["token"], db_session)
        answers = {q["id"]: "B" for q in questions}
        await client.post(
            f"/api/quizzes/{quiz_id}/submit",
            json={"answers": answers},
            headers=auth_header(user_token["token"]),
        )
        get = await client.get(f"/api/quizzes/{quiz_id}", headers=auth_header(user_token["token"]))
        assert get.json()["score"] == 2

    async def test_submit_empty_answers(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        quiz_id, questions = await self._create_and_get_quiz(client, user_token["token"], db_session)
        res = await client.post(
            f"/api/quizzes/{quiz_id}/submit",
            json={"answers": {}},
            headers=auth_header(user_token["token"]),
        )
        assert res.status_code == 200
        assert res.json()["score"] == 0

    async def test_submit_invalid_question_id(self, client: AsyncClient, db_session: AsyncSession, user_token: dict):
        quiz_id, questions = await self._create_and_get_quiz(client, user_token["token"], db_session)
        answers = {str(uuid4()): "B"}
        res = await client.post(
            f"/api/quizzes/{quiz_id}/submit",
            json={"answers": answers},
            headers=auth_header(user_token["token"]),
        )
        assert res.status_code == 200
        assert res.json()["score"] == 0
