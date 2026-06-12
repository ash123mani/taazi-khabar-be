# taazi-khabar-backend

AI-powered UPSC current affairs platform — backend.

Built with Python 3.10, FastAPI, SQLAlchemy (async), PostgreSQL 16 (Supabase), Redis.

## Architecture Overview

```
┌──────────────────────┐     ┌────────────────────────┐
│  Backend (port 8000) │ ──→ │  AI Inference Server   │
│                      │     │   (port 8001)          │
│  - FastAPI           │     │                        │
│  - Auth (JWT)        │     │  Phi-3-mini + LoRA     │
│  - Scrapers          │     │  adapter (fused)       │
│  - Orchestrator      │     │                        │
└──────────────────────┘     └────────────────────────┘
         │                            │
         │  Fallback                  │ Runs locally
         ▼                            (MPS/CUDA/CPU)
  ┌──────────────────┐
  │  NVIDIA NIM API  │
  │  (cloud, for      │
  │   non-fine-tuned  │
  │   personas)       │
  └──────────────────┘
```

All 3 AI personas (summarizer, filter, quiz setter) route through the local inference server by default. Each can be individually switched back to NVIDIA cloud via `.env`.

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

## AI Inference Server (for fine-tuned LoRA model)

```bash
# 1. Create dedicated venv
python3 -m venv app/ai/serving/.venv
app/ai/serving/.venv/bin/pip install torch transformers peft accelerate sentencepiece fastapi uvicorn

# 2. Download base model (one-time)
# Set HF_TOKEN in .env for faster downloads
app/ai/serving/.venv/bin/python -c "
from huggingface_hub import snapshot_download
snapshot_download('microsoft/Phi-3-mini-4k-instruct')
"

# 3. Extract LoRA adapter to app/ai/serving/taazi-adapter-final/
# (from taazi-adapter-final.zip)

# 4. Start inference server
app/ai/serving/.venv/bin/python -m app.ai.serving.server
# Runs on port 8001 — backend auto-discovers via .env
```

## Available Commands

| Command | Description |
|---------|-------------|
| `alembic upgrade head` | Apply all pending migrations |
| `alembic revision --autogenerate -m "desc"` | Create a new migration |
| `pytest` | Run tests |
| `ruff check .` | Lint |
| `mypy .` | Type check |
| `app/ai/serving/.venv/bin/python -m app.ai.serving.server` | Start inference server |

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
| `HF_TOKEN` | Hugging Face token (model downloads) |

To switch a persona back to NVIDIA cloud, set its `base_url` to `https://integrate.api.nvidia.com/v1`.

## API Docs

Once running: `http://localhost:8000/docs`

## Project Structure

```
app/
├── ai/
│   ├── serving/
│   │   ├── server.py              ★ Local LoRA inference server
│   │   ├── taazi-adapter-final/   ★ Trained adapter weights
│   │   └── requirements.txt       ML deps for inference
│   ├── orchestrator.py            Routes requests to right provider
│   ├── providers/nim.py           NVIDIA NIM API client
│   ├── personas/                  Prompt builders per persona
│   ├── config/models.yaml         Model registry
│   └── training/                  Dataset builders & training
├── api/                           FastAPI routes
├── models/                        SQLAlchemy models
├── services/                      Business logic
├── scripts/                       Cron, seed, etc.
└── config.py                      Settings (pydantic)
```
