from __future__ import annotations

from httpx import AsyncClient
import pytest


class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        res = await client.post("/api/auth/register", json={
            "email": "new@example.com",
            "password": "StrongPass1!",
            "name": "New User",
        })
        assert res.status_code == 201, res.text
        data = res.json()
        assert data["access_token"]
        assert data["user"]["email"] == "new@example.com"
        assert data["user"]["name"] == "New User"
        assert data["user"]["id"]

    async def test_register_duplicate_email(self, client: AsyncClient, user_token: dict):
        res = await client.post("/api/auth/register", json={
            "email": user_token["email"],
            "password": "OtherPass1!",
        })
        assert res.status_code == 409, res.text
        assert "already registered" in res.json()["detail"].lower()

    async def test_register_empty_body(self, client: AsyncClient):
        res = await client.post("/api/auth/register", json={})
        assert res.status_code == 422

    async def test_register_no_password(self, client: AsyncClient):
        res = await client.post("/api/auth/register", json={"email": "nopass@example.com"})
        assert res.status_code == 422

    async def test_register_no_email(self, client: AsyncClient):
        res = await client.post("/api/auth/register", json={"password": "SomePass1!"})
        assert res.status_code == 422

    async def test_register_name_optional(self, client: AsyncClient):
        res = await client.post("/api/auth/register", json={
            "email": "noname@example.com",
            "password": "SomePass1!",
        })
        assert res.status_code == 201
        assert res.json()["user"]["name"] is None


class TestLogin:
    async def test_login_success(self, client: AsyncClient, user_token: dict):
        res = await client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "TestPass123!",
        })
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["access_token"]
        assert data["user"]["email"] == "test@example.com"

    async def test_login_wrong_password(self, client: AsyncClient, user_token: dict):
        res = await client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "WrongPassword!",
        })
        assert res.status_code == 401
        assert "invalid" in res.json()["detail"].lower()

    async def test_login_nonexistent_user(self, client: AsyncClient):
        res = await client.post("/api/auth/login", json={
            "email": "nobody@example.com",
            "password": "SomePass1!",
        })
        assert res.status_code == 401

    async def test_login_empty_body(self, client: AsyncClient):
        res = await client.post("/api/auth/login", json={})
        assert res.status_code == 422

    async def test_login_empty_email(self, client: AsyncClient):
        res = await client.post("/api/auth/login", json={"email": "", "password": "pass"})
        assert res.status_code == 401


class TestMe:
    async def test_get_me_authenticated(self, client: AsyncClient, user_token: dict):
        res = await client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {user_token['token']}"
        })
        assert res.status_code == 200
        assert res.json()["email"] == "test@example.com"

    async def test_get_me_no_token(self, client: AsyncClient):
        res = await client.get("/api/auth/me")
        assert res.status_code == 401

    async def test_get_me_invalid_token(self, client: AsyncClient):
        res = await client.get("/api/auth/me", headers={
            "Authorization": "Bearer invalidtoken123"
        })
        assert res.status_code == 401

    async def test_get_me_expired_token(self, client: AsyncClient):
        res = await client.get("/api/auth/me", headers={
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZXhwIjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        })
        assert res.status_code == 401

    async def test_get_me_malformed_token(self, client: AsyncClient):
        res = await client.get("/api/auth/me", headers={
            "Authorization": "Bearer not-even-a-token"
        })
        assert res.status_code == 401
