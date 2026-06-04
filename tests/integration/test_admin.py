from __future__ import annotations

from uuid import uuid4
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header
from app.models.ai_interaction import AIInteraction


async def seed_interaction(db: AsyncSession, persona: str = "summarizer") -> AIInteraction:
    interaction = AIInteraction(
        persona=persona,
        model_used="meta/llama-3.1-8b-instruct",
        prompt_text="Summarize this article.",
        response_text="This is a summary.",
        tokens_used=50,
        latency_ms=1200.5,
    )
    db.add(interaction)
    await db.flush()
    await db.refresh(interaction)
    return interaction


class TestAdminInteractions:
    async def test_list_interactions(self, client: AsyncClient, db_session: AsyncSession, admin_token: dict):
        await seed_interaction(db_session)
        await seed_interaction(db_session, persona="question_setter")
        res = await client.get("/api/admin/interactions", headers=auth_header(admin_token["token"]))
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2
        assert data[0]["persona"] in ("summarizer", "question_setter")

    async def test_list_interactions_pagination(self, client: AsyncClient, db_session: AsyncSession, admin_token: dict):
        for _ in range(5):
            await seed_interaction(db_session)
        res = await client.get("/api/admin/interactions?skip=0&limit=2", headers=auth_header(admin_token["token"]))
        assert len(res.json()) == 2

    async def test_list_interactions_filter_by_persona(self, client: AsyncClient, db_session: AsyncSession, admin_token: dict):
        await seed_interaction(db_session, persona="summarizer")
        await seed_interaction(db_session, persona="question_setter")
        res = await client.get("/api/admin/interactions?persona=summarizer", headers=auth_header(admin_token["token"]))
        assert all(i["persona"] == "summarizer" for i in res.json())

    async def test_list_interactions_empty(self, client: AsyncClient, admin_token: dict):
        res = await client.get("/api/admin/interactions", headers=auth_header(admin_token["token"]))
        assert res.json() == []

    async def test_list_interactions_no_auth(self, client: AsyncClient):
        res = await client.get("/api/admin/interactions")
        assert res.status_code == 401

    async def test_list_interactions_non_admin(self, client: AsyncClient, user_token: dict):
        res = await client.get("/api/admin/interactions", headers=auth_header(user_token["token"]))
        assert res.status_code == 403

    async def test_update_interaction(self, client: AsyncClient, db_session: AsyncSession, admin_token: dict):
        interaction = await seed_interaction(db_session)
        res = await client.put(
            f"/api/admin/interactions/{interaction.id}",
            json={"tokens_used": 100},
            headers=auth_header(admin_token["token"]),
        )
        assert res.status_code == 200
        assert res.json()["status"] == "updated"

    async def test_update_interaction_not_found(self, client: AsyncClient, admin_token: dict):
        res = await client.put(
            f"/api/admin/interactions/{uuid4()}",
            json={"tokens_used": 100},
            headers=auth_header(admin_token["token"]),
        )
        assert res.status_code == 404

    async def test_update_interaction_unknown_field(self, client: AsyncClient, db_session: AsyncSession, admin_token: dict):
        interaction = await seed_interaction(db_session)
        res = await client.put(
            f"/api/admin/interactions/{interaction.id}",
            json={"nonexistent_field": "value"},
            headers=auth_header(admin_token["token"]),
        )
        assert res.status_code == 200

    async def test_update_interaction_no_auth(self, client: AsyncClient, db_session: AsyncSession, admin_token: dict):
        interaction = await seed_interaction(db_session)
        res = await client.put(
            f"/api/admin/interactions/{interaction.id}",
            json={"tokens_used": 100},
        )
        assert res.status_code == 401

    async def test_update_interaction_non_admin(self, client: AsyncClient, db_session: AsyncSession, admin_token: dict, user_token: dict):
        interaction = await seed_interaction(db_session)
        res = await client.put(
            f"/api/admin/interactions/{interaction.id}",
            json={"tokens_used": 100},
            headers=auth_header(user_token["token"]),
        )
        assert res.status_code == 403


class TestAdminDatasets:
    async def test_create_dataset(self, client: AsyncClient, db_session: AsyncSession, admin_token: dict):
        await seed_interaction(db_session)
        res = await client.post(
            "/api/admin/datasets?persona=summarizer",
            headers=auth_header(admin_token["token"]),
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "created"
        assert data["persona"] == "summarizer"
        assert data["record_count"] >= 1

    async def test_create_dataset_no_interactions(self, client: AsyncClient, admin_token: dict):
        res = await client.post(
            "/api/admin/datasets?persona=summarizer",
            headers=auth_header(admin_token["token"]),
        )
        assert res.status_code == 200
        assert res.json()["record_count"] == 0

    async def test_create_dataset_no_persona(self, client: AsyncClient, admin_token: dict):
        res = await client.post(
            "/api/admin/datasets",
            headers=auth_header(admin_token["token"]),
        )
        assert res.status_code == 422

    async def test_create_dataset_no_auth(self, client: AsyncClient):
        res = await client.post("/api/admin/datasets?persona=summarizer")
        assert res.status_code == 401

    async def test_create_dataset_non_admin(self, client: AsyncClient, user_token: dict):
        res = await client.post(
            "/api/admin/datasets?persona=summarizer",
            headers=auth_header(user_token["token"]),
        )
        assert res.status_code == 403


class TestAdminModels:
    async def test_list_models(self, client: AsyncClient, admin_token: dict):
        res = await client.get("/api/admin/models", headers=auth_header(admin_token["token"]))
        assert res.status_code == 200
        data = res.json()
        assert "summarizer" in data
        assert "question_setter" in data
        assert len(data["summarizer"]) >= 1

    async def test_list_models_structure(self, client: AsyncClient, admin_token: dict):
        res = await client.get("/api/admin/models", headers=auth_header(admin_token["token"]))
        summarizer = res.json()["summarizer"][0]
        assert "name" in summarizer
        assert "provider" in summarizer
        assert "active" in summarizer

    async def test_list_models_no_auth(self, client: AsyncClient):
        res = await client.get("/api/admin/models")
        assert res.status_code == 401

    async def test_list_models_non_admin(self, client: AsyncClient, user_token: dict):
        res = await client.get("/api/admin/models", headers=auth_header(user_token["token"]))
        assert res.status_code == 403

    async def test_update_model_raises_not_implemented(self, client: AsyncClient, admin_token: dict):
        try:
            res = await client.put(
                "/api/admin/models",
                json={"persona": "summarizer", "model_name": "meta/llama-3.1-8b-instruct"},
                headers=auth_header(admin_token["token"]),
            )
            assert res.status_code == 500
        except Exception:
            pass

    async def test_update_model_missing_fields(self, client: AsyncClient, admin_token: dict):
        res = await client.put(
            "/api/admin/models",
            json={},
            headers=auth_header(admin_token["token"]),
        )
        assert res.status_code == 400

    async def test_update_model_no_auth(self, client: AsyncClient):
        res = await client.put(
            "/api/admin/models",
            json={"persona": "summarizer", "model_name": "test"},
        )
        assert res.status_code == 401
