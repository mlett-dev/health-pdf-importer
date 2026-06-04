from __future__ import annotations

from pathlib import Path


DEFAULT_PROMPT_DIR = Path("config/prompts")
DEFAULT_PKV_INSURER_NAMES = ("Uniqua", "Donau", "Merkur")


def load_prompt(name: str, *, prompt_dir: Path = DEFAULT_PROMPT_DIR) -> str:
    path = prompt_dir / name
    return path.read_text(encoding="utf-8")


def load_invoice_prompt(
    name: str,
    *,
    prompt_dir: Path = DEFAULT_PROMPT_DIR,
    pkv_insurer_names: tuple[str, ...] = DEFAULT_PKV_INSURER_NAMES,
) -> str:
    prompt = load_prompt(name, prompt_dir=prompt_dir)
    return prompt.replace("{{pkv_insurer_names}}", ", ".join(pkv_insurer_names))


def page_text_for_prompt(pdf_text: dict) -> str:
    pages = pdf_text.get("pages", [])
    blocks = []
    for page in pages:
        blocks.append(f"[Seite {page.get('page_number')}]\n{page.get('text', '')}")
    return "\n\n".join(blocks)


def vision_prompt_for_page(
    page_number: int,
    *,
    pkv_insurer_names: tuple[str, ...] = DEFAULT_PKV_INSURER_NAMES,
) -> str:
    return load_invoice_prompt(
        "extract_invoice_vision.md", pkv_insurer_names=pkv_insurer_names
    ).replace('"page_number": 1', f'"page_number": {page_number}')
