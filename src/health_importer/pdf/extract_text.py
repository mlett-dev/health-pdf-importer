from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

import fitz


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str
    char_count: int


@dataclass(frozen=True)
class PdfTextExtraction:
    method: str
    page_count: int
    total_chars: int
    pages: list[PageText]

    @property
    def is_empty(self) -> bool:
        return self.total_chars == 0

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "page_count": self.page_count,
            "total_chars": self.total_chars,
            "pages": [asdict(page) for page in self.pages],
            "is_empty": self.is_empty,
        }


def extract_embedded_text(path: Path) -> PdfTextExtraction:
    pages: list[PageText] = []
    with fitz.open(path) as document:
        for index, page in enumerate(document.pages(), start=1):
            text = normalize_pdf_text(page.get_text("text"))
            pages.append(PageText(page_number=index, text=text, char_count=len(text)))

    return PdfTextExtraction(
        method="embedded_text",
        page_count=len(pages),
        total_chars=sum(page.char_count for page in pages),
        pages=pages,
    )


def normalize_pdf_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_SPACE_RE.sub(" ", line).strip() for line in normalized.split("\n")]

    collapsed_lines: list[str] = []
    previous_blank = False
    for line in lines:
        is_blank = not line
        if is_blank and previous_blank:
            continue
        collapsed_lines.append(line)
        previous_blank = is_blank
    return "\n".join(collapsed_lines).strip()


_SPACE_RE = re.compile(r"[ \t\f\v]+")
