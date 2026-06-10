# AI Training & Personas — Explained Simply

---

## The Big Picture: What Problem Are We Solving?

Our app (Taazi Khabar) uses AI to do three jobs:

1. **Summarize** news articles into UPSC study notes
2. **Filter** out articles that aren't relevant for UPSC
3. **Generate quiz questions** from articles

Right now, for every article, our app calls **NVIDIA's cloud AI** over the internet. This works, but:
- It costs money per call
- It's slow (internet round-trip + heavy AI processing)
- If NVIDIA goes down, our AI features break
- We're limited to 40 calls per minute (rate limit)

**The plan**: Train our own smaller, cheaper AI models that can do the same jobs — faster, cheaper, and offline. The large NVIDIA models act as our "teacher" to create training material, and we use that material to train small "student" models.

---

## Section 1: The Three AI Assistants (Personas)

Think of each "persona" as a separate AI assistant hired for a specific job.

### Persona 1: The Summarizer

**Job**: Read a news article and write structured UPSC study notes. The output has sections like:
- GK Summary (bullet points: event, key actors, significance)
- Prelims Focus (exam-ready facts)
- Mains Dimensions (multi-dimensional analysis)
- Interview Angle (opinion, solutions)
- Syllabus Tag (which GS paper it belongs to)
- Category (Polity, Economy, Environment, etc.)
- Key Terms (important vocabulary)

**Why we need this**: UPSC aspirants don't have time to read 100 long articles daily. They need crisp, exam-oriented notes.

**Current model (Teacher)**: `mistralai/ministral-14b-instruct-2512` — a 14-billion parameter model running on NVIDIA's cloud.

**Training goal**: A small model (3-7 billion parameters) that can produce similar quality summaries but runs cheaper and faster.

---

### Persona 2: The Article Filter

**Job**: Look at a news headline + first few lines and decide YES (relevant for UPSC) or NO (not relevant).

**Example YES articles**: Supreme Court judgment on reservation, new government scheme, international treaty, environmental policy.
**Example NO articles**: Cricket match result, film review, celebrity gossip, local crime without national significance.

**Why we need this**: Our RSS feeds dump 200+ articles daily. We can't summarize all of them — we'd go broke on API costs. The filter quickly separates wheat from chaff. Only ~30% pass.

**Current model (Teacher)**: Same as summarizer — `mistralai/ministral-14b-instruct-2512`.

**Training goal**: A tiny model (maybe 1-3 billion parameters) that makes fast YES/NO decisions.

---

### Persona 3: The Question Setter

**Job**: Read article summaries and create UPSC-style multiple choice questions (MCQs) with 4 options, correct answer, and explanation.

**Example**:
> **Question**: The 'PM-KISAN' scheme provides income support of how much per year?
> **Options**: A) ₹2,000 B) ₹6,000 C) ₹12,000 D) ₹18,000
> **Answer**: B
> **Explanation**: PM-KISAN provides ₹6,000/year to eligible farmer families in three installments.

**Why we need this**: Active recall (quizzing) is proven to boost retention. Every article should generate practice questions.

**Current model (Teacher)**: `nvidia/llama-3.3-nemotron-super-49b-v1.5` — a massive 49-billion parameter model. Very smart but very expensive.

**Training goal**: A small model (3-7 billion parameters) that generates decent MCQs.

---

## Section 2: How AI Works Today (Production Flow)

### Step-by-step flow when you click "Scrape Now":

```
1. RSS Feeds ──► Scraper fetches 60-200 new articles
                       │
2. For each article ──► Article Filter asks AI: "Is this UPSC-relevant?"
                       │
3. If YES ──► Save to database (basic info: headline, URL, date, body text)
                       │
4. For each saved article ──► Summarizer asks AI: "Write GK summary..."
                       │
5. Summary returned ──► Save to database (gk_summary, syllabus_tag, category, key_terms)
                       │
6. Database ──► Website shows articles with summaries and categories
                       │
7. User visits quiz page ──► Question Setter asks AI: "Create MCQs..."
                       │
8. MCQs returned ──► Show to user, cache for later
```

Every step that says "asks AI" makes an internet call to NVIDIA's cloud. Each call takes 2-10 seconds and costs money.

### What is an "AI Model" exactly?

An AI model is a mathematical brain trained on massive amounts of text. Think of it like a chef who has read millions of recipes:

- **Parameters** = the number of "connections" in the brain. More = smarter but slower and more expensive.
  - 14B model = 14 billion connections (like a master chef)
  - 49B model = 49 billion connections (like a world-class chef with decades of experience)
  - 3B model = 3 billion connections (like a short-order cook — fast and cheap, but limited)

- **Inference** = when the model actually does its job (reads a prompt and generates a response)

- **Training / Fine-tuning** = teaching the model to get better at a specific task (like sending the chef to a specialized baking course)

- **Prompt** = the instructions you give the AI (the "recipe" it follows)

---

## Section 3: Why We Need to Train Our Own Models

### Problem with the current approach:

| Issue | Detail |
|-------|--------|
| **Cost** | Every article costs ~₹0.50-2.00 in AI API fees. 200 articles/day = ₹100-400/day |
| **Speed** | Each AI call takes 3-10 seconds. 200 articles = 10+ minutes of waiting |
| **Rate limits** | NVIDIA allows ~40 calls per minute. We have to wait between batches |
| **Dependency** | If NVIDIA is down or changes pricing, our app breaks |
| **No customization** | The generic AI doesn't understand UPSC exam patterns deeply |

### Solution: Fine-tuning

Instead of calling the expensive cloud AI for every article, we:

1. **Create a dataset** of ~300 perfect examples (article → summary, article → YES/NO, summary → MCQs)
2. **Teach a small model** to mimic those perfect examples
3. **Deploy the small model** — it runs faster (1-2 seconds) and costs nearly nothing

This is called **knowledge distillation**: the large "teacher" model creates examples, and the small "student" model learns from them.

---

## Section 4: The Training Pipeline — Step by Step

### Overview diagram (plain terms):

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  TODAY (Production)                                                         │
│                                                                              │
│  News feeds ──► Our app ──► Ask NVIDIA cloud AI ──► Get result ──► Show user│
│                                                                              │
│  Every single call costs money and takes time.                               │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│  OUR TRAINING PLAN                                                          │
│                                                                              │
│  Step 1: Collect examples ──► Create practice tests (datasets)              │
│  Step 2: Teach a small AI using those practice tests (fine-tuning)          │
│  Step 3: Replace the expensive cloud AI with our trained small AI            │
│                                                                              │
│  Result: Same quality, much cheaper, much faster.                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Step 1: Collect Training Examples (already done)

We wrote a script called `build_persona_datasets.py`. Here's what it does for each persona:

#### For the Summarizer:
1. Go to the database
2. Find all articles that already have summaries (from previous AI calls)
3. Export 278 of those as-is (they're already good)
4. Take the 20 most recent articles and ask the teacher model to write them again (to ensure quality)
5. Save all 298 examples in a file: `gk_summarizer.jsonl` (each example = article body + its summary)

Think of it like collecting 298 solved math problems with step-by-step solutions.

#### For the Article Filter:
1. Take all articles that were previously marked as UPSC-relevant (these are "YES" examples)
2. Create 10 fake non-UPSC articles using AI (these are "NO" examples — celebrity gossip, cricket scores, etc.)
3. Save all 311 examples in a file: `article_filter.jsonl` (each example = headline + body + YES/NO)

Think of it like showing a student 311 pictures and saying "this is a cat" or "this is not a cat."

#### For the Question Setter:
1. Take article summaries from the database
2. Send them in batches of 5 to the teacher model
3. Ask the teacher to write 3 MCQs per article
4. Save the results: `quiz_setter.jsonl`
5. Some batches failed (the teacher got overwhelmed by long text)
6. We only got 25 examples so far. Need 90+.

### Step 2: What is QLoRA Fine-tuning? (next step)

QLoRA is a technique to train a small model without needing an expensive supercomputer.

**Plain explanation**:

Imagine you have a pre-trained chef (the base model) who already knows how to cook thousands of dishes. You want to make them a specialist in South Indian cuisine.

Instead of re-training the chef from scratch (which would cost millions), you:

1. **Freeze** the chef's existing knowledge (don't change their core skills)
2. **Add a small adapter** — like a tiny cheat-sheet with South Indian recipes that the chef can refer to
3. **Train only the cheat-sheet** (this is very cheap and fast)
4. At serving time, the chef uses their base knowledge + the cheat-sheet

The "cheat-sheet" is called a **LoRA adapter**. It's usually a few megabytes — tiny compared to the full model (which is gigabytes).

**Why QLoRA specifically?**
The "Q" stands for Quantization. Normally, the model's brain uses 16-bit numbers for every connection, which needs lots of computer memory. Quantization shrinks it to 4-bit numbers, using 4x less memory. This means even a laptop can fine-tune a 7-billion parameter model.

### Step 3: Run the Fine-tuning (not yet done)

We have a Google Colab notebook called `qlora_finetune.ipynb`. When we run it:

1. Load one of our JSONL files (e.g., `gk_summarizer.jsonl`)
2. Load a small base model (e.g., `Phi-3-mini` or `Mistral-7B`)
3. Apply QLoRA (shrink the model to 4-bit, add the adapter)
4. Train for a few hours on Google's free GPUs
5. Save the trained adapter weights to Google Drive
6. Repeat for each persona (summarizer, filter, quiz)

### Step 4: Deploy the Trained Models (not yet done)

NVIDIA NIM (our cloud AI provider) has a feature: you can upload your LoRA adapter and they'll serve it alongside their base model. They call this "NVCF LoRA serving."

In code: instead of calling `provider.complete()`, we call `provider.complete_with_lora("summarizer_adapter")`.

The flow becomes:
```
News article ──► Our app ──► NVIDIA NIM (with OUR adapter) ──► Result
```

Because the adapter is small, the inference is faster and cheaper than using the full teacher model.

Eventually, if we want to be fully independent, we can run the base model + adapter on our own server, eliminating NVIDIA entirely.

---

## Section 5: Data Collection — How We Get Better Over Time

Our app already logs every AI call to a database table called `AIInteraction`. This table captures:

- Which persona was used (summarizer, filter, quiz)
- What was sent to the AI (the prompt)
- What the AI replied (the response)
- How long it took
- Which article it was about

Every day the app runs, we accumulate more examples. After a few months, we'll have thousands of real-world examples to train on — much more than the 300 we manually created.

This is called **continuous data collection**: the system gets better as it runs longer.

---

## Section 6: Current Status

### What's Done ✓

| Step | Status | Details |
|------|--------|---------|
| Scrape UPSC PDFs from Rau's IAS | Done | 65 Mains + 26 Prelims PDFs downloaded |
| Build summarizer dataset | Done | 298 examples (article → summary) |
| Build article filter dataset | Done | 311 examples (headline → YES/NO) |
| Build quiz setter dataset | Partial | 25 examples (need 90+) |
| QLoRA notebook | Done | Ready to run on Google Colab |
| Live inference logging | Done | `collector.py` logs every AI call to DB |
| LoRA serving code | Done | `complete_with_lora()` method ready in provider |

### What's Left ✗

| Step | What It Means | Why Not Done |
|------|---------------|-------------|
| **Generate more quiz data** | Create 90+ MCQ examples instead of just 25 | Teacher model was giving errors (500) when given long article texts — need to break into smaller batches |
| **Run fine-tuning on Colab** | Execute the notebook, train 3 LoRA adapters | Requires manual trigger (open Colab, upload JSONL, run cells) — takes a few hours of GPU time |
| **Deploy adapters to NVIDIA** | Upload LoRA weights, switch API calls to use them | Need the trained adapters first |
| **Validate quality** | Test: do the small models produce good results? | Need to compare student vs teacher outputs |
| **Expand datasets** | Add more examples from the live `AIInteraction` logs | Waiting for more production data to accumulate |

---

## Section 7: Glossary (AI Terms in Plain English)

| Term | What it means |
|------|---------------|
| **AI Model** | A mathematical brain trained on text. Like a chef who read millions of recipes. |
| **Parameter** | A "connection" in the AI brain. More parameters = smarter but slower/more expensive. |
| **14B / 7B / 49B** | 14 billion, 7 billion, 49 billion parameters. Rough indicator of capability. |
| **Inference** | When the AI actually does its job (takes input, produces output). |
| **Prompt** | The instructions/input you give the AI. |
| **Training** | Teaching the AI from scratch (expensive, needs tons of data). |
| **Fine-tuning** | Taking an already-trained AI and specializing it (cheaper, needs less data). |
| **QLoRA** | A clever technique to fine-tune AI on a laptop instead of a supercomputer. |
| **LoRA Adapter** | A tiny "cheat-sheet" file (few MB) that modifies the AI's behavior. |
| **Quantization (Q)** | Compressing the AI's brain from 16-bit to 4-bit numbers. Uses 4x less memory. |
| **Knowledge Distillation** | Teacher model creates examples → student model learns from them. |
| **Teacher Model** | Big, smart, expensive AI (our current NVIDIA cloud models). |
| **Student Model** | Small, fast, cheap AI (what we want to train). |
| **Dataset** | A collection of examples used for training (question + expected answer). |
| **JSONL** | A file format where each line is one training example. |
| **Alpaca Format** | A standard way to structure training examples: instruction, input, output. |
| **NIM (NVIDIA Inference Microservice)** | NVIDIA's cloud service for running AI models. |
| **API** | An internet address our app calls to talk to the AI. |
| **Rate Limit** | Maximum number of API calls per minute (ours: 40 RPM). |
| **Colab** | Google's free online service for running AI training on their GPUs. |
| **Adapter Weights** | The trained "cheat-sheet" file produced by QLoRA fine-tuning. |
| **RAG (Retrieval Augmented Generation)** | Giving the AI reference documents to look up (our OLD approach). We switched to fine-tuning instead. |
| **NVCF_LORA_ADAPTER** | A special header that tells NVIDIA which LoRA adapter to use. |

---

## Section 8: Files in the Training Folder

```
app/ai/training/
│
├── build_persona_datasets.py     ★ Main script — creates the 3 datasets from DB + teacher AI
│
├── scrape_upsc_papers.py         Downloads UPSC question PDFs (reference material, not used)
│
├── dataset_builder.py            Older version of dataset builder (legacy)
│
├── collector.py                  Logs every AI call to DB for future dataset expansion
│
├── data/
│   ├── raw/                      ★ PDFs (334 MB) — gitignored, not used by code
│   │   ├── mains/*.pdf           (65 scanned PDFs of UPSC Mains question papers)
│   │   └── prelims/*.pdf         (26 scanned PDFs of UPSC Prelims question papers)
│   │
│   └── processed/                ★ Training datasets (JSONL, versioned in git)
│       ├── gk_summarizer.jsonl   (298 examples — article → summary)
│       ├── article_filter.jsonl  (311 examples — headline → YES/NO)
│       └── quiz_setter.jsonl     (25 examples — summary → MCQs)
│
└── __init__.py                   Makes this folder a Python package (empty)
```

Outside the training folder, the relevant files are:

```
app/ai/
├── orchestrator.py               ★ The "traffic cop" — routes requests to the right persona
├── model_registry.py             Manages which AI model is active for each persona
├── config/
│   ├── models.yaml               ★ Model settings (name, max_tokens, temperature)
│   └── prompts/
│       ├── summarizer.yaml       Instructions the AI follows when summarizing
│       ├── article_filter.yaml   Instructions for relevance filtering
│       └── question_setter.yaml  Instructions for MCQ generation
├── personas/
│   ├── summarizer.py             Builds prompt, parses response for summarizer
│   ├── article_filter.py         Builds prompt, parses response for filter
│   └── question_setter.py        Builds prompt, parses response for quiz
└── providers/
    └── nim.py                    ★ Talks to NVIDIA's cloud API (with rate limiting & LoRA)

notebooks/
└── qlora_finetune.ipynb          ★ Colab notebook — run this to train our models
```
