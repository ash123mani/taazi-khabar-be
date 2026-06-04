from pathlib import Path
from typing import Any

import yaml

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"


def _load_template() -> dict[str, str]:
    path = _PROMPT_DIR / "summarizer.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def build_prompt(article_body: str) -> tuple[str, str]:
    template = _load_template()
    system = template["system"]
    prompt = template["prompt_template"].format(article_body=article_body)
    return system, prompt


import re


def _strip_md(text: str) -> str:
    return re.sub(r"\*+", "", text).strip()


def parse_response(response_text: str) -> dict[str, Any]:
    lines = response_text.strip().splitlines()
    gist: list[str] = []
    syllabus_topic: str = ""
    key_terms: list[str] = []
    current_section: str | None = None

    for line in lines:
        stripped = line.strip()
        lower = _strip_md(stripped).lower()

        if lower.startswith("gk gist") or "gk gist" in lower[:20]:
            current_section = "gist"
            colon = stripped.find(":")
            if colon != -1:
                rest = _strip_md(stripped[colon + 1:])
                if rest:
                    gist.append(rest)
            continue
        elif lower.startswith("syllabus topic") or "syllabus topic" in lower[:25]:
            current_section = "syllabus"
            colon = stripped.find(":")
            if colon != -1:
                rest = _strip_md(stripped[colon + 1:])
                if rest:
                    syllabus_topic = rest
                    current_section = None
            continue
        elif lower.startswith("key terms") or "key terms" in lower[:15]:
            current_section = "terms"
            colon = stripped.find(":")
            if colon != -1:
                rest = _strip_md(stripped[colon + 1:])
                if rest:
                    key_terms = [t.strip() for t in rest.split(",") if t.strip()]
            continue

        if current_section == "gist":
            clean = _strip_md(stripped.lstrip("- ").lstrip("* "))
            if clean:
                gist.append(clean)
        elif current_section == "syllabus":
            clean = _strip_md(stripped.lstrip("- ").lstrip("* "))
            if clean:
                syllabus_topic = clean
                current_section = None
        elif current_section == "terms":
            clean = _strip_md(stripped.lstrip("- ").lstrip("* "))
            if clean:
                key_terms = [t.strip() for t in clean.split(",") if t.strip()]

    return {
        "gk_gist": "\n".join(gist) if gist else response_text,
        "syllabus_topic": syllabus_topic,
        "key_terms": key_terms,
    }
