"""Tests for create_pkv_draft node."""

from pathlib import Path
from typing import cast
from unittest.mock import patch

from health_importer.graph.nodes import create_pkv_draft
from health_importer.graph.state import GraphState


def _ef(value):
    return {"value": value, "confidence": 0.95, "evidence": "test", "page": 1}


def test_create_pkv_draft_file_only_provider(tmp_path: Path) -> None:
    """Regression: create_pkv_draft uses FileOnlyProvider when email disabled."""
    pdf = tmp_path / "processing" / "kasse.pdf"
    pdf.parent.mkdir()
    pdf.write_text("PDF")
    review_dir = tmp_path / "review"

    state = cast(
        GraphState,
        {
            "file_path": str(pdf),
            "ok": True,
            "status": "KASSEN_UPDATED",
            "kassen_ruckmeldung_extraction": {
                "patient_first_name": _ef("Anna"),
                "doctor_name": _ef("Dr. Testarzt F"),
                "bescheids_datum": _ef("2026-03-25"),
                "erstattungsbetrag_eur": _ef("100.00"),
                "rechnungsnummer": _ef(None),
                "aktenzeichen": _ef(None),
                "betreffender_termin": _ef(None),
            },
            "selected_match": {"name": "Invoice 1"},
            "review_folder": str(review_dir),
            "email_config": {"enabled": False},
            "events": [],
        },
    )

    result = create_pkv_draft(state)
    assert result["status"] == "KASSEN_EMAIL_DRAFT_CREATED"
    assert "pkv_draft_path" in result


def test_create_pkv_draft_skips_on_previous_failure() -> None:
    """Regression: create_pkv_draft skips when previous Kassen update failed."""
    state = cast(
        GraphState,
        {
            "ok": False,
            "status": "KASSEN_UPDATE_FAILED",
            "events": [],
        },
    )
    result = create_pkv_draft(state)
    assert result["status"] == "KASSEN_EMAIL_SKIPPED"


def test_create_pkv_draft_with_email_enabled(tmp_path: Path) -> None:
    """Regression: create_pkv_draft builds provider and creates draft."""
    pdf = tmp_path / "processing" / "kasse.pdf"
    pdf.parent.mkdir()
    pdf.write_text("PDF")

    state = cast(
        GraphState,
        {
            "file_path": str(pdf),
            "ok": True,
            "status": "KASSEN_UPDATED",
            "kassen_ruckmeldung_extraction": {
                "patient_first_name": _ef("Anna"),
                "doctor_name": _ef("Dr. Testarzt F"),
                "bescheids_datum": _ef("2026-03-25"),
                "erstattungsbetrag_eur": _ef("100.00"),
                "rechnungsnummer": _ef(None),
                "aktenzeichen": _ef(None),
                "betreffender_termin": _ef(None),
            },
            "selected_match": {"name": "Invoice 1"},
            "review_folder": str(tmp_path / "review"),
            "email_config": {
                "enabled": True,
                "provider": "file_only",
            },
            "events": [],
        },
    )

    with patch("health_importer.email.build_provider") as mock_build:
        mock_provider = mock_build.return_value
        mock_provider.create_draft.return_value = "draft://test"
        result = create_pkv_draft(state)

    assert result["status"] == "KASSEN_EMAIL_DRAFT_CREATED"
    assert result.get("pkv_draft_path") == "draft://test"


def test_create_pkv_draft_custom_body_template(tmp_path: Path) -> None:
    """Custom body template with sender placeholders is rendered into the draft."""
    pdf = tmp_path / "processing" / "kasse.pdf"
    pdf.parent.mkdir()
    pdf.write_text("PDF")
    review_dir = tmp_path / "review"

    state = cast(
        GraphState,
        {
            "file_path": str(pdf),
            "ok": True,
            "status": "KASSEN_UPDATED",
            "kassen_ruckmeldung_extraction": {
                "patient_first_name": _ef("Anna"),
                "doctor_name": _ef("Dr. Testarzt F"),
                "bescheids_datum": _ef("2026-03-25"),
                "erstattungsbetrag_eur": _ef("100.00"),
                "rechnungsnummer": _ef(None),
                "aktenzeichen": _ef(None),
                "betreffender_termin": _ef(None),
            },
            "selected_match": {"name": "Invoice 1"},
            "review_folder": str(review_dir),
            "email_config": {
                "enabled": False,
                "pkv_body_template": (
                    "Sehr geehrtes Pkv Team,\n\n"
                    "ich ersuche um Rueckerstattung.\n\n"
                    "{details}\n\n"
                    "Mit freundlichen Gruessen,\n"
                    "{sender_name}\n"
                    "Polizzennummer: {sender_policy_number}\n"
                ),
                "pkv_sender_name": "Max Mustermann",
                "pkv_sender_policy_number": "2015123456KV",
            },
            "events": [],
        },
    )

    result = create_pkv_draft(state)
    assert result["status"] == "KASSEN_EMAIL_DRAFT_CREATED"
    draft_path_value = result.get("pkv_draft_path")
    assert draft_path_value is not None
    draft_path = Path(draft_path_value)
    assert draft_path.exists()
    content = draft_path.read_text(encoding="utf-8")
    assert "Sehr geehrtes Pkv Team," in content
    assert "Max Mustermann" in content
    assert "Polizzennummer: 2015123456KV" in content
    assert "100,00 €" in content
