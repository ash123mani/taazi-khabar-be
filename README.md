# taazi-khabar-backend

AI-powered UPSC current affairs platform — backend.

Built with Python 3.10, FastAPI, SQLAlchemy (async), PostgreSQL 16, Redis.

## Prerequisites

- Python 3.10+
- PostgreSQL 16+ (with `pgcrypto` extension)
- Redis 7+ (optional, used for caching)

## Local Setup

```bash
# 1. Environment
cp .env.example .env

# 2. Virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 3. Database — create user & database
python -c "
import asyncio, asyncpg
async def setup():
    conn = await asyncpg.connect(user='mani', database='postgres', host='localhost')
    await conn.execute(\"CREATE ROLE taazi WITH LOGIN PASSWORD 'taazi'\")
    await conn.execute('CREATE DATABASE taazi OWNER taazi')
    await conn.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')
    await conn.close()
asyncio.run(setup())
"

# 4. Migrations
alembic upgrade head

# 5. Seed sample UPSC exam questions (optional)
python -m app.scripts.seed_exam_questions

# 6. Run
uvicorn app.main:app --reload --port 8000
```

## Available Commands

| Command | Description |
|---------|-------------|
| `alembic upgrade head` | Apply all pending migrations |
| `alembic revision --autogenerate -m "desc"` | Create a new migration |
| `python -m app.scripts.seed_exam_questions` | Seed sample UPSC questions |
| `pytest` | Run tests |
| `ruff check .` | Lint |
| `mypy .` | Type check |

## Configuration

All settings are in `app/config.py`, loaded from `.env`. See `.env.example` for all available variables.

## API Docs

Once running: `http://localhost:8000/docs`
