"""Tests for Pkv-Antwort review stub routing."""

import json
from pathlib import Path
from typing import Any, cast

from health_importer.ai.schemas import DocumentType, DocumentTypeField
from health_importer.graph.classification_nodes import route_by_document_type
from health_importer.graph.nodes import (
    mark_pkv_review,
    prepare_pkv_target_filename,
)
from health_importer.graph.state import GraphState


def test_route_by_document_type_pkv() -> None:
    state = cast(
        GraphState,
        {
            "events": [],
            "invoice_extraction": {
                "document_type": {"value": "pkv_antwort", "confidence": 0.95},
                "patient_first_name": {"value": "Max", "confidence": 0.9},
                "doctor_name": {"value": None, "confidence": 0.0},
                "appointment_date": {"value": None, "confidence": 0.0},
                "topic": {"value": None, "confidence": 0.0},
                "total_amount_eur": {"value": None, "confidence": 0.0},
            },
        },
    )
    result = route_by_document_type(state)
    assert cast(Any, result).get("next_route") == "pkv_flow"
    assert result["events"][-1]["status"] == "PKV_FLOW"


def test_mark_pkv_review_moves_to_review(tmp_path: Path) -> None:
    source = tmp_path / "inbox" / "pkv.pdf"
    source.parent.mkdir()
    source.write_text("PDF content")
    review_dir = tmp_path / "review"

    state = cast(
        GraphState,
        {
            "file_path": str(source),
            "file_name": "pkv.pdf",
            "sha256": "abc123",
            "review_folder": str(review_dir),
            "events": [],
        },
    )
    result = mark_pkv_review(state)

    assert result["status"] == "PKV_REVIEW"
    moved_path = Path(result["file_path"])
    assert moved_path.parent == review_dir
    assert moved_path.name == "pkv.pdf"
    assert moved_path.exists()
    assert not source.exists()

    # Sidecar should exist
    sidecar = moved_path.with_suffix(".import.json")
    assert sidecar.exists()
    data = json.loads(sidecar.read_text())
    assert data["document_type"] == "pkv_antwort"
    assert data["suggested_action"] == "inspect_match_or_extraction"


def test_pkv_antwort_extraction_schema() -> None:
    from health_importer.ai.schemas import ExtractedField, PkvAntwortExtraction

    extraction = PkvAntwortExtraction(
        document_type=DocumentTypeField(
            value=DocumentType.PKV_ANTWORT, confidence=0.95, evidence="test"
        ),
        patient_first_name=ExtractedField(value="Max", confidence=0.9, evidence="test"),
        erstattungsbetrag_eur=ExtractedField(value="120.00", confidence=0.8, evidence="test"),
        bescheids_datum=ExtractedField(value="2024-03-15", confidence=0.7, evidence="test"),
    )
    assert extraction.patient_first_name.value == "Max"
    assert extraction.erstattungsbetrag_eur.value == "120.00"
    assert extraction.workflow_required_missing_fields() == []


def test_pkv_antwort_extraction_missing_erstattungsbetrag() -> None:
    """Missing erstattungsbetrag_eur should be flagged as required."""
    from health_importer.ai.schemas import ExtractedField, PkvAntwortExtraction

    extraction = PkvAntwortExtraction(
        document_type=DocumentTypeField(
            value=DocumentType.PKV_ANTWORT, confidence=0.95, evidence="test"
        ),
        patient_first_name=ExtractedField(value="Max", confidence=0.9, evidence="test"),
        erstattungsbetrag_eur=ExtractedField(value=None, confidence=0.0),
    )
    assert extraction.workflow_required_missing_fields() == ["erstattungsbetrag_eur"]
    assert not extraction.is_ready_for_code_validation()


def test_pkv_antwort_extraction_missing_both_required() -> None:
    """Missing both patient and erstattungsbetrag should list both."""
    from health_importer.ai.schemas import ExtractedField, PkvAntwortExtraction

    extraction = PkvAntwortExtraction(
        document_type=DocumentTypeField(
            value=DocumentType.PKV_ANTWORT, confidence=0.95, evidence="test"
        ),
        patient_first_name=ExtractedField(value=None, confidence=0.0),
        erstattungsbetrag_eur=ExtractedField(value=None, confidence=0.0),
    )
    assert extraction.workflow_required_missing_fields() == [
        "patient_first_name",
        "erstattungsbetrag_eur",
    ]


def test_prepare_pkv_target_filename_basic() -> None:
    state = cast(
        GraphState,
        {
            "events": [],
            "allowed_patients": ["Max", "Anna"],
            "required_confidence_min": 0.8,
            "pkv_file_naming": {
                "enabled": True,
                "pattern": "{date}_{patient}_PKV.pdf",
                "date_format": "%Y_%m_%d",
                "max_topic_length": 40,
            },
            "pkv_antwort_extraction": {
                "document_type": {"value": "pkv_antwort", "confidence": 0.9, "evidence": "test"},
                "patient_first_name": {"value": "Max", "confidence": 0.9, "evidence": "test"},
                "doctor_name": {"value": None, "confidence": 0.0},
                "erstattungsbetrag_eur": {"value": 100.0, "confidence": 0.9, "evidence": "test"},
                "bescheids_datum": {"value": "2026-04-12", "confidence": 0.9, "evidence": "test"},
                "aufwendungsbetrag_eur": {"value": None, "confidence": 0.0},
                "rechnungsnummer": {"value": None, "confidence": 0.0},
                "betreffender_termin": {"value": None, "confidence": 0.0},
                "warnings": [],
                "missing_fields": [],
            },
        },
    )
    result = prepare_pkv_target_filename(state)
    target_filename = result.get("target_filename")
    assert target_filename is not None
    assert target_filename == "2026_04_12_Max_PKV.pdf"
    assert any(e["status"] == "FILENAME_PREPARED" for e in result["events"])


def test_prepare_pkv_target_filename_fallback_to_invoice_date() -> None:
    state = cast(
        GraphState,
        {
            "events": [],
            "allowed_patients": ["Anna", "Max"],
            "required_confidence_min": 0.8,
            "pkv_file_naming": {
                "enabled": True,
                "pattern": "{date}_{patient}_PKV.pdf",
                "date_format": "%Y_%m_%d",
                "max_topic_length": 40,
            },
            "pkv_antwort_extraction": {
                "document_type": {"value": "pkv_antwort", "confidence": 0.9, "evidence": "test"},
                "patient_first_name": {"value": "Anna", "confidence": 0.9, "evidence": "test"},
                "doctor_name": {"value": None, "confidence": 0.0},
                "erstattungsbetrag_eur": {"value": 85.0, "confidence": 0.9, "evidence": "test"},
                "bescheids_datum": {"value": None, "confidence": 0.0},
                "aufwendungsbetrag_eur": {"value": None, "confidence": 0.0},
                "rechnungsnummer": {"value": None, "confidence": 0.0},
                "betreffender_termin": {
                    "value": "2026-05-01",
                    "confidence": 0.9,
                    "evidence": "test",
                },
                "warnings": [],
                "missing_fields": [],
            },
        },
    )
    result = prepare_pkv_target_filename(state)
    target_filename = result.get("target_filename")
    assert target_filename is not None
    assert target_filename == "2026_05_01_Anna_PKV.pdf"


def test_prepare_pkv_target_filename_unknown_date() -> None:
    state = cast(
        GraphState,
        {
            "events": [],
            "allowed_patients": ["Max", "Max"],
            "required_confidence_min": 0.8,
            "pkv_file_naming": {
                "enabled": True,
                "pattern": "{date}_{patient}_PKV.pdf",
                "date_format": "%Y_%m_%d",
                "max_topic_length": 40,
            },
            "pkv_antwort_extraction": {
                "document_type": {"value": "pkv_antwort", "confidence": 0.9, "evidence": "test"},
                "patient_first_name": {"value": "Max", "confidence": 0.9, "evidence": "test"},
                "doctor_name": {"value": None, "confidence": 0.0},
                "erstattungsbetrag_eur": {"value": 50.0, "confidence": 0.9, "evidence": "test"},
                "bescheids_datum": {"value": None, "confidence": 0.0},
                "aufwendungsbetrag_eur": {"value": None, "confidence": 0.0},
                "rechnungsnummer": {"value": None, "confidence": 0.0},
                "betreffender_termin": {"value": None, "confidence": 0.0},
                "warnings": [],
                "missing_fields": [],
            },
        },
    )
    result = prepare_pkv_target_filename(state)
    target_filename = result.get("target_filename")
    assert target_filename is not None
    assert target_filename == "unknown_date_Max_PKV.pdf"


def test_prepare_pkv_target_filename_no_patient() -> None:
    state = cast(
        GraphState,
        {
            "events": [],
            "allowed_patients": ["Max"],
            "required_confidence_min": 0.8,
            "pkv_file_naming": {
                "enabled": True,
                "pattern": "{date}_{patient}_PKV.pdf",
                "date_format": "%Y_%m_%d",
                "max_topic_length": 40,
            },
            "pkv_antwort_extraction": {
                "document_type": {"value": "pkv_antwort", "confidence": 0.9, "evidence": "test"},
                "patient_first_name": {"value": None, "confidence": 0.0},
                "doctor_name": {"value": None, "confidence": 0.0},
                "erstattungsbetrag_eur": {"value": 100.0, "confidence": 0.9, "evidence": "test"},
                "bescheids_datum": {"value": None, "confidence": 0.0},
                "aufwendungsbetrag_eur": {"value": None, "confidence": 0.0},
                "rechnungsnummer": {"value": None, "confidence": 0.0},
                "betreffender_termin": {"value": None, "confidence": 0.0},
                "warnings": [],
                "missing_fields": [],
            },
        },
    )
    result = prepare_pkv_target_filename(state)
    assert result.get("target_filename") is None
    assert any(e["status"] == "FILENAME_SKIPPED" for e in result["events"])
