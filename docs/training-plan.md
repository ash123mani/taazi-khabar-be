# Training Execution Plan

## Overview

Fine-tune **one** LoRA adapter that handles all 3 tasks (summarizer, filter, quiz setter).
The base model learns to switch behavior based on the `instruction` field in each example.

**Dataset**: `combined.jsonl` (704 records, ~2.1 MB)

| Task | Records | Instruction Prefix |
|------|---------|-------------------|
| Summarizer | 298 | "Summarize this UPSC article..." |
| Article Filter | 311 | "Determine if this is UPSC-relevant..." |
| Quiz Setter | 95 | "Generate UPSC-style MCQ..." |

---

## Phase 1: Datasets ✅ Done

- Fixed quiz batch size (5→2) to reduce 500 errors
- Regenerated quiz setter: 25 → 95 records
- Merged all 3 into `data/processed/combined.jsonl`

## Phase 2: Train One Adapter (Colab)

**You do this — takes ~2-3 hours once.**

1. Upload `app/ai/training/data/processed/combined.jsonl` to Google Drive at `MyDrive/TaaziKhabar/training/combined.jsonl`
2. Open `notebooks/qlora_finetune.ipynb` in Colab
3. Mount Drive, update paths, Runtime → Run all
4. Adapter saves to `MyDrive/TaaziKhabar/adapters/combined-v1/`

## Phase 3: Evaluate

Quick test in notebook (cell 8) — swap the test prompt for each task:

```python
# Test summarizer
prompt = "### Instruction:\nSummarize this UPSC article...\n### Input:\n<real article body>\n### Response:\n"

# Test filter
prompt = "### Instruction:\nDetermine if this is UPSC-relevant...\n### Input:\nHeadline: ...\nBody: ...\n### Response:\n"

# Test quiz
prompt = "### Instruction:\nGenerate UPSC-style MCQ...\n### Input:\n<article summary>\n### Response:\n"
```

Check:
- Does summarizer output proper sections (Prelims/Mains/Interview)?
- Does filter give correct YES/NO?
- Does quiz produce well-formed MCQs?

## Phase 4: Deploy

1. Upload adapter to NVIDIA NIM LoRA serving
2. Update `orchestrator.py` to use `complete_with_lora()` with combined adapter
3. Gradual roll-out: filter first (low risk), then summarizer, then quiz

## Dataset Files

| File | Records | Use |
|------|---------|-----|
| `combined.jsonl` | 704 | Training (1 adapter for all 3 tasks) |
| `gk_summarizer.jsonl` | 298 | Individual (reference) |
| `article_filter.jsonl` | 311 | Individual (reference) |
| `quiz_setter.jsonl` | 95 | Individual (reference) |
