from __future__ import annotations

from typing import AsyncGenerator

from httpx import ASGITransport, AsyncClient
from sqlalchemy import StaticPool, TypeDecorator
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.deps import get_db
from app.main import app
from app.models.base import Base

TEST_DB_URL = "sqlite+aiosqlite://"

engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# --- SQLite compilers for PostgreSQL-specific types ---
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, ARRAY as PG_ARRAY, UUID as PG_UUID
from sqlalchemy import ARRAY, Text, String
from pgvector.sqlalchemy import Vector


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return compiler.process(JSON(), **kw)


@compiles(Vector, "sqlite")
def _compile_vector_sqlite(element, compiler, **kw):
    return "BLOB"


@compiles(PG_ARRAY, "sqlite")
def _compile_pg_array_sqlite(element, compiler, **kw):
    return compiler.process(Text(), **kw)


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(element, compiler, **kw):
    return compiler.process(Text(), **kw)


@compiles(PG_UUID, "sqlite")
def _compile_pg_uuid_sqlite(element, compiler, **kw):
    return compiler.process(String(36), **kw)
# --- end SQLite compilers ---


async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = _get_test_db


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _get_transport():
    return ASGITransport(app=app)


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def get_session() -> AsyncSession:
    async with TestSessionLocal() as session:
        return session
