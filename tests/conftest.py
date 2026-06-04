from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from httpx import ASGITransport, AsyncClient
from sqlalchemy import StaticPool, TypeDecorator, types
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

# --- SQLite-compatible replacements for PostgreSQL types ---
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, ARRAY as PG_ARRAY, UUID as PG_UUID
from sqlalchemy import ARRAY, Text, String
from pgvector.sqlalchemy import Vector

# Store JSONB as JSON text on SQLite
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return compiler.process(JSON(), **kw)

# Store Vector as blob on SQLite
@compiles(Vector, "sqlite")
def _compile_vector_sqlite(element, compiler, **kw):
    return "BLOB"

# Store PG_ARRAY as JSON text on SQLite
@compiles(PG_ARRAY, "sqlite")
def _compile_pg_array_sqlite(element, compiler, **kw):
    return compiler.process(JSON(), **kw)

# Store ARRAY as JSON text on SQLite  
@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(element, compiler, **kw):
    return compiler.process(JSON(), **kw)

# Store PG_UUID as string on SQLite
@compiles(PG_UUID, "sqlite")
def _compile_pg_uuid_sqlite(element, compiler, **kw):
    return compiler.process(String(36), **kw)
# --- end SQLite compilers ---

# Patch ARRAY bind/result processors for SQLite to use JSON serialization
import sqlalchemy.types as satypes

_orig_array_bind = ARRAY.bind_processor
def _patched_array_bind(self, dialect):
    if dialect.name == "sqlite":
        def process(value):
            if value is None:
                return None
            return json.dumps(value)
        return process
    return _orig_array_bind(self, dialect)
ARRAY.bind_processor = _patched_array_bind

_orig_array_result = ARRAY.result_processor
def _patched_array_result(self, dialect, coltype):
    if dialect.name == "sqlite":
        def process(value):
            if value is None:
                return None
            return json.loads(value)
        return process
    return _orig_array_result(self, dialect, coltype)
ARRAY.result_processor = _patched_array_result

# Same for PG_ARRAY
_orig_pg_array_bind = PG_ARRAY.bind_processor
def _patched_pg_array_bind(self, dialect):
    if dialect.name == "sqlite":
        def process(value):
            if value is None:
                return None
            return json.dumps(value)
        return process
    return _orig_pg_array_bind(self, dialect)
PG_ARRAY.bind_processor = _patched_pg_array_bind

_orig_pg_array_result = PG_ARRAY.result_processor
def _patched_pg_array_result(self, dialect, coltype):
    if dialect.name == "sqlite":
        def process(value):
            if value is None:
                return None
            return json.loads(value)
        return process
    return _orig_pg_array_result(self, dialect, coltype)
PG_ARRAY.result_processor = _patched_pg_array_result

# Patch JSONB bind/result processors for SQLite
_orig_jsonb_bind = JSONB.bind_processor
def _patched_jsonb_bind(self, dialect):
    if dialect.name == "sqlite":
        def process(value):
            if value is None:
                return None
            return json.dumps(value)
        return process
    return _orig_jsonb_bind(self, dialect)
JSONB.bind_processor = _patched_jsonb_bind

_orig_jsonb_result = JSONB.result_processor
def _patched_jsonb_result(self, dialect, coltype):
    if dialect.name == "sqlite":
        def process(value):
            if value is None:
                return None
            return json.loads(value)
        return process
    return _orig_jsonb_result(self, dialect, coltype)
JSONB.result_processor = _patched_jsonb_result


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
