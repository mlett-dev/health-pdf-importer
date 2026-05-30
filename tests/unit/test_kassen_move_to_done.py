"""Tests for moving Kassen PDFs to done or error folder."""

import json
from pathlib import Path
from typing import Any, cast

from health_importer.graph.anytype_update_nodes import update_kassen_anytype
from health_importer.graph.file_nodes import rename_file_to_target
from health_importer.graph.nodes import (
    move_kassen_to_done,
    prepare_kassen_target_filename,
)
from health_importer.graph.state import GraphState


def _ef(value, confidence=0.95, evidence="test", page=1):
    """Build a realistic ExtractedField dict as produced by model_dump(mode='json')."""
    return {"value": value, "confidence": confidence, "evidence": evidence, "page": page}


def test_move_kassen_to_done_basic(tmp_path: Path) -> None:
    source = tmp_path / "processing" / "kasse.pdf"
    source.parent.mkdir()
    source.write_text("PDF content")
    done_dir = tmp_path / "done"

    state = cast(
        GraphState,
        {
            "file_path": str(source),
            "done_folder": str(done_dir),
            "events": [],
            "kassen_ruckmeldung_extraction": {
                "document_type": _ef("krankenkasse_antwort"),
                "patient_first_name": _ef("Max"),
                "doctor_name": _ef("Dr. Testarzt"),
                "bescheids_datum": _ef(None),
                "aufwendungsbetrag_eur": _ef(None),
                "erstattungsbetrag_eur": _ef("85.00"),
                "rechnungsnummer": _ef(None),
                "aktenzeichen": _ef(None),
                "betreffender_termin": _ef(None),
                "warnings": [],
                "missing_fields": [],
            },
            "allowed_patients": ["Max", "Anna"],
        },
    )
    result = move_kassen_to_done(state)

    assert result["status"] == "KASSEN_DONE"
    moved_path = Path(result["file_path"])
    assert moved_path.parent == done_dir
    assert moved_path.name == "kasse.pdf"
    assert moved_path.exists()
    assert not source.exists()


def test_prepare_kassen_target_filename_basic() -> None:
    state = cast(
        GraphState,
        {
            "events": [],
            "kassen_file_naming": {
                "enabled": True,
                "pattern": "{date}_{patient}_GKK_{topic}.pdf",
                "date_format": "%Y_%m_%d",
                "max_topic_length": 30,
            },
            "kassen_ruckmeldung_extraction": {
                "document_type": _ef("krankenkasse_antwort"),
                "patient_first_name": _ef("Max"),
                "doctor_name": _ef("Dr. Testarzt"),
                "bescheids_datum": _ef(None),
                "aufwendungsbetrag_eur": _ef(None),
                "erstattungsbetrag_eur": _ef("85.00"),
                "rechnungsnummer": _ef(None),
                "aktenzeichen": _ef(None),
                "betreffender_termin": _ef(None),
                "warnings": [],
                "missing_fields": [],
            },
            "allowed_patients": ["Max", "Anna"],
        },
    )
    result = prepare_kassen_target_filename(state)
    assert cast(Any, result).get("target_filename") == "unknown_date_Max_GKK_Dr._Testarzt.pdf"
    assert any(e["status"] == "FILENAME_PREPARED" for e in result["events"])


def test_prepare_kassen_target_filename_with_date() -> None:
    """Regression: date field must be extracted from nested ExtractedField dict."""
    state = cast(
        GraphState,
        {
            "events": [],
            "kassen_file_naming": {
                "enabled": True,
                "pattern": "{date}_{patient}_GKK_{topic}.pdf",
                "date_format": "%Y_%m_%d",
                "max_topic_length": 30,
            },
            "kassen_ruckmeldung_extraction": {
                "document_type": _ef("krankenkasse_antwort"),
                "patient_first_name": _ef("Anna"),
                "doctor_name": _ef("Dr. Testarzt F"),
                "bescheids_datum": _ef("2026-03-25"),
                "aufwendungsbetrag_eur": _ef(None),
                "erstattungsbetrag_eur": _ef("100.00"),
                "rechnungsnummer": _ef(None),
                "aktenzeichen": _ef(None),
                "betreffender_termin": _ef(None),
                "warnings": [],
                "missing_fields": [],
            },
            "allowed_patients": ["Max", "Anna"],
        },
    )
    result = prepare_kassen_target_filename(state)
    target_filename = cast(Any, result).get("target_filename")
    assert target_filename is not None
    assert "2026_03_25" in target_filename
    assert "Anna" in target_filename
    assert target_filename.endswith(".pdf")
    assert any(e["status"] == "FILENAME_PREPARED" for e in result["events"])


def test_prepare_kassen_target_filename_disabled() -> None:
    state = cast(
        GraphState,
        {
            "events": [],
            "kassen_file_naming": {
                "enabled": False,
                "pattern": "{date}_{patient}_GKK_{topic}.pdf",
                "date_format": "%Y_%m_%d",
                "max_topic_length": 30,
            },
            "kassen_ruckmeldung_extraction": {
                "document_type": _ef("krankenkasse_antwort"),
                "patient_first_name": _ef("Max"),
                "doctor_name": _ef("Dr. Testarzt"),
                "bescheids_datum": _ef(None),
                "aufwendungsbetrag_eur": _ef(None),
                "erstattungsbetrag_eur": _ef("85.00"),
                "rechnungsnummer": _ef(None),
                "aktenzeichen": _ef(None),
                "betreffender_termin": _ef(None),
                "warnings": [],
                "missing_fields": [],
            },
            "allowed_patients": ["Max", "Anna"],
        },
    )
    result = prepare_kassen_target_filename(state)
    assert result.get("target_filename") is None
    assert any(e["status"] == "FILENAME_SKIPPED" for e in result["events"])


def test_prepare_kassen_target_filename_respects_confidence_threshold() -> None:
    """Regression: prepare_kassen_target_filename must use state required_confidence_min."""
    state = cast(
        GraphState,
        {
            "events": [],
            "kassen_file_naming": {
                "enabled": True,
                "pattern": "{date}_{patient}_GKK_{topic}.pdf",
                "date_format": "%Y_%m_%d",
                "max_topic_length": 30,
            },
            "kassen_ruckmeldung_extraction": {
                "document_type": _ef("krankenkasse_antwort"),
                "patient_first_name": _ef("Max", confidence=0.85),
                "doctor_name": _ef("Dr. Testarzt"),
                "bescheids_datum": _ef(None),
                "aufwendungsbetrag_eur": _ef(None),
                "erstattungsbetrag_eur": _ef("85.00"),
                "rechnungsnummer": _ef(None),
                "aktenzeichen": _ef(None),
                "betreffender_termin": _ef(None),
                "warnings": [],
                "missing_fields": [],
            },
            "allowed_patients": ["Max", "Anna"],
            "required_confidence_min": 0.9,
        },
    )
    result = prepare_kassen_target_filename(state)
    # Because patient_first_name confidence (0.85) is below threshold (0.9),
    # validation should fail and filename preparation is skipped.
    assert result.get("target_filename") is None
    assert any(e["status"] == "FILENAME_SKIPPED" for e in result["events"])


def test_prepare_kassen_target_filename_uses_selected_match_topic() -> None:
    """When selected_match is present, its name should be used as the topic placeholder."""
    state = cast(
        GraphState,
        {
            "events": [],
            "kassen_file_naming": {
                "enabled": True,
                "pattern": "{date}_{patient}_GKK_{topic}.pdf",
                "date_format": "%Y_%m_%d",
                "max_topic_length": 60,
            },
            "kassen_ruckmeldung_extraction": {
                "document_type": _ef("krankenkasse_antwort"),
                "patient_first_name": _ef("Max"),
                "doctor_name": _ef("Dr. Testarzt"),
                "bescheids_datum": _ef("2024-03-15"),
                "aufwendungsbetrag_eur": _ef(None),
                "erstattungsbetrag_eur": _ef("85.00"),
                "rechnungsnummer": _ef(None),
                "aktenzeichen": _ef(None),
                "betreffender_termin": _ef(None),
                "warnings": [],
                "missing_fields": [],
            },
            "allowed_patients": ["Max", "Anna"],
            "selected_match": {
                "object_id": "TEST_OBJECT_ID",
                "name": "Kontrolle von Wachstum und Gewicht",
                "score": 0.95,
                "invoice_file_id": 42,
                "properties": {},
            },
        },
    )
    result = prepare_kassen_target_filename(state)
    assert (
        cast(Any, result).get("target_filename")
        == "2024_03_15_Max_GKK_Kontrolle_von_Wachstum_und_Gewicht.pdf"
    )
    assert any(e["status"] == "FILENAME_PREPARED" for e in result["events"])


def test_rename_file_to_target_uses_state_target_filename(tmp_path: Path) -> None:
    """rename_file_to_target must also read state['target_filename']."""
    source = tmp_path / "processing" / "kasse.pdf"
    source.parent.mkdir()
    source.write_text("PDF content")

    state = cast(
        GraphState,
        {
            "file_path": str(source),
            "events": [],
            "target_filename": "2026_03_25_Anna_GKK_Dr._Testarzt_F.pdf",
        },
    )
    result = rename_file_to_target(state)
    assert result["file_path"].endswith("2026_03_25_Anna_GKK_Dr._Testarzt_F.pdf")
    assert result.get("target_filename") is None  # cleared to prevent double rename
    assert any(e["status"] == "RENAMED" for e in result["events"])


def test_move_kassen_to_error_on_failed_status(tmp_path: Path) -> None:
    """When ok=False or status is KASSEN_UPDATE_FAILED, move to error folder."""
    source = tmp_path / "processing" / "kasse.pdf"
    source.parent.mkdir()
    source.write_text("PDF content")
    done_dir = tmp_path / "done"
    error_dir = tmp_path / "error"

    state = cast(
        GraphState,
        {
            "file_path": str(source),
            "done_folder": str(done_dir),
            "error_folder": str(error_dir),
            "events": [],
            "ok": False,
            "status": "KASSEN_UPDATE_FAILED",
            "kassen_ruckmeldung_extraction": {
                "document_type": _ef("krankenkasse_antwort"),
                "patient_first_name": _ef("Max"),
                "doctor_name": _ef("Dr. Testarzt"),
                "bescheids_datum": _ef(None),
                "aufwendungsbetrag_eur": _ef(None),
                "erstattungsbetrag_eur": _ef("85.00"),
                "rechnungsnummer": _ef(None),
                "aktenzeichen": _ef(None),
                "betreffender_termin": _ef(None),
                "warnings": [],
                "missing_fields": [],
            },
            "allowed_patients": ["Max", "Anna"],
        },
    )
    result = move_kassen_to_done(state)

    assert result["status"] == "KASSEN_ERROR"
    moved_path = Path(result["file_path"])
    assert moved_path.parent == error_dir
    assert moved_path.name == "kasse.pdf"
    assert moved_path.exists()
    assert not source.exists()

    sidecar_path = moved_path.with_suffix(".import.json")
    assert sidecar_path.exists()
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["document_type"] == "krankenkasse_antwort"
    assert sidecar["status"] == "KASSEN_UPDATE_FAILED"
    assert sidecar["suggested_action"] == "inspect_error"
    assert sidecar["extraction"]["patient_first_name"]["value"] == "Max"


def test_update_kassen_anytype_skips_after_upload_failure() -> None:
    state = cast(
        GraphState,
        {
            "events": [],
            "ok": False,
            "status": "KASSEN_UPLOAD_FAILED",
            "selected_match": {"object_id": "obj-1"},
            "kassen_ruckmeldung_extraction": {"erstattungsbetrag_eur": {"value": "10.00"}},
        },
    )

    result = update_kassen_anytype(state)

    assert result["status"] == "KASSEN_UPLOAD_FAILED"
    assert any(event["status"] == "KASSEN_UPDATE_SKIPPED" for event in result["events"])
