# AI Training & Persona Architecture

## 1. Overview

The system uses three AI **personas** to power the UPSC current affairs platform:

| Persona | Role | Production Model | Fine-tuning Target |
|---------|------|-----------------|--------------------|
| **Summarizer** | Transforms news articles → structured GK summaries (Prelims/Mains/Interview) | `mistralai/ministral-14b-instruct-2512` | Small model (Phi-3 / Mistral 7B) via QLoRA |
| **Article Filter** | Binary YES/NO classifier for UPSC relevance | `mistralai/ministral-14b-instruct-2512` | Small model via QLoRA |
| **Question Setter** | Generates UPSC-style MCQs from article summaries | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | Small model via QLoRA |

All three currently run on **NVIDIA NIM** cloud API (`integrate.api.nvidia.com/v1`). The training pipeline builds datasets to fine-tune smaller, cheaper models that can replace cloud calls.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PRODUCTION (current)                           │
│                                                                         │
│  RSS Feeds ──► Scraper ──► Article DB ──► AIOrchestrator ──► NIM API   │
│  (The Hindu,          │                    │              (cloud)       │
│   Indian Express)     │                    │                            │
│                       │                    └── summarizer.build_prompt()│
│                       │                    └── article_filter.build_... │
│                       │                    └── question_setter.build_.. │
│                       │                    └── collector.log_interact() │
│                       ▼                                                │
│               Category DB ──── admin portal                            │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                │ (AIInteraction logs accumulate in DB)
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     TRAINING PIPELINE (offline)                         │
│                                                                         │
│  ┌──────────────────────┐    ┌──────────────────────────────────────┐   │
│  │ scrape_upsc_papers   │    │  build_persona_datasets.py            │   │
│  │ (Rau's IAS Compass)  │    │                                      │   │
│  │         │            │    │  1. Fetch articles from DB            │   │
│  │         ▼            │    │  2. For each persona:                 │   │
│  │  data/raw/           │    │     a. Export existing pairs from DB  │   │
│  │   ├── mains/*.pdf   │    │     b. Regenerate ~20 via Teacher LLM │   │
│  │   └── prelims/*.pdf │    │     c. Add synthetic negatives (filter)│   │
│  │      (334 MB total) │    │     d. Batch generate MCQs (quiz)      │   │
│  └──────────────────────┘    │                                      │   │
│                               │  Teacher LLM: qwen3.5-122b (NIM)     │   │
│                               └──────────────┬───────────────────────┘   │
│                                              │                           │
│                                              ▼                           │
│                               ┌──────────────────────────────┐          │
│                               │  data/processed/*.jsonl      │          │
│                               │  (Alpaca format)             │          │
│                               │  ├── gk_summarizer.jsonl     │          │
│                               │  │    (298 records, 1.7 MB)  │          │
│                               │  ├── article_filter.jsonl    │          │
│                               │  │    (311 records, 236 KB)  │          │
│                               │  └── quiz_setter.jsonl       │          │
│                               │       (25 records, 42 KB)    │          │
│                               └──────────────┬───────────────┘          │
│                                              │                           │
│                                              ▼                           │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  notebooks/qlora_finetune.ipynb (Colab)                      │      │
│  │                                                              │      │
│  │  1. Load JSONL via datasets / pandas                         │      │
│  │  2. Base model: microsoft/Phi-3-mini-4k-instruct             │      │
│  │     (or Mistral-7B-Instruct-v0.3)                            │      │
│  │  3. QLoRA: r=16, alpha=32, dropout=0.05                     │      │
│  │     All linear projection modules, 4-bit quantization       │      │
│  │  4. Batch=4, grad_accum=4, lr=2e-4, 3 epochs                │      │
│  │  5. Output: LoRA adapter weights → Google Drive             │      │
│  └──────────────────────────┬───────────────────────────────────┘      │
│                             │                                          │
│                             ▼                                          │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  DEPLOYMENT                                                │      │
│  │                                                              │      │
│  │  NVIDIA NIM LoRA serving:                                    │      │
│  │  Provider: NIMProvider.complete_with_lora()                  │      │
│  │  Header: NVCF_LORA_ADAPTER = <adapter_name>                  │      │
│  │  Route: POST /chat/completions                               │      │
│  └──────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                     DATA COLLECTION (continuous)                        │
│                                                                         │
│  collector.py ──► AIInteraction table (PostgreSQL)                      │
│                                                                         │
│  Every production inference call (summarize, filter, quiz) gets logged  │
│  with: persona, model_name, prompt_text, response_text, tokens_used,   │
│  latency_ms, article_id, user_id.                                       │
│                                                                         │
│  This table is the SOURCE OF TRUTH for future dataset expansions.       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Personas in Detail

### 3.1 Summarizer

| Property | Value |
|----------|-------|
| Module | `app/ai/personas/summarizer.py` |
| Prompt Template | `app/ai/config/prompts/summarizer.yaml` |
| Output Format | Structured markdown: GK Summary, Prelims Focus, Mains Dimensions, Interview Angle, Syllabus Tag, Category, Key Terms |
| Dataset Strategy | Existing DB article→summary pairs exported directly. 20 most recent regenerated via teacher LLM. |
| Dataset Size | 298 records |

### 3.2 Article Filter

| Property | Value |
|----------|-------|
| Module | `app/ai/personas/article_filter.py` |
| Prompt Template | `app/ai/config/prompts/article_filter.yaml` |
| Output | Boolean YES/NO |
| Dataset Strategy | 301 positive examples from DB (articles that passed filter), 10 synthetic negatives generated by teacher LLM (sports, entertainment, celebrity headlines) |
| Dataset Size | 311 records |

### 3.3 Question Setter

| Property | Value |
|----------|-------|
| Module | `app/ai/personas/question_setter.py` |
| Prompt Template | `app/ai/config/prompts/question_setter.yaml` |
| Output Format | UPSC-style MCQs: question, 4 options, answer, explanation, difficulty, syllabus_tag |
| Dataset Strategy | Articles batched in groups of 5 → teacher LLM generates 3 MCQs per article. Some batches failed with HTTP 500 (token limit). |
| Dataset Size | 25 records (goal: 90+) |

---

## 4. Model Configuration

File: `app/ai/config/models.yaml`

```yaml
models:
  summarizer:
    active: "mistralai/ministral-14b-instruct-2512"
    candidates:
      - name: "mistralai/ministral-14b-instruct-2512"
        provider: "nim"
        max_tokens: 2048        # Increased from 1024 (was truncating Category/Syllabus Tag)
        temperature: 0.15
        top_p: 1.0
        frequency_penalty: 0.0
        presence_penalty: 0.0

  question_setter:
    active: "nvidia/llama-3.3-nemotron-super-49b-v1.5"
    candidates:
      - name: "nvidia/llama-3.3-nemotron-super-49b-v1.5"
        provider: "nim"
        max_tokens: 2048
        temperature: 0.6
        top_p: 0.95
        frequency_penalty: 0.0
        presence_penalty: 0.0

  article_filter:
    active: "mistralai/ministral-14b-instruct-2512"
    candidates:
      - name: "mistralai/ministral-14b-instruct-2512"
        provider: "nim"
        max_tokens: 64          # Only needs YES/NO
        temperature: 0.05
        top_p: 1.0
        frequency_penalty: 0.0
        presence_penalty: 0.0
```

Runtime model management via `app/ai/model_registry.py` — supports switching active models at runtime, persisted back to YAML or DB.

---

## 5. Rate Limiting & API Key Management

All NIM calls route through `app/ai/providers/nim.py`:

```
NIMProvider (class-level)
  ├── _semaphore = Semaphore(5)           # Max 5 concurrent requests
  ├── _throttle()                           # 1.5s minimum interval (~40 RPM)
  ├── _request_with_retry()                 # 3 attempts, exponential backoff on 429
  ├── complete()                            # Standard chat completion
  └── complete_with_lora()                  # LoRA adapter inference (NVCF_LORA_ADAPTER)
```

API keys stored per-persona in `.env`:
- `NVIDIA_API_KEY_SUMMARIZER`
- `NVIDIA_API_KEY_QUESTION_SETTER`
- `NVIDIA_API_KEY` (fallback, also used for article_filter)

Retrieved via `settings.get_persona_credentials("summarizer")`.

---

## 6. Data Files

### 6.1 Raw (gitignored, not used by pipeline)

| Path | Contents | Size |
|------|----------|------|
| `data/raw/mains/` | 65 UPSC Mains PDFs (2013–2025) | ~99 MB |
| `data/raw/prelims/` | 26 UPSC Prelims PDFs (2013–2025) | ~235 MB |

These are scanned images (no extractable text) — scraped from Rau's IAS Compass as reference material. Not used by any production or training code.

### 6.2 Processed (versioned in git)

| File | Records | Size | Format |
|------|---------|------|--------|
| `data/processed/gk_summarizer.jsonl` | 298 | 1.7 MB | `{"instruction": "...", "input": "article body", "output": "summary"}` |
| `data/processed/article_filter.jsonl` | 311 | 236 KB | `{"instruction": "...", "input": "headline + body", "output": "YES/NO"}` |
| `data/processed/quiz_setter.jsonl` | 25 | 42 KB | `{"instruction": "...", "input": "article summaries", "output": "MCQs"}` |

---

## 7. Progress & Remaining Work

### Done ✓
- PDF scraping script (`scrape_upsc_papers.py`) — 65 Mains + 26 Prelims PDFs downloaded
- Dataset generation script (`build_persona_datasets.py`) — all 3 personas
- Summarizer dataset: 298 records (20 regenerated via teacher LLM, rest from DB)
- Article filter dataset: 311 records (301 positive + 10 synthetic negatives)
- Quiz setter dataset: 25 records (from 30 articles, some batches failed)
- QLoRA notebook (`notebooks/qlora_finetune.ipynb`) — ready for Colab
- `collector.py` logs live inference to DB (continuous data accumulation)
- `NIMProvider.complete_with_lora()` for serving fine-tuned adapters

### Remaining
- **Generate more quiz setter data**: Fix batch size / prompt length to avoid HTTP 500 errors. Target: 90+ records
- **Run QLoRA fine-tuning**: Execute `qlora_finetune.ipynb` on Colab with generated JSONL files — train separate LoRA adapters for each persona
- **Deploy adapters**: Upload LoRA weights to NVIDIA NIM and switch `AIOrchestrator` from `complete()` to `complete_with_lora()` for the fine-tuned personas
- **Validate quality**: Compare fine-tuned model outputs against teacher model outputs for a held-out test set
- **Expand datasets**: Periodically export new batches from the growing `AIInteraction` table in production
