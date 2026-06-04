from pathlib import Path

import yaml

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"


def _load_template() -> dict[str, str]:
    path = _PROMPT_DIR / "article_filter.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def build_prompt(headline: str, body_text: str) -> tuple[str, str]:
    template = _load_template()
    system = template["system"]
    prompt = template["prompt_template"].format(
        headline=headline,
        body_preview=body_text[:500],
    )
    return system, prompt


def parse_response(response_text: str) -> bool:
    return "YES" in response_text.strip().upper()[:10]
