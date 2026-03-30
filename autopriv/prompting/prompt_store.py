from __future__ import annotations

from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    path = PROMPT_DIR / name
    return path.read_text(encoding="utf-8")


def render_prompt(name: str, variables: dict[str, str] | None = None) -> str:
    text = load_prompt(name)
    if not variables:
        return text
    out = text
    for k, v in variables.items():
        out = out.replace(f"[[{k}]]", v)
    return out
