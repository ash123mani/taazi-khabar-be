# AI Training & Personas — Explained Simply

---

## The Big Picture: What Problem Are We Solving?

Our app (Taazi Khabar) uses AI to do three jobs:

1. **Summarize** news articles into UPSC study notes
2. **Filter** out articles that aren't relevant for UPSC
3. **Generate quiz questions** from articles

Originally, every AI call went to **NVIDIA's cloud API** — which costs money, has rate limits (40 RPM), and depends on internet connectivity. Now, we've trained our own small model and run it **locally** on our own hardware, eliminating those costs and dependencies.

---

## Section 1: The Three AI Assistants (Personas)

### Persona 1: The Summarizer

**Job**: Read a news article and write structured UPSC study notes. The output has sections like:
- GK Summary (bullet points: event, key actors, significance)
- Prelims Focus (exam-ready facts)
- Mains Dimensions (multi-dimensional analysis)
- Interview Angle (opinion, solutions)
- Syllabus Tag (which GS paper it belongs to)
- Category (Polity, Economy, Environment, etc.)
- Key Terms (important vocabulary)

**Training data**: 298 examples (article → summary)

**Fine-tuned model**: `microsoft/Phi-3-mini-4k-instruct` (3.8B) + LoRA adapter (rank=16)

---

### Persona 2: The Article Filter

**Job**: Look at a news headline + first few lines and decide YES (relevant for UPSC) or NO (not relevant).

**Training data**: 311 examples (headline → YES/NO)

**Fine-tuned model**: Same base + adapter (single combined model handles all 3 tasks, differentiated by instruction)

---

### Persona 3: The Question Setter

**Job**: Read article summaries and create UPSC-style multiple choice questions (MCQs) with 4 options, correct answer, and explanation.

**Training data**: 95 examples (summary → 3 MCQs)

**Fine-tuned model**: Same base + adapter (fewest training examples — quality is still being evaluated)

---

## Section 2: Current Architecture (How AI Works Now)

### Inference Server

Instead of calling NVIDIA's cloud for every operation, we run a **local inference server** that loads `Phi-3-mini-4k-instruct` with our fused LoRA adapter:

```
┌──────────────────────┐     ┌────────────────────────┐
│  Backend (port 8000) │ ──→ │  AI Server (port 8001) │
│                      │     │                        │
│  Orchestrator picks  │     │  Phi-3-mini (3.8B)     │
│  base_url from .env  │     │  + LoRA adapter fused  │
│                      │     │  Running on MPS/CUDA   │
└──────────────────────┘     └────────────────────────┘
```

**Key insight**: The orchestrator already accepts `base_url` per persona via `.env`. To route through the local server, we just set:

```
NVIDIA_NIM_BASE_URL=http://localhost:8001/v1
```

Zero code changes. The same `NIMProvider.complete()` method sends the same OpenAI-compatible payload — just to a different address.

### Why Local Instead of NVIDIA LoRA Serving?

NVIDIA's hosted API (`integrate.api.nvidia.com/v1`) does NOT support custom LoRA adapters. The `NVCF_LORA_ADAPTER` header is for the paid NVIDIA Cloud Functions service. So we built our own lightweight serving layer.

### Deployment Flexibility

The inference server is a standalone process. Same code runs on:
- **MacBook** (MPS) — development
- **Linux GPU server** (CUDA) — production
- **Modal / RunPod** (serverless GPU) — cloud deployment

Just change the `base_url` in `.env` to point wherever the server is deployed.

---

## Section 3: The Training Pipeline

### Step 1: Collect Training Examples ✓

We wrote `app/ai/training/build_persona_datasets.py` which:

1. Reads existing articles + summaries from the database (created by the teacher model during live operation)
2. Formats them into Alpaca-format JSONL files
3. Combines all 3 tasks into a single dataset for single-adapter training

**Datasets produced**:

| Dataset | Records | Task |
|---------|---------|------|
| `gk_summarizer.jsonl` | 298 | Article → structured summary |
| `article_filter.jsonl` | 311 | Headline → YES/NO |
| `quiz_setter.jsonl` | 95 | Summary → 3 MCQs |
| **combined.jsonl** | **704** | All 3 merged |

The combined dataset uses the `instruction` field to differentiate tasks:
- `"Summarize this article for UPSC..."` → summarizer task
- `"Decide if this article is relevant..."` → filter task
- `"Create MCQs from this summary..."` → quiz task

### Step 2: Fine-tune with QLoRA ✓

We used Kaggle (free T4 GPU) to train `microsoft/Phi-3-mini-4k-instruct` with QLoRA:

| Hyperparameter | Value |
|----------------|-------|
| Base model | `microsoft/Phi-3-mini-4k-instruct` |
| LoRA rank | 16 |
| LoRA alpha | 32 |
| Target modules | `q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj` |
| Batch size | 4 (with 4 grad accumulation = effective 16) |
| Epochs | 2 |
| Max sequence length | 2048 |
| Learning rate | 2e-4 |

**Training results**:
- 80 steps, 2 epochs
- Loss: 1.65 → 1.26
- Token accuracy: 0.66 → 0.71
- Adapter size: 17MB (saved as `adapter_model.safetensors`)

### Step 3: Deploy ✓

1. Adapter downloaded as `taazi-adapter-final.zip` (~14MB)
2. Extracted to `app/ai/serving/taazi-adapter-final/`
3. Inference server loads base model, fuses adapter, exposes OpenAI-compatible API
4. Backend routes all 3 personas through the local server via `.env`

---

## Section 4: Data Flow (End to End)

```
1. RSS Feeds ──► Scraper fetches 60-200 new articles
                       │
2. For each article ──► Local Phi-3: "Relevant for UPSC?" ──► YES/NO
                       │
3. If YES ──► Save to database (headline, URL, body text)
                       │
4. For each saved article ──► Local Phi-3: "Write GK summary..."
                       │
5. Summary parsed ──► Save to DB (gk_summary, category, syllabus_tag, key_terms)
                       │
6. For each saved article ──► Local Phi-3: "Create 3 MCQs..."
                       │
7. MCQs cached ──► Quiz page serves pre-generated questions
```

All 3 AI calls hit the same local server (port 8001), same model, same adapter — differentiated by the `instruction` field in the prompt.

---

## Section 5: Continuous Improvement

Every AI call is logged to the `AIInteraction` database table:
- Which persona was used
- What was sent (the prompt)
- What the AI replied
- Latency and token usage
- Which article it was about

Over time, we accumulate real production data that can be used to:
1. Expand the training dataset with real examples
2. Re-train or fine-tune further
3. Evaluate quality by comparing against the original teacher model outputs

---

## Section 6: Current Status

### What's Done ✓

| Step | Details |
|------|---------|
| Dataset building | 704 combined examples across 3 personas |
| QLoRA training | Completed on Kaggle T4 GPU, 2 epochs |
| Adapter saved | `taazi-adapter-final.zip` (17MB) |
| Inference server built | FastAPI + PyTorch + PEFT, MPS/CUDA support |
| Model downloaded | `Phi-3-mini-4k-instruct` (~7.1GB cached) |
| Adapter deployed | Fused into base model, server running on port 8001 |
| Orchestrator wired | All 3 personas point to local server via `.env` |

### What's Left ✗

| Step | Priority | Details |
|------|----------|---------|
| **Quality evaluation** | High | Compare local Phi-3 vs teacher model outputs for all 3 tasks |
| **Re-train with more data** | Medium | Wait for more production `AIInteraction` logs to accumulate |
| **Serverless deployment** | Low | Package inference server for Modal / cloud GPU deployment |
| **Quiz setter refinement** | Medium | Only 95 training examples — quality gap vs 49B teacher model |

---

## Section 7: Files Reference

```
app/ai/
├── serving/
│   ├── server.py                  ★ Local inference server (FastAPI)
│   ├── taazi-adapter-final/       ★ Trained LoRA adapter weights
│   ├── requirements.txt           ML dependencies
│   └── .venv/                     Isolated Python venv
├── orchestrator.py                Routes requests to right provider
├── model_registry.py              Active model management
├── providers/nim.py               NVIDIA NIM API client (with rate limiting)
├── personas/                      Prompt builders & response parsers
│   ├── summarizer.py
│   ├── article_filter.py
│   └── question_setter.py
├── config/
│   ├── models.yaml                Model registry (candidates, active)
│   └── prompts/                   System prompts per persona
└── training/
    ├── build_persona_datasets.py  Creates JSONL datasets from DB
    ├── collector.py               Logs AI calls to DB
    └── data/processed/
        ├── combined.jsonl         704 records (all 3 tasks merged)
        ├── gk_summarizer.jsonl    298 records
        ├── article_filter.jsonl   311 records
        └── quiz_setter.jsonl      95 records

notebooks/
└── taazi_training_kaggle.ipynb    Kaggle training notebook

docs/
├── architecture.md                This file
├── training-glossary.md           ML terms explained
└── training-plan.md               Original training plan
```
