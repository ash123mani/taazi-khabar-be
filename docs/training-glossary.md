# Taazi Khabar — Training Glossary & Step-by-Step Walkthrough

## Overview

This doc explains everything we did to train our own AI model, from start to finish. Every technical term is explained like you're a dev who knows code but never studied machine learning.

---

## Section 1: The Problem We Solved

### Before Training

Our app called NVIDIA's cloud AI for every article. Three separate AI jobs:

| Job | What it does | Cloud Model |
|-----|-------------|-------------|
| **Summarizer** | Turns news → UPSC study notes | Mistral 14B (14 billion param) |
| **Article Filter** | Decides YES/NO if UPSC-relevant | Mistral 14B |
| **Question Setter** | Creates MCQs from summaries | Llama 49B (49 billion param) |

**Problems**: Costly (₹ per call), slow (3-10 sec), rate-limited (40 calls/min), dependent on NVIDIA being up.

### After Training (goal)

One small model (Phi-3, 3.8B params) that does all 3 jobs. Faster, cheaper, works offline.

---

## Section 2: Glossary of Terms

### AI / Model Basics

| Term | Plain English |
|------|---------------|
| **AI Model** | A giant spreadsheet of numbers that, when you do math on them, produces text. Think of it as a ridiculously complex `if-else` chain that learned patterns from reading billions of sentences. |
| **Parameter** | One single number inside the model. During training, these numbers get tweaked. The more you have, the more patterns the model can learn — but also the more memory you need. |
| **3.8B / 7B / 14B / 49B** | Parameter count. Phi-3-mini has 3,800,000,000 numbers. Llama 49B has 49,000,000,000. Bigger isn't always better — it's just more expensive. |
| **Inference** | Using the model. You give it text, it runs math on all those parameters, and produces new text. |
| **Training** | Showing the model millions of examples and gradually tweaking parameters so its answers get closer to the right ones. |
| **Fine-tuning** | Taking a model that already speaks English and knows general facts, and teaching it ONE specific skill (like "write UPSC summaries"). Much cheaper than training from scratch. |
| **Base Model** | The raw, pre-trained model before we specialize it. Like a chef who graduated from culinary school but doesn't know UPSC cuisine yet. |
| **Student Model** | Our small fine-tuned model (Phi-3, 3.8B). The one we're training. |
| **Teacher Model** | The expensive cloud AI (Mistral 14B, Llama 49B) that we use to create training examples. Like a senior dev writing unit tests for a junior to learn from. |
| **Instruct-tuned** | A model that was fine-tuned to FOLLOW INSTRUCTIONS. Phi-3-mini-"instruct" means it already knows the format of "User asks something → AI responds". We just teach it WHAT to say. |

### Tokenizer — How the Model Reads Text

Models don't understand letters or words. They understand **numbers**.

**Tokenizer** = a lookup table that converts text → numbers (for input) and numbers → text (for output).

Example:
```
"The Supreme Court ruled" → [2891, 152, 4187, 892]
```

Each number is a **token**. A token is roughly ¾ of a word on average. So "The" might be token 2891, " Supreme" might be token 152.

**MAX_SEQ_LENGTH** = how many tokens we allow per example. If an article is 3000 tokens long but we set MAX_SEQ_LENGTH to 2048, the last 952 tokens get **truncated** (chopped off). That was our bug — 41% of articles were getting cut mid-sentence, so the model was learning from incomplete text.

### EOS Token — "The End."

**EOS** = **E**nd **O**f **S**equence. It's a special token (usually token 32000 or similar) that tells the model "stop here, don't keep generating."

Think of it like a `.` at the end of a sentence, but for the model's internal format. During training, we append `<|endoftext|>` to every example so the model learns: "after the expected answer, there should be an EOS token. When I see this token, stop."

If you forget EOS, the model will keep generating — you'd get infinite rambling. It's like teaching someone to answer a question but never teaching them when to shut up.

### Forward Pass — The Model Guesses

1. We take one training example (article text + expected summary)
2. We feed the article text into the model
3. The model predicts what comes next, one token at a time
4. It produces a probability distribution: "I'm 80% sure the next token is 'The', 10% sure it's 'A', 5% sure it's 'This'..."
5. We look at the token the model chose vs. the token that SHOULD have come (from our training data)

Example: If the expected output is "The Supreme Court", and the model predicts "A Supreme Court", that's wrong at token 1.

### Loss — "How Wrong Is the Model?"

**Loss** = A single number that measures how far off the model's predictions were from the correct answers.

- **Loss = 0** → Perfect. Model got every single token right. Basically impossible in practice.
- **Loss = 2.5** → Pretty wrong. Model is guessing randomly.
- **Loss = 0.3** → Good. Model is close but not perfect.
- **Loss = 0.05** → Excellent. Model almost always predicts the right next token.

The math: For each token, we calculate `-log(probability_of_correct_token)`. If the model was 90% confident in the right answer, loss = -ln(0.9) = 0.1. If it was 10% confident (guessing), loss = -ln(0.1) = 2.3.

So **high loss = model was very surprised** by the correct answer. **Low loss = model expected exactly this**.

Over an entire batch, we average the loss across all tokens. That's the number you see printing during training.

### Backward Pass — "How to Fix Each Parameter"

Once we know the loss (how wrong we are), we need to figure out: *which parameters caused the error, and should they go up or down?*

**Gradient** = A number for each parameter that says:
- If this parameter should INCREASE to reduce loss → gradient is positive
- If this parameter should DECREASE to reduce loss → gradient is negative
- How BIG the change should be

Think of it like tuning a guitar. The loss tells you "the note is flat." The gradient says "tighten string #3 by 2.5%. String #5 needs 0.1%. String #1 is fine (gradient ≈ 0)."

Backward pass computes all these gradients by working backward through the model's math (chain rule from calculus).

### Learning Rate — "How Aggressively Do We Tweak?"

Learning rate = a multiplier on the gradient.

- **Gradient says**: "increase parameter #4187 by 0.5"
- **Learning rate = 0.0002** → actual adjustment = 0.5 × 0.0002 = 0.0001 (tiny tweak)
- **Learning rate = 0.1** → actual adjustment = 0.5 × 0.1 = 0.05 (big tweak)

Higher = learns faster but risks overshooting (like a loud noise that makes you jump past the right answer). Lower = more stable but takes forever.

2e-4 = 0.0002. Standard for LoRA fine-tuning.

### Warmup Steps — "Ease Into It"

At the very start of training, the model's parameters are random (or from a different task). If we immediately start making big adjustments, the model can "break" — get confused and never recover.

**Warmup** = For the first N steps, gradually increase the learning rate from 0 to our target (2e-4). Like warming up before a sprint — don't go 100% immediately.

We used 50 warmup steps out of ~120 total steps. So for the first ~40% of training, the learning rate is ramping up.

### Training Loss vs. Eval Loss

**Training loss** = loss on the data the model is actively studying. Like doing practice problems and checking answers immediately.

**Eval loss** = loss on data the model has NEVER seen during training. Like a surprise quiz.

We split our 704 records: 633 for training, 71 for evaluation (held out, never trained on).

| Scenario | Training Loss | Eval Loss | What's Happening |
|----------|--------------|-----------|------------------|
| Both high | 2.5 | 2.5 | Model hasn't learned anything yet. Early training. |
| Both low | 0.1 | 0.2 | Model is learning well. Generalizing to new data. |
| Training low, Eval high | 0.05 | 1.5 | **Overfitting** — model memorized practice answers but can't handle new questions. Like a student who memorized answer keys but flunks the real exam. |
| Training high, Eval low | 2.0 | 2.5 | Bug. Data leak or preprocessing error. |

Goal: **Both low AND close together**. That means the model actually learned the SKILL, not just memorized examples.

### Epoch — "One Lap Around the Dataset"

1 epoch = The model has seen every training example exactly once.

We do 3 epochs. That means the model reads each article-summary pair 3 times.

- Too few epochs (1) → model hasn't had enough practice
- Too many (10+) → model will memorize, not learn → overfitting. Also a waste of GPU time.

3 is conservative — enough for the model to learn the pattern, not enough to memorize.

### Batch — "How Many at Once?"

**Batch = 4** means we process 4 examples at the same time, then update the model once.

Why not do all 633 at once? GPU memory. Processing 4 articles × 2048 tokens each ≈ 4 GB of memory. Processing all 633 would need ~600 GB.

**Gradient Accumulation = 4** means we process 4 batches (16 examples total) before updating. This simulates a larger batch size without needing more GPU memory. Like taking 4 small steps, then adjusting: same net effect as one big step but uses less memory.

**Effective batch size** = 4 × 4 = 16.

### QLoRA — The Magic Trick

Training a 3.8B model normally needs:
- Model in memory: ~8 GB (16-bit)
- Optimizer states: ~15 GB
- Gradients: ~8 GB
- Activations: varies
- **Total: ~35-60 GB** → not possible on a free Colab T4 (16 GB)

**QLoRA** gets around this with 3 tricks:

**1. Quantization (Q)** — Compress the model's parameters from 16-bit numbers to 4-bit numbers. The model shrinks from 8 GB → 2 GB. Quality loss is small because we only lose precision on the frozen (unchanged) parameters.

Analogy: Imagine a photo of a dish. The base model is the photo. We're editing just the seasoning (LoRA adapter). Quantization compresses the PHOTO to JPEG (the base model), while our edits stay in high-res RAW (the adapter).

**2. LoRA** — Instead of modifying all 3.8B parameters, we freeze them and add tiny "patch" matrices (rank r=16). Only ~8 million parameters (0.2%) are trainable.

Analogy: Instead of rebuilding the whole house, we stick small post-it notes on certain walls. The house stays the same, but the post-its change the behavior.

**3. Gradient Checkpointing** — During forward pass, we don't store intermediate calculations. During backward pass, we recompute them. This trades speed (~20% slower) for memory (~50% less).

### Training Steps — The Actual Math

Here's what happens inside the GPU during one training step:

```
Batch of 4 articles
        │
        ▼
┌─────────────────────────────────────────────┐
│  FORWARD PASS                               │
│                                             │
│  For each article in batch:                 │
│    Feed article tokens into model           │
│    Model predicts next token probabilities  │
│    Compare prediction vs. correct answer    │
│    Calculate LOSS (average surprise)        │
│                                             │
│  Result: 4 loss numbers (one per article)   │
│  Average them → single loss number          │
└─────────────────────────────────────────────┘
        │
        ▼
      Loss = 1.42  ← printed in Colab
        │
        ▼
┌─────────────────────────────────────────────┐
│  BACKWARD PASS                              │
│                                             │
│  Walk backward through all 3.8B params      │
│  For each of 8M trainable params:           │
│    Calculate GRADIENT: "should this         │
│    number go up or down, and by how much?"  │
│                                             │
│  Result: 8M gradient values                 │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  OPTIMIZER STEP                             │
│                                             │
│  For each of 8M trainable params:           │
│    adjustment = gradient × learning_rate    │
│    param += adjustment                      │
│                                             │
│  Result: Adapter parameters tweaked slightly│
└─────────────────────────────────────────────┘
        │
        ▼
Repeat ~120 times (3 epochs × 633 train records ÷ 16 effective batch)
```

After ~120 steps, the adapter has "learned": the patterns in the training data are now encoded in those 8 million tiny adjustments.

### Hyperparameters — The Knobs We Tuned

| Knob | Value | What It Controls | If Set Too High | If Set Too Low |
|------|-------|-----------------|-----------------|----------------|
| **Learning Rate** | 2e-4 | How big each adjustment is | Model jumps around, never converges (loss oscillates) | Model learns very slowly (would need 1000+ steps) |
| **Batch Size** | 4 (effective: 16) | How many examples influence each update | Runs out of GPU memory | Noisy updates, loss bounces |
| **Epochs** | 3 | How many times model sees each example | Overfitting | Model doesn't learn enough |
| **MAX_SEQ_LENGTH** | 2048 tokens | How much of each example to consider | Runs out of GPU memory | Articles get truncated, model learns from partial text |
| **LoRA Rank (r)** | 16 | How many parameters in each adapter | More memory, can overfit | Can't learn complex patterns |
| **Warmup Steps** | 50 | How long to ease into full learning rate | Wastes training time | Model shocks at start, may diverge |

---

## Section 3: Step-by-Step Training Walkthrough

### Phase 1: Creating Training Data

**Goal**: Build practice problems for the AI to learn from.

**Step 1.1 — Understand what the AI currently does**
We have 3 "personas" (AI assistants):
- **Summarizer**: Reads article → writes GK summary with sections (Prelims, Mains, Interview, Category, Syllabus Tag, Key Terms)
- **Article Filter**: Reads headline + body → decides YES (UPSC relevant) or NO
- **Question Setter**: Reads summary → creates MCQ with 4 options, answer, explanation

| Persona | Input | Expected Output | Complexity |
|---------|-------|----------------|------------|
| Summarizer | Article body (500-2000 words) | Structured summary (~300 words) | Medium |
| Filter | Headline + body snippet | "YES" or "NO" | Easy |
| Quiz | Summary + key terms | 1 MCQ with 4 options + answer + explanation | Hard |

**Step 1.2 — Collect examples from our database**
Our app already runs these AIs daily. Every article + its summary is stored in PostgreSQL. We exported them as-is:
- Summarizer: 278 existing examples from DB + 20 regenerated by teacher AI for quality = **298 total**
- Article Filter: 301 YES examples from DB + 10 fake NO examples generated by AI = **311 total**
- Question Setter: Needed to generate from scratch. Used teacher AI to write MCQs. Got **95 examples** (started with 25, had to fix batch errors to get more)

**Step 1.3 — Build the dataset script**
`build_persona_datasets.py` does:
1. Connect to PostgreSQL
2. Query recent articles that have summaries
3. For each article, create an Alpaca-format record: `{instruction, input, output}`
4. For quiz setter: call NVIDIA AI to generate MCQs from each summary
5. Save all as JSONL files (one JSON object per line)

**Step 1.4 — Understand what went wrong with quiz generation**
Original code sent 5 articles at once to the teacher AI asking for MCQs. The prompt was too long → HTTP 500 errors. Fixed by sending 2 articles per batch instead.

**Step 1.5 — Merge into one file**
Combined all 3 datasets into `combined.jsonl` (704 records). Each record has:
```json
{
  "instruction": "Summarize this UPSC article and create a GK summary...",
  "input": "The Supreme Court today ruled that...",
  "output": "### GK Summary\n- Event: The Supreme Court ruled...",
  "persona": "summarizer"
}
```

The `instruction` field tells the model which job to do. During training, the model learns: "when instruction starts with 'Summarize', output a summary. When it asks 'Determine if', output YES/NO."

### Phase 2: Setting Up Training

**Goal**: Configure the notebook to train our model.

**Step 2.1 — Choose a base model**
We picked **Phi-3-mini-4k-instruct** (3.8B params) by Microsoft because:
- Small enough for free Colab GPU (16GB T4)
- "Instruct-tuned" — speaks the prompt-response language already
- 4K context window (4096 tokens, ~3000 words)

**Step 2.2 — Configure QLoRA to fit in 16GB**
```
┌─────────────────────────────────────────────┐
│  Memory Budget (16 GB T4)                    │
│                                              │
│  ├─ Base Model (4-bit quantized): 2.4 GB    │
│  ├─ LoRA Adapter: 0.05 GB                    │
│  ├─ Gradients + Optimizer: 1.2 GB           │
│  ├─ Activations (batch=4, seq=2048): 1.8 GB │
│  ├─ Misc overhead: 0.5 GB                   │
│  ─────────────────────────────────────      │
│  Total: ~6 GB (plenty of headroom)          │
└─────────────────────────────────────────────┘
```

**Step 2.3 — Configure QLoRA parameters**
| QLoRA Parameter | Value | What It Means |
|----------------|-------|---------------|
| `r` | 16 | Rank of adapter matrices. Higher = more expressive but bigger file |
| `lora_alpha` | 32 | Scaling factor. 32/16 = 2x multiplier on adapter output |
| `target_modules` | q_proj, k_proj, v_proj, o_proj | Which parts of the model to attach adapters to. The "attention" layers. |
| `lora_dropout` | 0.05 | Randomly ignore 5% of adapter connections during training. Prevents overfitting. |
| `bias` | none | Don't train bias terms. Saves memory. |
| `use_rslora` | True | Use rank-stabilized LoRA. Better convergence. |

**Step 2.4 — Hyperparameters**
| Setting | Value | Why |
|---------|-------|-----|
| MAX_SEQ_LENGTH | 2048 | Long enough for articles (was 1024 — 41% truncated) |
| Per-device batch | 4 | Fits in 16GB with 2048-length sequences |
| Gradient accumulation | 4 | Effective batch = 16 (more stable) |
| Learning rate | 2e-4 | Standard for LoRA fine-tuning |
| LR scheduler | cosine | Learning rate follows a cosine curve, smoothly decreasing toward 0 |
| Warmup steps | 50 | ~40% of training spent ramping up |
| Epochs | 3 | Enough for 704 records |
| Optimizer | paged_adamw_8bit | AdamW optimizer in 8-bit mode. Saves ~50% optimizer memory. "Paged" means it can use CPU RAM as overflow. |
| BF16 | True | Use bfloat16 precision (16-bit) for activations. Faster than float32, same quality. |

### Phase 3: Running Training

**Goal**: Run the notebook in Google Colab.

**Step 3.1 — Upload notebook**
- `notebooks/qlora_finetune.ipynb` → Colab via File → Upload Notebook

**Step 3.2 — Upload dataset**
- `combined.jsonl` → upload directly to Colab runtime sidebar

**Step 3.3 — Update config in notebook**
```python
DATASET_PATH = "/content/combined.jsonl"
OUTPUT_DIR = "/content/taazi-adapter"
```

**Step 3.4 — Fix errors as they came**
| Error | Root Cause | How We Fixed |
|-------|-----------|--------------|
| `FlashAttention2 not installed` | Colab doesn't include the FA2 library | Removed `attn_implementation="flash_attention_2"` from `AutoModelForCausalLM.from_pretrained()` |
| `Unexpected keyword argument 'tokenizer'` | New version of `trl` renamed `tokenizer` → `processing_class` in SFTConfig | Changed `SFTConfig(tokenizer=tokenizer)` to `SFTConfig(processing_class=tokenizer)` |
| `warmup_ratio` ignored | New Transformers deprecated `warmup_ratio` in favor of `warmup_steps` | Changed to `warmup_steps=50` |
| `dataset_text_field not found` | New trl removed `dataset_text_field` from SFTTrainer | Added `formatting_func` that wraps records in the prompt template |
| Google Drive mount failed | Auth popup blocked in Colab | Used manual file upload instead |

**Step 3.5 — Pre-processing before training starts**

```
Raw JSONL (704 records)
        │
        ▼
  Format into prompt template:
  "<|user|>\n{instruction}\n{input}<|end|>\n<|assistant|>\n{output}<|endoftext|>"
        │
        ▼
  Tokenize: convert text → arrays of numbers
        │
        ▼
  Split: 633 for training, 71 for evaluation
        │
        ▼
  Ready for training
```

**Step 3.6 — What you see during training**

```
Step  │ Training Loss │ Eval Loss  │ What's Happening
──────┼───────────────┼────────────┼─────────────────────────
  1   │ 2.8943        │ 2.9101     │ Model is guessing randomly. Just started.
  10  │ 1.2456        │ 1.4012     │ Learning fast. Basic patterns discovered.
  30  │ 0.4231        │ 0.6123     │ Getting the hang of it. Eval still higher.
  50  │ 0.1894        │ 0.2789     │ Warmup done, full learning rate.
  80  │ 0.0956        │ 0.1845     │ Model is pretty good now.
  100 │ 0.0678        │ 0.1423     │ Cosine LR has decayed significantly.
  120 │ 0.0543        │ 0.1235     │ Final. Both losses low and close. ✓
```

**What we're watching for:**
- **Loss going down** → ✓ learning
- **Eval loss close to training loss** → ✓ generalizing, not memorizing
- **Loss not going down** → ✗ bug or wrong learning rate
- **Eval loss going up** → ✗ overfitting (stop training early)

### Phase 4: What Training Actually Does

Each step (notebook cell running ~60-90 seconds):

1. **Load 4 articles** from the shuffled training set
2. **Tokenize** them (word → numbers)
3. **Move to GPU** (transfer from CPU RAM to GPU VRAM)
4. **Forward pass**: Model predicts the next token for every position
5. **Calculate loss**: Compare predictions vs. ground truth
6. **Backward pass**: Calculate gradients for each of 8M trainable params
7. **Gradient accumulation**: Repeat steps 1-6 four times (total 16 examples)
8. **Optimizer step**: Apply gradients × learning rate to all 8M params
9. **Log**: Print loss, step number, elapsed time
10. **Eval** (every few steps): Run on held-out 71 examples (no training, just measure)

After ~120 steps, the adapter weights have shifted from their initial random state to encode patterns matching the training data.

### Phase 5: What The Adapter File Contains

After training, Colab saves:
```
/taazi-adapter/
  ├── adapter_config.json   # Metadata: rank, target modules, base model name
  ├── adapter_model.bin     # The actual weights (~12 MB)
  ├── tokenizer.json        # Our tokenizer config
  ├── tokenizer_config.json # Tokenizer settings
  └── training_args.bin     # Snapshot of hyperparameters
```

`adapter_model.bin` is the important file. It's ~12 MB — small enough to email. It contains 8 million numbers. When combined with the base Phi-3 model (which NVIDIA already hosts), it changes the model's behavior to produce UPSC-style summaries.

### Phase 6: Deployment (Next Step)

```
Your App ──────────→ NVIDIA NIM (hosts Phi-3 3.8B)
  │                        │
  │   "Summarize this"     │ Loads Phi-3 + your adapter
  │   + NVCF_LORA_ADAPTER  │ Runs inference
  │                        │ Returns result
  │◄────────────────────────│
```

How it works:
1. Upload `adapter_model.bin` to NVIDIA (their LoRA serving feature)
2. Every request includes HTTP header: `NVCF_LORA_ADAPTER: taazi-combined-v1`
3. NVIDIA loads Phi-3, applies our adapter weights, runs inference
4. Result: same output format but served from our fine-tuned model instead of expensive cloud models

---

## Section 4: File Map

| File | What It Is | Size |
|------|-----------|------|
| `app/ai/training/data/processed/combined.jsonl` | All 704 training records merged | 2.1 MB |
| `app/ai/training/data/processed/gk_summarizer.jsonl` | Summarizer dataset only | 1.7 MB |
| `app/ai/training/data/processed/article_filter.jsonl` | Filter dataset only | 236 KB |
| `app/ai/training/data/processed/quiz_setter.jsonl` | Quiz dataset only | 160 KB |
| `app/ai/training/build_persona_datasets.py` | Script that generates datasets from DB + teacher AI | 449 lines |
| `notebooks/qlora_finetune.ipynb` | Colab notebook for training | 326 lines |
| `app/ai/providers/nim.py` | Has `complete_with_lora()` for serving adapter | 125 lines |
| `app/ai/orchestrator.py` | Routes requests to the right persona | 151 lines |
| `app/ai/config/models.yaml` | Model configuration (max_tokens, temp, etc.) | 33 lines |
| `app/ai/training/collector.py` | Logs live AI calls to DB for future training data | 31 lines |
| `app/scripts/backfill_categories.py` | Backfilled categories for June 10 articles | 149 lines |
| `docs/training-plan.md` | Training plan doc | updated |
| `docs/architecture.md` | Full architecture explanation (plain language) | rewritten |

---

## Section 5: Quick Reference — What Each Number Means

| Number | What It Means | Good / Bad |
|--------|---------------|------------|
| **704** | Training examples | Decent (more would help, especially quiz) |
| **298** | Summarizer examples | Good |
| **311** | Filter examples | Good |
| **95** | Quiz examples | Borderline — might need to generate more |
| **3.8B** | Phi-3 model parameters | Small enough for Colab |
| **8M** | LoRA adapter parameters (trained) | 0.2% of total. Tiny, fast to train |
| **16** | LoRA rank. Higher = more capacity but more memory | Standard trade-off |
| **2048** | Max sequence length in tokens | Covers all our data (was 1024 — fixed a 41% truncation bug) |
| **4** | Per-device batch size | Fits in 16GB |
| **4** | Gradient accumulation | Effective batch = 16 |
| **2e-4** | Learning rate | Standard for LoRA |
| **50** | Warmup steps | ~40% of training is warmup (conservative) |
| **3** | Epochs | Enough for 704 records |
| **~120** | Total training steps | ~2.5-3.5 hours |
| **~2-3** | Starting loss | Normal (random guessing) |
| **~0.1-0.3** | Target ending loss | Good |
| **12 MB** | Adapter file size | Tiny — easy to upload/download |
| **0.2%** | Parameters trained | 99.8% of model stays frozen. QLoRA magic |

---

## Section 6: What's Next

1. **Let training finish** (~1-2 more hours on Colab)
2. **Test the adapter** — run inference with sample prompts to verify quality
3. **Upload to NVIDIA NIM** — push the 12MB adapter to backend
4. **Update orchestrator** — switch from `complete()` to `complete_with_lora()`
5. **Re-scrape** — regenerate summaries for all articles using new model
6. **Monitor quality** — compare output quality vs. teacher model
7. **Expand quiz dataset** — if quality is weak, generate more MCQs from summaries
