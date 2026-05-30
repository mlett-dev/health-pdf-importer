from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

GOLDSTANDARD_FIELDS = (
    "patient_first_name",
    "doctor_name",
    "appointment_date",
    "topic",
    "total_amount_eur",
)

EXPECTED_FIELD_ALIASES = {
    "patient": "patient_first_name",
    "arzt": "doctor_name",
    "termin": "appointment_date",
    "thema": "topic",
    "betrag": "total_amount_eur",
}


@dataclass(frozen=True)
class FieldComparison:
    field: str
    expected: Any
    actual: Any
    matched: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
            "matched": self.matched,
            "message": self.message,
        }


@dataclass(frozen=True)
class GoldstandardCase:
    pdf_path: Path
    expected_path: Path


def load_goldstandard_cases(pdf_dir: Path, expected_dir: Path) -> list[GoldstandardCase]:
    if not pdf_dir.exists():
        raise FileNotFoundError(f"PDF fixture directory does not exist: {pdf_dir}")
    if not expected_dir.exists():
        raise FileNotFoundError(f"Expected JSON directory does not exist: {expected_dir}")

    cases: list[GoldstandardCase] = []
    for expected_path in sorted(expected_dir.glob("*.json")):
        pdf_path = pdf_dir / f"{expected_path.stem}.pdf"
        if not pdf_path.exists():
            raise FileNotFoundError(f"Missing PDF fixture for {expected_path.name}: {pdf_path}")
        cases.append(GoldstandardCase(pdf_path=pdf_path, expected_path=expected_path))
    if not cases:
        raise ValueError(f"No expected JSON files found in {expected_dir}")
    return cases


def run_goldstandard_evaluation(
    pdf_dir: Path,
    expected_dir: Path,
    run_pdf: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    cases = load_goldstandard_cases(pdf_dir, expected_dir)
    results = []
    correct = 0
    total = 0

    for case in cases:
        expected = load_expected_json(case.expected_path)
        result = run_pdf(case.pdf_path)
        comparisons = compare_extraction_result(result, expected)
        correct += sum(1 for comparison in comparisons if comparison.matched)
        total += len(comparisons)
        results.append(
            {
                "pdf_path": str(case.pdf_path),
                "expected_path": str(case.expected_path),
                "ok": bool(result.get("ok")),
                "status": result.get("status"),
                "correct_fields": sum(1 for comparison in comparisons if comparison.matched),
                "total_fields": len(comparisons),
                "field_accuracy": _ratio(
                    sum(1 for comparison in comparisons if comparison.matched),
                    len(comparisons),
                ),
                "fields": [comparison.to_dict() for comparison in comparisons],
            }
        )

    return {
        "ok": True,
        "case_count": len(results),
        "correct_fields": correct,
        "total_fields": total,
        "field_accuracy": _ratio(correct, total),
        "results": results,
    }


def load_expected_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON must be an object: {path}")
    normalized: dict[str, Any] = {}
    for raw_key, value in data.items():
        key = str(raw_key)
        normalized[EXPECTED_FIELD_ALIASES.get(key, key)] = value
    return normalized


def compare_extraction_result(
    result: dict[str, Any],
    expected: dict[str, Any],
) -> list[FieldComparison]:
    extraction = result.get("invoice_extraction") if result.get("ok") else None
    if not isinstance(extraction, dict):
        extraction = {}

    comparisons: list[FieldComparison] = []
    for field in GOLDSTANDARD_FIELDS:
        expected_value = expected.get(field)
        actual_value = _actual_field_value(extraction, field)
        matched = values_match(field, expected_value, actual_value)
        comparisons.append(
            FieldComparison(
                field=field,
                expected=expected_value,
                actual=actual_value,
                matched=matched,
                message="ok" if matched else "value_mismatch",
            )
        )
    return comparisons


def values_match(field: str, expected: Any, actual: Any) -> bool:
    if expected is None:
        return actual is None
    if actual is None:
        return False
    if field == "total_amount_eur":
        return _decimal_value(expected) == _decimal_value(actual)
    return _normalize_text(expected) == _normalize_text(actual)


def _actual_field_value(extraction: dict[str, Any], field: str) -> Any:
    raw = extraction.get(field)
    if isinstance(raw, dict):
        return raw.get("value")
    return raw


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def _decimal_value(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _ratio(correct: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(correct / total, 4)
