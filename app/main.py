from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.router import api_router
from app.ai.model_registry import registry
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        connect_args={"statement_cache_size": 0},
    )
    async_session_factory = async_sessionmaker(
        engine, expire_on_commit=False
    )
    app.state.engine = engine
    app.state.async_session_factory = async_session_factory

    async with async_session_factory() as session:
        seeded = await registry.db_seed_from_yaml(db=session)
        await session.commit()
        if seeded:
            print(f"Seeded {seeded} model registry entries from YAML")

    yield
    await engine.dispose()


app = FastAPI(title="Taazi Khabar API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
