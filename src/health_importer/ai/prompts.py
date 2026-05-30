from __future__ import annotations

from pathlib import Path


DEFAULT_PROMPT_DIR = Path("config/prompts")


def load_prompt(name: str, *, prompt_dir: Path = DEFAULT_PROMPT_DIR) -> str:
    path = prompt_dir / name
    return path.read_text(encoding="utf-8")


def page_text_for_prompt(pdf_text: dict) -> str:
    pages = pdf_text.get("pages", [])
    blocks = []
    for page in pages:
        blocks.append(f"[Seite {page.get('page_number')}]\n{page.get('text', '')}")
    return "\n\n".join(blocks)


def vision_prompt_for_page(page_number: int) -> str:
    return load_prompt("extract_invoice_vision.md").replace('"page_number": 1', f'"page_number": {page_number}')
