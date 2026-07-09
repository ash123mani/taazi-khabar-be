# Taazi Khabar — Architecture

## Overview

Two custom fine-tuned LLM personas serving UPSC aspirants:
1. **GK Summarizer** — reads newspaper articles, extracts UPSC-relevant essence
2. **Question Setter** — takes selected articles, generates Prelims-style MCQs

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js)                           │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  ┌───────────┐  │
│  │  News Feed   │  │  Quiz Center │  │ History  │  │  Admin    │  │
│  │              │  │              │  │          │  │  Panel    │  │
│  │ • Article    │  │ • Select     │  │ • Past    │  │           │  │
│  │   cards with│  │   articles   │  │   quizzes │  │ • Training│  │
│  │   GK summary │  │ • Generate   │  │ • Linked │  │   Data    │  │
│  │ • Syllabus   │  │   Quiz      │  │   articles│  │   Browser │  │
│  │   tag        │  │ • Take Quiz  │  │ • Scores  │  │ • Dataset │  │
│  │ • Link to    │  │ • Instant    │  │   history │  │   Builder │  │
│  │   original   │  │   result     │  │          │  │ • Model   │  │
│  │              │  │              │  │          │  │   Manager │  │
│  └──────┬───────┘  └──────┬───────┘  └────┬─────┘  └─────┬─────┘  │
│         └─────────────────┴───────────────┴───────────────┘        │
│                           │ NextAuth.js                             │
└───────────────────────────┼─────────────────────────────────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────────┐
│                    API LAYER (FastAPI)                               │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     AI ORCHESTRATOR ★                         │  │
│  │                                                               │  │
│  │  ┌──────────────────────────────────────────────────────┐    │  │
│  │  │              Model Abstraction Layer                  │    │  │
│  │  │                                                      │    │  │
│  │  │  ┌──────────────┐    ┌──────────────────────────┐   │    │  │
│  │  │  │  NVIDIA NIM  │    │   vLLM (self-hosted)     │   │    │  │
│  │  │  │  (Phase 1:   │    │                          │   │    │  │
│  │  │  │   Free Tier) │    │  • Base model            │   │    │  │
│  │  │  │              │    │  • + LoRA adapters       │   │    │  │
│  │  │  │  Base Llama  │    │  • Phase 2+ after        │   │    │  │
│  │  │  │  3.1 8B      │    │    fine-tuning           │   │    │  │
│  │  │  └──────────────┘    └──────────────────────────┘   │    │  │
│  │  └──────────────────────────────────────────────────────┘    │  │
│  │                                                               │  │
│  │  ┌──────────────────────────────────────────────────────┐    │  │
│  │  │          Two Fine-Tuned LLM Personas ★               │    │  │
│  │  │                                                      │    │  │
│  │  │  ┌────────────────────────┐ ┌────────────────────┐  │    │  │
│  │  │  │  📰 GK SUMMARIZER     │ │  🧠 QUESTION      │  │    │  │
│  │  │  │                       │ │     SETTER         │  │    │  │
│  │  │  │  Input: article text  │ │  Input: 1-5        │  │    │  │
│  │  │  │  Output:              │ │    articles         │  │    │  │
│  │  │  │  • 3-4 line GK jist   │ │  Output:           │  │    │  │
│  │  │  │  • Syllabus topic tag │ │  • 5-10 MCQs       │  │    │  │
│  │  │  │  • Key terms/high-    │ │  • Answer key      │  │    │  │
│  │  │  │    lights for Prelims │ │  • Explanations    │  │    │  │
│  │  │  │  • Article link       │ │  • Difficulty tag  │  │    │  │
│  │  │  │                       │ │                    │  │    │  │
│  │  │  │  Trained on:          │ │  Trained on:       │  │    │  │
│  │  │  │  • Past UPSC papers   │ │  • UPSC Prelims    │  │    │  │
│  │  │  │  • Expert summaries   │ │    (1995-2025)     │  │    │  │
│  │  │  │  • Syllabus taxonomy  │ │  • Topic-wise      │  │    │  │
│  │  │  │                       │ │    question banks  │  │    │  │
│  │  │  │  LoRA: summary-v1     │ │  • Current affairs │  │    │  │
│  │  │  │                       │ │     Q&A            │  │    │  │
│  │  │  │                       │ │                    │  │    │  │
│  │  │  │                       │ │  LoRA: quizzer-v1  │  │    │  │
│  │  │  └────────────────────────┘ └────────────────────┘  │    │  │
│  │  └──────────────────────────────────────────────────────┘    │  │
│  │                                                               │  │
│  │  ┌──────────────────────────────────────────────────────┐    │  │
│  │  │           TRAINING DATA COLLECTOR ★                  │    │  │
│  │  │                                                      │    │  │
│  │  │  ┌───────────┐  ┌───────────┐  ┌─────────────────┐ │    │  │
│  │  │  │ Past UPSC │  │ AI Inter- │  │ User Feedback   │ │    │  │
│  │  │  │ Papers    │  │ actions   │  │ (quiz perf,     │ │    │  │
│  │  │  │ (public)  │  │ (prompt + │  │  thumbs up/down,│ │    │  │
│  │  │  │           │  │  response)│  │  admin edits)   │ │    │  │
│  │  │  └───────────┘  └───────────┘  └─────────────────┘ │    │  │
│  │  └──────────────────────────────────────────────────────┘    │  │
│  │                                                               │  │
│  │  ┌──────────────────────────────────────────────────────┐    │  │
│  │  │              FINE-TUNING PIPELINE ★                  │    │  │
│  │  │                                                      │    │  │
│  │  │  Collect → Filter → Format (Alpaca) → LoRA Train    │    │  │
│  │  │  → Evaluate → Push to MinIO → Update Model Registry │    │  │
│  │  └──────────────────────────────────────────────────────┘    │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Service Layer                                                 │  │
│  │  User Srvc │ Article Srvc │ Quiz Srvc │ TrainingData Srvc    │  │
│  │  ModelRegistry Srvc │ Eval Srvc                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Scraping Pipeline (Cron)                                     │  │
│  │  The Hindu RSS → Extract → AI Summarize → Save to DB        │  │
│  │  Indian Express RSS → Extract → AI Summarize → Save to DB   │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────┴──────┐    ┌──────┴─────┐    ┌───────┴──────────┐
│  PostgreSQL  │    │   Redis    │    │   MinIO (S3)     │
│  + pgvector  │    │            │    │                  │
│              │    │ Cache      │    │  • LoRA adapters │
│  Users       │    │ Sessions   │    │  • Training      │
│  Articles    │    │ Task Queue │    │    datasets      │
│  Quizzes     │    │            │    │  • Past UPSC     │
│  Questions   │    │            │    │    papers        │
│  AI Inter-   │    │            │    │  • Article       │
│  actions     │    │            │    │    snapshots     │
│  Embeddings  │    │            │    │                  │
└──────────────┘    └────────────┘    └──────────────────┘
```

---

## Database Schema

```sql
-- 👤 Users
users (
  id UUID PK,
  email VARCHAR UNIQUE,
  password_hash VARCHAR,
  name VARCHAR,
  created_at TIMESTAMP
)

-- 📰 Articles (from The Hindu & Indian Express)
articles (
  id UUID PK,
  source VARCHAR,              -- 'the_hindu' | 'indian_express'
  headline TEXT,
  body_text TEXT,
  url TEXT,
  published_at TIMESTAMP,
  scraped_at TIMESTAMP,
  -- AI-generated fields:
  gk_summary TEXT,             -- 3-4 line UPSC-relevant summary
  key_terms TEXT[],            -- important terms for prelims
  syllabus_tag VARCHAR,        -- e.g. 'Polity → Fundamental Rights'
  syllabus_subject VARCHAR,    -- e.g. 'Polity'
  created_at TIMESTAMP
)

-- 🏷️ Categories (UPSC Syllabus Tree)
categories (
  id UUID PK,
  name VARCHAR,                -- 'Polity', 'History', etc.
  parent_id UUID FK,           -- self-referencing for hierarchy
  level INT,                   -- 1: subject, 2: topic, 3: subtopic
  syllabus_code VARCHAR        -- official UPSC code if available
)

-- 🤖 AI Interactions (Every model call logged for fine-tuning)
ai_interactions (
  id UUID PK,
  user_id UUID FK,
  article_id UUID FK,
  persona ENUM('summarizer', 'question_setter'),
  model_used VARCHAR,
  prompt TEXT,
  response TEXT,
  latency_ms INT,
  tokens_used INT,
  user_feedback INT,           -- -1 (bad), 0 (neutral), 1 (good)
  admin_edited_response TEXT,  -- human correction → training data
  in_training_dataset BOOL DEFAULT false,
  created_at TIMESTAMP
)

-- 📝 Past UPSC Exam Questions (Training data source)
exam_questions (
  id UUID PK,
  year INT,
  subject VARCHAR,
  topic VARCHAR,
  question_text TEXT,
  options JSONB,
  correct_answer VARCHAR,
  explanation TEXT,
  question_type ENUM('statement', 'match', 'assertion_reason', 'sequence'),
  difficulty ENUM('easy', 'medium', 'hard'),
  source_url TEXT
)

-- 🎯 Quizzes (with article-set caching to avoid duplicate LLM calls)
quizzes (
  id UUID PK,
  user_id UUID FK,
  title VARCHAR,
  article_set_hash VARCHAR UNIQUE,  -- MD5(sorted article IDs) for cache dedup
  score INT,
  total_questions INT,
  time_taken_sec INT,
  created_at TIMESTAMP
)

quiz_articles (quiz_id FK, article_id FK)  -- which articles this quiz is based on
quiz_questions (
  id UUID PK,
  quiz_id UUID FK,
  question_text TEXT,
  options JSONB,
  correct_answer VARCHAR,
  explanation TEXT,
  difficulty VARCHAR,
  ai_interaction_id UUID FK    -- link back to the AI call that generated it
)
quiz_answers (user_id FK, quiz_question_id FK, selected_answer VARCHAR,
              is_correct BOOL, time_taken_sec INT)

-- 🧠 Training Datasets
training_datasets (
  id UUID PK,
  name VARCHAR,
  persona ENUM('summarizer', 'question_setter'),
  base_model VARCHAR,
  num_examples INT,
  status ENUM('collecting', 'ready', 'training', 'deployed', 'failed'),
  lora_adapter_path VARCHAR,    -- minio/lora/summarizer-v1/
  metrics JSONB,                -- eval results
  created_at TIMESTAMP
)
```

---

## Model Registry (Single Config File)

```yaml
# config/models.yaml
models:
  summarizer:
    provider: nim              # switches to 'vllm' after fine-tuning
    model: meta-llama/Llama-3.1-8B-Instruct
    lora_adapter: null         # minio/lora/summarizer-v1 after training
    prompt_template: |
      You are a UPSC GK Summarizer. Given a newspaper article, extract:
      1. Key points relevant to UPSC Prelims & Mains (3-4 lines)
      2. The UPSC syllabus topic (e.g., Polity → Parliament)
      3. 3-5 key terms the aspirant should remember

  question_setter:
    provider: nim
    model: meta-llama/Llama-3.1-8B-Instruct
    lora_adapter: null
    prompt_template: |
      You are a UPSC Prelims Question Setter. Given these article summaries,
      create {n} MCQs in UPSC Prelims format (statement-based, match-the-following,
      assertion-reason). Provide answer key with explanations.
```

---

## Fine-Tuning Loop

```
                    ┌──────────────────┐
                    │  Collect Data    │
                    │  (auto + manual) │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Filter & Label  │
                    │  (Admin UI)      │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Build Dataset   │
                    │  (Alpaca format) │
                    └────────┬─────────┘
                             │
               ┌─────────────┼─────────────┐
               │                             │
    ┌──────────▼──────────┐      ┌──────────▼──────────┐
    │  LoRA Fine-Tune     │      │  Evaluate on Test   │
    │  (QLoRA 4-bit)      │      │  Set                │
    └──────────┬──────────┘      └──────────┬──────────┘
               │                             │
               └─────────────┬───────────────┘
                             │
                    ┌────────▼─────────┐
                    │  Push Adapter    │
                    │  to MinIO        │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Update Model    │
                    │  Registry        │
                    │  (swap provider) │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  A/B Test vs     │
                    │  Previous Model  │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Deploy to       │
                    │  Production      │
                    └──────────────────┘
```

---

---

## Quiz Caching Strategy (LLM Call Optimization)

**Problem:** Every time a user selects articles A, B, C and generates a quiz, the current design calls the LLM. If another user selects the same articles, we'd call the LLM again for the same work.

**Solution:** Deduplicate quiz generation via `article_set_hash`

```
User selects articles [A, B, C]
         │
         ▼
Compute MD5 hash of sorted article IDs
         │
         ▼
Query: quiz with article_set_hash = hash already exists?
         │
         ├── YES ──► Return existing quiz from DB (zero LLM cost)
         │
         └── NO ───► Call LLM → Save quiz + questions with hash
                          → Return new quiz
                          → Future requests for same articles skip LLM
```

**Key design decisions:**
- Hash is globally unique (not per-user) — if any user generated a quiz for articles [A,B,C], everyone gets it from cache
- Hash is computed from sorted article IDs so order doesn't matter
- The hash column has a UNIQUE constraint in PostgreSQL
- Cached quizzes still appear in each user's history (via `quiz_articles` join)
- The LLM training data collector still logs the *first* generation (the one that actually called the LLM)

## Tech Stack Summary

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | Next.js 14 + Tailwind + TypeScript | SSR for articles, PWA, admin routes |
| Auth | NextAuth.js | Google OAuth + email, built-in DB sessions |
| Backend | FastAPI (Python) | Async, auto-docs, perfect for AI workloads |
| Database | PostgreSQL + pgvector | Relational data + vector search for RAG |
| Cache/Queue | Redis | Sessions, rate limiting, Celery broker |
| Object Store | MinIO | Self-hosted S3 for LoRA adapters + training data |
| AI Provider | NVIDIA NIM (Phase 1) | Free tier, no GPU needed |
| AI Self-host | vLLM (Phase 2+) | Serve fine-tuned LoRA adapters on GPU |
| Task Queue | Celery | Async scraping + training jobs |
| Container | Docker Compose | One-command local setup |
