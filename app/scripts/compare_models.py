"""
Compare LoRA vs Teacher (NVIDIA NIM) outputs for all 3 personas.

Usage:
    .venv/bin/python -m app.scripts.compare_models

Requires:
    - Backend on localhost:8000 (for fetching articles)
    - LoRA inference server on localhost:8001
    - NVIDIA_API_KEY env vars for teacher models
"""

import os
import sys
import json
import asyncio
import time
from datetime import datetime

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.config import settings

API_BASE = "http://localhost:8000/api"
LORA_BASE = "http://localhost:8001/v1"
NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"

TEACHER_MODELS = {
    "summarizer": "mistralai/ministral-14b-instruct-2512",
    "filter": "mistralai/ministral-14b-instruct-2512",
    "quiz_setter": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
}

NVIDIA_API_KEYS = {
    "summarizer": settings.nvidia_api_key_summarizer.get_secret_value() or settings.nvidia_api_key.get_secret_value(),
    "quiz_setter": settings.nvidia_api_key_question_setter.get_secret_value() or settings.nvidia_api_key.get_secret_value(),
}

# System prompts (same as in the app)
FILTER_SYSTEM = "You are a UPSC current affairs assistant that decides if articles are relevant for UPSC preparation. Reply with only YES or NO."

SUMMARIZER_SYSTEM = (
    "You are a UPSC current affairs assistant. "
    "Summarize the article in structured format with GK Summary, "
    "Prelims Focus, Mains Dimensions, Interview Angle, Category, "
    "Syllabus Tag, and Key Terms."
)

QUIZ_SYSTEM = "You are a UPSC quiz question generator. Create 3 MCQs with 4 options each, correct answer, and explanation."


async def call_lora(messages, max_tokens=300, temperature=0.15):
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.post(
            f"{LORA_BASE}/chat/completions",
            json={
                "model": "phi-3-lora",
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def call_teacher(messages, persona, max_tokens=300, temperature=0.15):
    api_key = NVIDIA_API_KEYS.get(persona) or NVIDIA_API_KEYS.get("summarizer")
    model = TEACHER_MODELS[persona]
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.post(
            f"{NVIDIA_BASE}/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def fetch_articles():
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{API_BASE}/articles", params={"limit": 5})
        r.raise_for_status()
        return r.json()["articles"]


def make_prompts(article):
    headline = article["headline"]
    body = (article.get("body_text") or "")[:1500]

    filter_msgs = [
        {"role": "system", "content": FILTER_SYSTEM},
        {"role": "user", "content": f"Is this article relevant for UPSC?\n\nHeadline: {headline}\n\nBody: {body[:500]}"},
    ]
    summarizer_msgs = [
        {"role": "system", "content": SUMMARIZER_SYSTEM},
        {"role": "user", "content": f"Summarize this article for UPSC preparation:\n\nHeadline: {headline}\n\n{body}"},
    ]
    summary_for_quiz = article.get("gk_summary") or body[:500]
    quiz_msgs = [
        {"role": "system", "content": QUIZ_SYSTEM},
        {"role": "user", "content": f"Create MCQs from this summary:\n\n{summary_for_quiz[:800]}"},
    ]
    return filter_msgs, summarizer_msgs, quiz_msgs


async def main():
    print("Fetching articles...")
    articles = await fetch_articles()
    print(f"Got {len(articles)} articles\n")

    results = {"run_id": datetime.utcnow().isoformat(), "articles": []}

    for i, article in enumerate(articles):
        print(f"\n{'='*60}")
        print(f"Article {i+1}/{len(articles)}: {article['headline'][:80]}")
        print(f"Source: {article['source']} | Date: {article.get('published_at','')[:10]}")
        print(f"{'='*60}")

        filter_msgs, summarizer_msgs, quiz_msgs = make_prompts(article)

        article_result = {
            "id": article["id"],
            "headline": article["headline"],
            "source": article["source"],
            "results": {},
        }

        # --- FILTER ---
        print("\n[Filter] LoRA...", end=" ", flush=True)
        try:
            lora_filter = await call_lora(filter_msgs, max_tokens=10, temperature=0.1)
            print(lora_filter)
        except Exception as e:
            lora_filter = f"ERROR: {e}"
            print(lora_filter)

        print("[Filter] Teacher...", end=" ", flush=True)
        try:
            teacher_filter = await call_teacher(filter_msgs, "filter", max_tokens=10, temperature=0.1)
            print(teacher_filter)
        except Exception as e:
            teacher_filter = f"ERROR: {e}"
            print(teacher_filter)

        article_result["results"]["filter"] = {
            "lora": lora_filter,
            "teacher": teacher_filter,
        }

        # --- SUMMARIZER ---
        print("\n[Summarizer] LoRA...")
        try:
            lora_summary = await call_lora(summarizer_msgs, max_tokens=400, temperature=0.15)
            print(lora_summary[:200] + "...")
        except Exception as e:
            lora_summary = f"ERROR: {e}"
            print(lora_summary)

        print("[Summarizer] Teacher...")
        try:
            teacher_summary = await call_teacher(summarizer_msgs, "summarizer", max_tokens=400, temperature=0.15)
            print(teacher_summary[:200] + "...")
        except Exception as e:
            teacher_summary = f"ERROR: {e}"
            print(teacher_summary)

        article_result["results"]["summarizer"] = {
            "lora": lora_summary,
            "teacher": teacher_summary,
        }

        # --- QUIZ SETTER ---
        print("\n[Quiz] LoRA...")
        try:
            lora_quiz = await call_lora(quiz_msgs, max_tokens=500, temperature=0.3)
            print(lora_quiz[:200] + "...")
        except Exception as e:
            lora_quiz = f"ERROR: {e}"
            print(lora_quiz)

        print("[Quiz] Teacher...")
        try:
            teacher_quiz = await call_teacher(quiz_msgs, "quiz_setter", max_tokens=500, temperature=0.6)
            print(teacher_quiz[:200] + "...")
        except Exception as e:
            teacher_quiz = f"ERROR: {e}"
            print(teacher_quiz)

        article_result["results"]["quiz_setter"] = {
            "lora": lora_quiz,
            "teacher": teacher_quiz,
        }

        results["articles"].append(article_result)

        # Cooldown between articles to avoid overheating
        if i < len(articles) - 1:
            print("\nCooling down 15s...")
            await asyncio.sleep(15)

    # Save results
    out_path = f"/tmp/model_comparison_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n\nResults saved to: {out_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for ar in results["articles"]:
        print(f"\n{ar['headline'][:70]}")
        for persona, res in ar["results"].items():
            lora_ok = not str(res["lora"]).startswith("ERROR")
            teacher_ok = not str(res["teacher"]).startswith("ERROR")
            match = res["lora"].strip() == res["teacher"].strip() if persona == "filter" else "N/A"
            print(f"  {persona:12} LoRA={'✓' if lora_ok else '✗'} Teacher={'✓' if teacher_ok else '✗'}", end="")
            if persona == "filter" and lora_ok and teacher_ok:
                print(f" Match={match}", end="")
            print()


if __name__ == "__main__":
    asyncio.run(main())
