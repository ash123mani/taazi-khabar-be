import re
from pathlib import Path
from typing import Any

import yaml

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"


def _load_template() -> dict[str, str]:
    path = _PROMPT_DIR / "question_setter.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _summarize_articles(articles: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for i, article in enumerate(articles, 1):
        headline = article.get("headline", "Untitled")
        body = article.get("gk_summary") or article.get("body_text", "")
        parts.append(f"Article {i}: {headline}\n{body[:1500]}")
    return "\n\n".join(parts)


def build_prompt(articles: list[dict[str, Any]], num_questions: int) -> tuple[str, str]:
    template = _load_template()
    system = template["system"]
    article_summaries = _summarize_articles(articles)
    prompt = template["prompt_template"].format(
        article_summaries=article_summaries,
        num_questions=num_questions,
    )
    return system, prompt


def parse_response(response_text: str) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    blocks = re.split(r"\n---\n", response_text.strip())

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        q_match = re.search(r"^Q:\s*(.+?)$", block, re.MULTILINE)
        if not q_match:
            continue

        options: dict[str, str] = {}
        for letter in ("A", "B", "C", "D"):
            opt_match = re.search(
                rf"^{letter}\)\s*(.+?)$", block, re.MULTILINE
            )
            if opt_match:
                options[letter] = opt_match.group(1).strip()

        answer_match = re.search(
            r"^Answer:\s*([A-D])", block, re.MULTILINE
        )
        explanation_match = re.search(
            r"^Explanation:\s*(.+?)$", block, re.MULTILINE
        )
        difficulty_match = re.search(
            r"^Difficulty:\s*(Easy|Medium|Hard)", block, re.MULTILINE
        )

        questions.append({
            "question_text": q_match.group(1).strip(),
            "options": options,
            "correct_answer": answer_match.group(1) if answer_match else "A",
            "explanation": explanation_match.group(1).strip() if explanation_match else None,
            "difficulty": difficulty_match.group(1) if difficulty_match else None,
        })

    return questions
