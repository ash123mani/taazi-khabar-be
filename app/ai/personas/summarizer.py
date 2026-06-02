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


def parse_response(response_text: str) -> dict[str, Any]:
    lines = response_text.strip().splitlines()
    gist: list[str] = []
    syllabus_topic: str = ""
    key_terms: list[str] = []
    current_section: str | None = None

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()

        if lower.startswith("- gk gist") or lower.startswith("gk gist"):
            current_section = "gist"
            continue
        elif lower.startswith("- syllabus topic") or lower.startswith("syllabus topic"):
            current_section = "syllabus"
            continue
        elif lower.startswith("- key terms") or lower.startswith("key terms"):
            current_section = "terms"
            continue

        if current_section == "gist":
            clean = stripped.lstrip("- ").strip()
            if clean and not clean.lower().startswith("gk gist"):
                gist.append(clean)
        elif current_section == "syllabus":
            clean = stripped.lstrip("- ").strip()
            if clean:
                syllabus_topic = clean
                current_section = None
        elif current_section == "terms":
            clean = stripped.lstrip("- ").strip()
            if clean:
                key_terms = [t.strip() for t in clean.split(",") if t.strip()]

    return {
        "gk_gist": "\n".join(gist) if gist else response_text,
        "syllabus_topic": syllabus_topic,
        "key_terms": key_terms,
    }
