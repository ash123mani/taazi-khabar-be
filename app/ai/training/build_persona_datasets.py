"""
Build Alpaca-format training datasets for all three personas.

Usage:
    python -m app.ai.training.build_persona_datasets --all

Outputs JSONL files to app/ai/training/data/processed/
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import joinedload

from app.ai.model_registry import registry
from app.ai.orchestrator import AIOrchestrator
from app.config import settings
from app.models.article import Article

logger = logging.getLogger("build_dataset")

DATA_DIR = Path(__file__).resolve().parent / "data"
PROC_DIR = DATA_DIR / "processed"
PROC_DIR.mkdir(parents=True, exist_ok=True)

TEACHER_MODEL = "qwen/qwen3.5-122b-a10b"

SEM = asyncio.Semaphore(3)


def _load_dedup_set(out_path: Path) -> set:
    """Load existing output keys for dedup (first 80 chars of input)."""
    if not out_path.exists():
        return set()
    seen = set()
    with open(out_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    r = json.loads(line)
                    seen.add(r.get("input", "")[:80])
                except json.JSONDecodeError:
                    continue
    return seen


async def _fetch_articles(db: AsyncSession) -> list[Article]:
    result = await db.execute(
        select(Article)
        .options(joinedload(Article.category))
        .where(Article.body_text.isnot(None), Article.gk_summary.isnot(None))
        .order_by(Article.published_at.desc())
    )
    articles = list(result.unique().scalars().all())
    logger.info("Fetched %d articles with summaries", len(articles))
    return articles


async def _llm_complete(
    orch: AIOrchestrator, prompt: str, system: str,
    max_tokens: int = 2048, temperature: float = 0.3,
) -> str:
    model_config = registry.get_active_model("summarizer")
    model_name = TEACHER_MODEL or (model_config.name if model_config else "qwen/qwen3.5-122b-a10b")
    api_key, base_url = settings.get_persona_credentials("summarizer")
    async with SEM:
        resp = await orch._provider.complete(
            prompt=prompt, system=system,
            model=model_name, api_key=api_key, base_url=base_url,
            max_tokens=max_tokens, temperature=temperature,
        )
    return resp.text


# ---------------------------------------------------------------------------
#  GK SUMMARIZER  — export existing article→summary pairs from DB
# ---------------------------------------------------------------------------

SUMMARIZER_INSTRUCTION = (
    "Summarize the following UPSC current affairs article for Civil Services Examination preparation. "
    "Include GK Gist (Prelims Focus, Mains Dimensions, Interview Angle), Syllabus Tag, "
    "Key Terms, and Category."
)

SUMMARIZER_REGEN_SYSTEM = "You are a UPSC GK summary expert. Rewrite summaries to be more comprehensive and exam-oriented."

SUMMARIZER_REGEN_PROMPT = """Rewrite this UPSC GK summary to be more comprehensive, following this exact format:

### GK Gist:
[2-3 paragraph summary covering Prelims Focus, Mains Dimensions, Interview Angle]

### Syllabus Tag: [specific UPSC syllabus topic]
### Key Terms: [comma-separated]
### Category: [subject area]

Original Article: {headline}
Original Summary: {summary}
Original Syllabus Tag: {syllabus_tag}
Original Key Terms: {key_terms}
Original Category: {category}

Output ONLY the rewritten summary in the format above."""


async def build_summarizer_dataset(orch: AIOrchestrator, db: AsyncSession) -> Path:
    out_path = PROC_DIR / "gk_summarizer.jsonl"
    articles = await _fetch_articles(db)
    seen = _load_dedup_set(out_path)
    logger.info("Building summarizer dataset from %d articles", len(articles))

    # Regenerate only first 20 for quality improvement; rest use existing
    regen_set = {a.id for a in articles[:20] if a.gk_summary}

    with open(out_path, "a") as out:
        for idx, article in enumerate(articles):
            if not article.gk_summary or len(article.gk_summary) < 50:
                continue
            inp = (article.body_text or article.gk_summary)[:2000]
            if inp[:80] in seen:
                continue

            if article.id in regen_set:
                try:
                    output = await _llm_complete(
                        orch, SUMMARIZER_REGEN_PROMPT.format(
                            headline=article.headline,
                            summary=article.gk_summary[:2000],
                            syllabus_tag=article.syllabus_tag or "General Studies",
                            key_terms=", ".join(article.key_terms or []),
                            category=article.category.name if article.category else "General",
                        ),
                        SUMMARIZER_REGEN_SYSTEM,
                        temperature=0.3,
                    )
                except Exception:
                    output = None
                if output:
                    record = {
                        "instruction": SUMMARIZER_INSTRUCTION,
                        "input": inp,
                        "output": output,
                        "source": str(article.id),
                    }
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    seen.add(inp[:80])
                    logger.info("  [%d/%d] Regenerated article %s", idx + 1, len(articles), article.id)
                    continue

            # Use existing summary directly
            output = (
                f"### GK Gist:\n{article.gk_summary}\n"
                f"### Syllabus Tag: {article.syllabus_tag or 'General Studies'}\n"
                f"### Key Terms: {', '.join(article.key_terms or [])}\n"
                f"### Category: {article.category.name if article.category else 'General'}"
            )
            record = {
                "instruction": SUMMARIZER_INSTRUCTION,
                "input": inp,
                "output": output,
                "source": str(article.id),
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            seen.add(inp[:80])

    count = sum(1 for _ in open(out_path) if _.strip())
    logger.info("Summarizer: %d records → %s", count, out_path)
    return out_path


# ---------------------------------------------------------------------------
#  ARTICLE FILTER  — existing articles as positives + a few synthetic negatives
# ---------------------------------------------------------------------------

FILTER_SYSTEM = "You are a UPSC syllabus expert."

FILTER_NEGATIVE_PROMPT = """Write a news HEADLINE and 2-sentence SUMMARY that is NOT relevant for UPSC Civil Services Exam preparation (e.g., celebrity news, sports, entertainment, fashion, lifestyle). Output exactly:

Headline: <headline>
Summary: <summary>"""


async def build_filter_dataset(orch: AIOrchestrator, db: AsyncSession) -> Path:
    out_path = PROC_DIR / "article_filter.jsonl"
    articles = await _fetch_articles(db)
    seen = _load_dedup_set(out_path)
    logger.info("Building filter dataset from %d existing articles + synthetic negatives", len(articles))

    with open(out_path, "a") as out:
        # Positive: all existing articles
        pos_count = 0
        for article in articles:
            inp = f"Headline: {article.headline}\nBody: {(article.gk_summary or article.body_text or '')[:500]}"
            if inp[:80] in seen:
                continue
            record = {
                "instruction": "Determine if the following news article is relevant for UPSC Civil Services Examination preparation. Respond with YES or NO.",
                "input": inp,
                "output": "YES",
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            seen.add(inp[:80])
            pos_count += 1
        logger.info("  Added %d positive examples", pos_count)

        # Negative: generate ~20 negatives (2 API calls with 10 each)
        def _parse_neg(text: str) -> dict | None:
            h, b = "", ""
            for line in text.strip().splitlines():
                if line.startswith("Headline:"):
                    h = line[len("Headline:"):].strip()
                elif line.startswith("Summary:"):
                    b = line[len("Summary:"):].strip()
            if h and b:
                return {
                    "instruction": "Determine if the following news article is relevant for UPSC Civil Services Examination preparation. Respond with YES or NO.",
                    "input": f"Headline: {h}\nBody: {b[:500]}",
                    "output": "NO",
                }
            return None

        multi_prompt = """Generate 10 different news headlines and summaries that are NOT relevant for UPSC Civil Services Exam preparation. Each one should be on a different topic (celebrity, sports, entertainment, fashion, lifestyle, tech gadgets, food, travel, etc.).

Output each as:
Headline: ...
Summary: ...

Separate each with a blank line."""

        try:
            text = await _llm_complete(orch, multi_prompt, FILTER_SYSTEM, max_tokens=2000, temperature=0.9)
            blocks = re.split(r"\n\n+", text.strip())
            neg_count = 0
            for block in blocks:
                r = _parse_neg(block)
                if r and r["input"][:80] not in seen:
                    out.write(json.dumps(r, ensure_ascii=False) + "\n")
                    seen.add(r["input"][:80])
                    neg_count += 1
            logger.info("  Added %d negative examples", neg_count)
        except Exception as e:
            logger.warning("  Negative generation failed: %s", e)

    count = sum(1 for _ in open(out_path) if _.strip())
    logger.info("Filter: %d records → %s", count, out_path)
    return out_path


# ---------------------------------------------------------------------------
#  QUIZ SETTER  — synthetic MCQs from article summaries (batched)
# ---------------------------------------------------------------------------

QUIZ_SYSTEM = "You are a UPSC question paper expert. Generate MCQs in the exact UPSC Prelims style."

QUIZ_BATCH_PROMPT = """Based on the following {num} UPSC current affairs article summaries, generate 3 multiple choice questions for EACH article. Total: {total} questions.

The questions must:
- Test conceptual understanding (not rote recall)
- Have plausible distractors
- Match UPSC Prelims difficulty

{articles_text}

For each question, output:

Q: Question text
A) Option A
B) Option B
C) Option C
D) Option D
Answer: A
Explanation: Brief explanation
Difficulty: Easy|Medium|Hard

Separate questions with ---

Group questions by article with a header like "Article 1:" before each group."""


async def build_quiz_dataset(orch: AIOrchestrator, db: AsyncSession) -> Path:
    out_path = PROC_DIR / "quiz_setter.jsonl"
    articles = await _fetch_articles(db)
    articles = [a for a in articles if a.gk_summary and len(a.gk_summary) > 100]
    seen = _load_dedup_set(out_path)

    # Skip articles already in dedup set
    new_articles = []
    for a in articles:
        inp = (a.gk_summary or "")[:500]
        if inp[:80] not in seen:
            new_articles.append(a)
    articles = new_articles[:90]
    total_batches = (len(articles) + 1) // 2
    logger.info("Building quiz dataset from %d new articles (%d batches of 2)", len(articles), total_batches)

    if not articles:
        logger.info("No new articles to process. Already have %d records.", len(seen))
        return out_path

    batch_size = 2

    with open(out_path, "a") as out:
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]

            parts = []
            for j, a in enumerate(batch, 1):
                parts.append(
                    f"Article {j}: {a.headline}\n"
                    f"Summary: {(a.gk_summary or '')[:500]}\n"
                    f"Syllabus: {a.syllabus_tag or 'General'}"
                )

            prompt = QUIZ_BATCH_PROMPT.format(
                num=len(batch),
                total=len(batch) * 3,
                articles_text="\n\n".join(parts),
            )

            for attempt in range(3):
                try:
                    text = await _llm_complete(
                        orch, prompt, QUIZ_SYSTEM,
                        max_tokens=3072, temperature=0.7,
                    )
                    break
                except Exception as e:
                    if attempt < 2:
                        await asyncio.sleep(3)
                        continue
                    logger.warning("  Batch %d failed after 3 tries: %s", i // batch_size, e)
                    text = ""
                    break

            mcqs = _parse_mcq_blocks(text)
            logger.info("  Batch %d: extracted %d MCQs", i // batch_size, len(mcqs))

            for art_idx, article in enumerate(batch):
                article_mcqs = mcqs[art_idx * 3: (art_idx + 1) * 3]
                for mcq in article_mcqs:
                    inp = (article.gk_summary or "")[:500]
                    if inp[:80] in seen:
                        continue
                    output = (
                        f"Q: {mcq['question_text']}\n"
                        f"A) {mcq['options'].get('A', '')}\n"
                        f"B) {mcq['options'].get('B', '')}\n"
                        f"C) {mcq['options'].get('C', '')}\n"
                        f"D) {mcq['options'].get('D', '')}\n"
                        f"Answer: {mcq['correct_answer']}"
                    )
                    if mcq.get("explanation"):
                        output += f"\nExplanation: {mcq['explanation']}"
                    output += f"\nDifficulty: {mcq.get('difficulty', 'Medium')}"

                    record = {
                        "instruction": "Generate a UPSC-style multiple choice question with 4 options and indicate the correct answer.",
                        "input": inp,
                        "output": output,
                        "source": str(article.id),
                    }
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    seen.add(inp[:80])

    count = sum(1 for _ in open(out_path) if _.strip())
    logger.info("Quiz setter: %d records → %s", count, out_path)
    return out_path


def _parse_mcq_blocks(text: str) -> list[dict[str, Any]]:
    questions = []
    blocks = re.split(r"\n-{3,}\n", text.strip())
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        q_match = re.search(r"^Q:\s*(.+?)$", block, re.MULTILINE)
        if not q_match:
            continue
        options = {}
        for letter in ("A", "B", "C", "D"):
            m = re.search(rf"^{letter}\)\s*(.+?)$", block, re.MULTILINE)
            if m:
                options[letter] = m.group(1).strip()
        answer_m = re.search(r"^Answer:\s*([A-D])", block, re.MULTILINE)
        expl_m = re.search(r"^Explanation:\s*(.+?)$", block, re.MULTILINE)
        diff_m = re.search(r"^Difficulty:\s*(Easy|Medium|Hard)", block, re.MULTILINE)
        questions.append({
            "question_text": q_match.group(1).strip(),
            "options": options,
            "correct_answer": answer_m.group(1) if answer_m else "A",
            "explanation": expl_m.group(1).strip() if expl_m else None,
            "difficulty": diff_m.group(1) if diff_m else "Medium",
        })
    return questions


# ---------------------------------------------------------------------------
#  MAIN
# ---------------------------------------------------------------------------


async def main(build_quiz: bool, build_filter: bool, build_summarizer: bool):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", force=True)

    db_url = str(settings.database_url)
    if "postgresql" in db_url and "+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url, pool_pre_ping=True, pool_size=1, connect_args={"statement_cache_size": 0})
    Session = async_sessionmaker(engine, expire_on_commit=False)
    db = Session()

    try:
        await registry.db_seed_from_yaml(db)
        await db.commit()
    except Exception as e:
        logger.warning("Registry seed: %s", e)

    orch = AIOrchestrator()

    if build_summarizer:
        logger.info("=" * 60)
        logger.info("Building GK SUMMARIZER dataset")
        await build_summarizer_dataset(orch, db)

    if build_filter:
        logger.info("=" * 60)
        logger.info("Building ARTICLE FILTER dataset")
        await build_filter_dataset(orch, db)

    if build_quiz:
        logger.info("=" * 60)
        logger.info("Building QUIZ SETTER dataset")
        await build_quiz_dataset(orch, db)

    await db.close()
    await engine.dispose()
    logger.info("All done.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiz", action="store_true")
    parser.add_argument("--filter", action="store_true")
    parser.add_argument("--summarizer", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if args.all or not (args.quiz or args.filter or args.summarizer):
        args.quiz = args.filter = args.summarizer = True
    asyncio.run(main(
        build_quiz=args.quiz,
        build_filter=args.filter,
        build_summarizer=args.summarizer,
    ))
