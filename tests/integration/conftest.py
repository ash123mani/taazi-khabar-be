from __future__ import annotations

import asyncio
from uuid import UUID
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import (
    create_tables,
    drop_tables,
    auth_header,
    _get_transport,
    TestSessionLocal,
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await create_tables()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = _get_transport()
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def user_token(client: AsyncClient) -> dict:
    res = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "TestPass123!",
        "name": "Test User",
    })
    data = res.json()
    return {
        "token": data["access_token"],
        "user_id": data["user"]["id"],
        "email": "test@example.com",
    }


@pytest_asyncio.fixture
async def second_user_token(client: AsyncClient) -> dict:
    res = await client.post("/api/auth/register", json={
        "email": "user2@example.com",
        "password": "TestPass456!",
        "name": "Second User",
    })
    data = res.json()
    return {"token": data["access_token"], "user_id": data["user"]["id"]}


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient) -> dict:
    res = await client.post("/api/auth/register", json={
        "email": "admin@example.com",
        "password": "AdminPass123!",
        "name": "Admin User",
    })
    data = res.json()
    user_id_str = data["user"]["id"]
    user_id_uuid = UUID(user_id_str)
    async with TestSessionLocal() as session:
        from sqlalchemy import select, update
        from app.models.user import User
        await session.execute(
            update(User).where(User.id == user_id_uuid).values(is_admin=True)
        )
        await session.commit()
    res2 = await client.post("/api/auth/login", json={
        "email": "admin@example.com",
        "password": "AdminPass123!",
    })
    admin_data = res2.json()
    return {
        "token": admin_data["access_token"],
        "user_id": user_id_str,
        "email": "admin@example.com",
    }
