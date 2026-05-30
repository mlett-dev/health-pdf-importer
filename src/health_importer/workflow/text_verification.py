from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from dateutil import parser


@dataclass(frozen=True)
class TextVerificationResult:
    amount_found: bool
    date_found: bool
    amount_candidates: list[Decimal] = field(default_factory=list)
    date_candidates: list[date] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.warnings)


def verify_amount_and_date_in_text(
    text: str,
    *,
    amount: Decimal,
    target_date: date,
) -> TextVerificationResult:
    amount_candidates = extract_euro_amounts(text)
    date_candidates = extract_dates(text)
    amount_found = any(candidate == amount for candidate in amount_candidates)
    date_found = target_date in date_candidates

    warnings = []
    if not amount_found:
        warnings.append("amount_not_found_in_text")
    if len(set(amount_candidates)) > 1:
        warnings.append("multiple_amounts_found")
    if not date_found:
        warnings.append("date_not_found_in_text")

    return TextVerificationResult(
        amount_found=amount_found,
        date_found=date_found,
        amount_candidates=amount_candidates,
        date_candidates=date_candidates,
        warnings=warnings,
    )


def extract_euro_amounts(text: str) -> list[Decimal]:
    amounts: list[Decimal] = []
    seen: set[Decimal] = set()
    date_spans = [match.span() for match in _DATE_RE.finditer(text)]
    for match in _AMOUNT_RE.finditer(text):
        if any(_spans_overlap(match.span(), date_span) for date_span in date_spans):
            continue
        raw_amount = match.group("prefixed_amount") or match.group("amount")
        normalized = _normalize_amount(raw_amount)
        if normalized not in seen:
            amounts.append(normalized)
            seen.add(normalized)
    return amounts


def extract_dates(text: str) -> list[date]:
    dates: list[date] = []
    seen: set[date] = set()
    for match in _DATE_RE.finditer(text):
        raw_date = match.group(0)
        try:
            if "-" in raw_date:
                parsed = date.fromisoformat(raw_date)
            else:
                parsed = parser.parse(raw_date, dayfirst=True).date()
        except (ValueError, OverflowError):
            continue
        if parsed not in seen:
            dates.append(parsed)
            seen.add(parsed)
    return dates


def _normalize_amount(raw: str) -> Decimal:
    value = raw.strip().replace(" ", "")
    if value.endswith(".-"):
        value = value[:-2]
    value = value.replace(".", "").replace(",", ".")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid amount: {raw}") from exc


def _spans_overlap(first: tuple[int, int], second: tuple[int, int]) -> bool:
    return first[0] < second[1] and second[0] < first[1]


_AMOUNT_RE = re.compile(
    r"(?:(?:EUR|€)\s*(?P<prefixed_amount>\d{1,5}(?:[.]\d{3})*(?:,\d{2})?|\d{1,5}[.]-)"
    r"|(?P<amount>\d{1,5}(?:[.]\d{3})*(?:,\d{2})|\d{1,5}[.]-)\s*(?:EUR|€)?)",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\b(?:\d{1,2}[.]\d{1,2}[.]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
