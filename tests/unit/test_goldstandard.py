from pathlib import Path

import pytest

from health_importer.workflow.goldstandard import (
    compare_extraction_result,
    load_goldstandard_cases,
    run_goldstandard_evaluation,
)


def test_load_goldstandard_cases_matches_expected_json_to_pdf(tmp_path: Path) -> None:
    pdf_dir = tmp_path / "pdfs"
    expected_dir = tmp_path / "expected_json"
    pdf_dir.mkdir()
    expected_dir.mkdir()
    (pdf_dir / "invoice.pdf").write_bytes(b"%PDF-1.4\n")
    (expected_dir / "invoice.json").write_text("{}", encoding="utf-8")

    cases = load_goldstandard_cases(pdf_dir, expected_dir)

    assert len(cases) == 1
    assert cases[0].pdf_path == pdf_dir / "invoice.pdf"
    assert cases[0].expected_path == expected_dir / "invoice.json"


def test_load_goldstandard_cases_rejects_missing_pdf(tmp_path: Path) -> None:
    pdf_dir = tmp_path / "pdfs"
    expected_dir = tmp_path / "expected_json"
    pdf_dir.mkdir()
    expected_dir.mkdir()
    (expected_dir / "invoice.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Missing PDF fixture"):
        load_goldstandard_cases(pdf_dir, expected_dir)


def test_compare_extraction_result_reports_field_matches() -> None:
    result = {
        "ok": True,
        "invoice_extraction": {
            "patient_first_name": {"value": "Max"},
            "doctor_name": {"value": "Dr. Testarzt Example"},
            "appointment_date": {"value": "2026-05-10"},
            "topic": {"value": "Kontrolle"},
            "total_amount_eur": {"value": 120.0},
        },
    }

    comparisons = compare_extraction_result(
        result,
        {
            "patient_first_name": "max",
            "doctor_name": "Dr. Testarzt Example",
            "appointment_date": "2026-05-10",
            "topic": "Kontrolle",
            "total_amount_eur": "120.00",
        },
    )

    assert all(comparison.matched for comparison in comparisons)


def test_run_goldstandard_evaluation_returns_accuracy_report(tmp_path: Path) -> None:
    pdf_dir = tmp_path / "pdfs"
    expected_dir = tmp_path / "expected_json"
    pdf_dir.mkdir()
    expected_dir.mkdir()
    (pdf_dir / "invoice.pdf").write_bytes(b"%PDF-1.4\n")
    (expected_dir / "invoice.json").write_text(
        """
{
  "patient": "Max",
  "arzt": "Dr. Testarzt Example",
  "termin": "2026-05-10",
  "thema": "Kontrolle",
  "betrag": 120
}
""",
        encoding="utf-8",
    )

    report = run_goldstandard_evaluation(pdf_dir, expected_dir, _fake_run_pdf)

    assert report["ok"] is True
    assert report["case_count"] == 1
    assert report["correct_fields"] == 5
    assert report["total_fields"] == 5
    assert report["field_accuracy"] == 1.0


def _fake_run_pdf(path: Path) -> dict:
    return {
        "ok": True,
        "file_path": str(path),
        "invoice_extraction": {
            "patient_first_name": {"value": "Max"},
            "doctor_name": {"value": "Dr. Testarzt Example"},
            "appointment_date": {"value": "2026-05-10"},
            "topic": {"value": "Kontrolle"},
            "total_amount_eur": {"value": 120.0},
        },
    }
