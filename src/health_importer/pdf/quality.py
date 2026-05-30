from __future__ import annotations

import re
from dataclasses import asdict, dataclass


TYPICAL_TERMS = (
    "rechnung",
    "honorarnote",
    "betrag",
    "summe",
    "patient",
    "ordination",
    "€",
    "eur",
)


@dataclass(frozen=True)
class TextQuality:
    score: float
    route: str
    total_chars: int
    readable_ratio: float
    matched_terms: list[str]
    date_count: int
    amount_count: int
    reasons: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_text_quality(text: str, *, min_text_chars: int = 500) -> TextQuality:
    total_chars = len(text.strip())
    readable_ratio = _readable_ratio(text)
    matched_terms = _matched_terms(text)
    date_count = len(_DATE_RE.findall(text))
    amount_count = len(_find_amounts(text))

    length_score = min(total_chars / min_text_chars, 1.0) if min_text_chars > 0 else 1.0
    readable_score = readable_ratio
    term_score = min(len(matched_terms) / 3, 1.0)
    date_score = 1.0 if date_count else 0.0
    amount_score = 1.0 if amount_count else 0.0

    score = round(
        (length_score * 0.35)
        + (readable_score * 0.25)
        + (term_score * 0.20)
        + (date_score * 0.10)
        + (amount_score * 0.10),
        3,
    )
    reasons = _reasons(total_chars, min_text_chars, readable_ratio, matched_terms, date_count, amount_count)
    return TextQuality(
        score=score,
        route="llm_text_extraction" if score >= 0.65 else "ocr",
        total_chars=total_chars,
        readable_ratio=round(readable_ratio, 3),
        matched_terms=matched_terms,
        date_count=date_count,
        amount_count=amount_count,
        reasons=reasons,
    )


def join_page_text(pdf_text: dict) -> str:
    pages = pdf_text.get("pages", [])
    return "\n\n".join(str(page.get("text", "")) for page in pages)


def _readable_ratio(text: str) -> float:
    stripped = text.strip()
    if not stripped:
        return 0.0
    readable = sum(1 for char in stripped if char.isalnum() or char.isspace() or char in ".,;:-_/()€$")
    return readable / len(stripped)


def _matched_terms(text: str) -> list[str]:
    lowered = text.casefold()
    return [term for term in TYPICAL_TERMS if term in lowered]


def _reasons(
    total_chars: int,
    min_text_chars: int,
    readable_ratio: float,
    matched_terms: list[str],
    date_count: int,
    amount_count: int,
) -> list[str]:
    reasons: list[str] = []
    if total_chars < min_text_chars:
        reasons.append("below_min_text_chars")
    if readable_ratio < 0.85:
        reasons.append("low_readable_ratio")
    if not matched_terms:
        reasons.append("missing_invoice_terms")
    if date_count == 0:
        reasons.append("missing_date")
    if amount_count == 0:
        reasons.append("missing_amount")
    if not reasons:
        reasons.append("text_quality_ok")
    return reasons


_DATE_RE = re.compile(r"\b(?:\d{1,2}[.]\d{1,2}[.]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
_CURRENCY_AMOUNT_RE = re.compile(
    r"(?:€|EUR)\s*\b\d{1,5}(?:[.,]\d{2})?\b|\b\d{1,5}(?:[.,]\d{2})?\s*(?:€|EUR)\b",
    re.IGNORECASE,
)
_DECIMAL_AMOUNT_RE = re.compile(r"\b\d{1,5}[,.]\d{2}\b(?![.]\d)")


def _find_amounts(text: str) -> list[str]:
    spans: set[tuple[int, int]] = set()
    amounts: list[str] = []
    for regex in (_CURRENCY_AMOUNT_RE, _DECIMAL_AMOUNT_RE):
        for match in regex.finditer(text):
            if match.span() in spans:
                continue
            spans.add(match.span())
            amounts.append(match.group(0))
    return amounts
