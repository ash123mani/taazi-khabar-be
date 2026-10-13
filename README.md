# taazi-khabar-backend

AI-powered UPSC current affairs platform — backend.

Built with Python 3.10, FastAPI, SQLAlchemy (async), PostgreSQL 16 (Supabase), Redis.

## Architecture Overview

```
┌──────────────────────┐     ┌────────────────────────┐
│  Backend (port 8000) │ ──→ │  NVIDIA NIM API        │
│                      │     │  (cloud inference)     │
│  - FastAPI           │     │                        │
│  - Auth (JWT)        │     │  All 3 AI personas     │
│  - Scrapers          │     │  (summarizer, filter,  │
│  - Orchestrator      │     │   quiz setter)         │
└──────────────────────┘     └────────────────────────┘
```

## Prerequisites

- Python 3.10+
- PostgreSQL 16+ (Supabase pooler:5432)
- Redis 7+ (optional, for caching)

## Local Setup

```bash
# 1. Environment
cp .env.example .env
# Edit .env with your credentials (DB, NVIDIA keys, HF token)

# 2. Backend virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 3. Migrations
alembic upgrade head

# 4. Seed admin user (optional)
python -m app.scripts.seed_exam_questions

# 5. Run backend
uvicorn app.main:app --reload --port 8000
```

## Available Commands

| Command | Description |
|---------|-------------|
| `alembic upgrade head` | Apply all pending migrations |
| `alembic revision --autogenerate -m "desc"` | Create a new migration |
| `pytest` | Run tests |
| `ruff check .` | Lint |
| `mypy .` | Type check |

## Configuration

All settings in `app/config.py`, loaded from `.env`. Key variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Supabase PostgreSQL pooler URL |
| `NVIDIA_API_KEY` | Global NVIDIA NIM key (fallback) |
| `NVIDIA_NIM_BASE_URL` | Global AI endpoint (default: localhost:8001) |
| `NVIDIA_NIM_BASE_URL_SUMMARIZER` | Per-persona override for summarizer |
| `NVIDIA_NIM_BASE_URL_QUESTION_SETTER` | Per-persona override for quiz setter |
| `NEXTAUTH_SECRET` | JWT signing secret |

To switch a persona back to NVIDIA cloud, set its `base_url` to `https://integrate.api.nvidia.com/v1`.

## API Docs

Once running: `http://localhost:8000/docs`

## Project Structure

```
app/
├── ai/
│   ├── orchestrator.py            Routes requests to right provider
│   ├── providers/nim.py           NVIDIA NIM API client
│   ├── personas/                  Prompt builders per persona
│   ├── config/models.yaml         Model registry
│   └── training/                  Interaction logging & dataset builder
├── api/                           FastAPI routes
├── models/                        SQLAlchemy models
├── services/                      Business logic
├── scripts/                       Cron, seed, etc.
└── config.py                      Settings (pydantic)
```
