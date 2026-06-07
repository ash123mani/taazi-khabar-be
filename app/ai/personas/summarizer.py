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


SECTIONS = {
    "gk summary": "gist",
    "gk pointers": "gist",
    "law/rule change": "gist",
    "syllabus tag": "syllabus",
    "key terms": "terms",
}


def parse_response(response_text: str) -> dict[str, Any]:
    lines = response_text.strip().splitlines()
    gist: list[str] = []
    syllabus_topic: str = ""
    key_terms: list[str] = []
    current_section: str | None = None

    for line in lines:
        stripped = line.rstrip()
        lower = stripped.lower().strip()

        matched_section = None
        for key, value in SECTIONS.items():
            if lower.startswith("### ") and key in lower:
                matched_section = value
                break

        if matched_section:
            current_section = matched_section
            colon = stripped.find(":")
            if colon != -1 and current_section == "syllabus":
                rest = _strip_md(stripped[colon + 1:])
                if rest:
                    syllabus_topic = rest
                    current_section = None
            elif colon != -1 and current_section == "terms":
                rest = _strip_md(stripped[colon + 1:])
                if rest:
                    key_terms = [t.strip() for t in rest.split(",") if t.strip()]
            gist.append(stripped)
            continue

        if current_section == "syllabus":
            if "###" in lower:
                current_section = None
                continue
            clean = _strip_md(stripped.lstrip("- ").lstrip("* "))
            if clean:
                syllabus_topic = clean
                current_section = None
            continue

        if current_section == "terms":
            if "###" in lower:
                current_section = None
                continue
            clean = _strip_md(stripped.lstrip("- ").lstrip("* "))
            if clean:
                key_terms = [t.strip() for t in clean.split(",") if t.strip()]
            current_section = None
            continue

        if current_section == "gist":
            gist.append(stripped)

    return {
        "gk_gist": "\n".join(gist) if gist else response_text,
        "syllabus_topic": syllabus_topic or None,
        "key_terms": key_terms,
    }
