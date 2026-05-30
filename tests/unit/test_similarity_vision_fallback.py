from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from health_importer.ai.schemas import (
    DocumentType,
    DocumentTypeField,
    ExtractedField,
    InvoiceExtraction,
    VisionPageExtraction,
)
from health_importer.graph.invoice_nodes import extract_structured_invoice
from health_importer.graph.state import GraphState


def _text_extraction_with_patient_as_doctor() -> InvoiceExtraction:
    return InvoiceExtraction(
        document_type=DocumentTypeField(
            value=DocumentType.HONORARNOTE, confidence=0.9, evidence="Honorarnote", page=1
        ),
        patient_first_name=ExtractedField(value="Anna", confidence=0.9, evidence="Anna", page=1),
        doctor_name=ExtractedField(value="Anna", confidence=0.6, evidence="Anna", page=1),
        appointment_date=ExtractedField(
            value="2026-05-10", confidence=0.9, evidence="10.05.2026", page=1
        ),
        invoice_date=ExtractedField(value=None, confidence=0.0),
        topic=ExtractedField(value="Kontrolle", confidence=0.9, evidence="Kontrolle", page=1),
        total_amount_eur=ExtractedField(value=120.0, confidence=0.9, evidence="EUR 120", page=1),
    )


def _vision_page_extraction() -> VisionPageExtraction:
    return VisionPageExtraction(
        page_number=1,
        document_type=DocumentTypeField(
            value=DocumentType.HONORARNOTE, confidence=0.9, evidence="Honorarnote", page=1
        ),
        patient_first_name=ExtractedField(value="Max", confidence=0.9, evidence="Max", page=1),
        doctor_name=ExtractedField(
            value="Dr. Testarzt Patient",
            confidence=0.9,
            evidence="Logo Dr. Testarzt Patient",
            page=1,
        ),
        appointment_date=ExtractedField(
            value="2026-05-10", confidence=0.9, evidence="10.05.2026", page=1
        ),
        invoice_date=ExtractedField(value=None, confidence=0.0),
        topic=ExtractedField(value="Kontrolle", confidence=0.9, evidence="Kontrolle", page=1),
        total_amount_eur=ExtractedField(value=120.0, confidence=0.9, evidence="EUR 120", page=1),
    )


def test_extract_structured_invoice_falls_back_to_vision_on_name_similarity(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    rendered = type(
        "RP",
        (),
        {
            "page_number": 1,
            "path": tmp_path / "page.png",
            "width": 800,
            "height": 1100,
        },
    )

    state = cast(
        GraphState,
        {
            "file_path": str(pdf_path),
            "status": "TEXT_QUALITY_EVALUATED",
            "events": [],
            "next_route": "llm_text_extraction",
            "pdf_text": {
                "method": "embedded_text",
                "page_count": 1,
                "total_chars": 10,
                "pages": [{"page_number": 1, "text": "Max", "char_count": 4}],
            },
            "render_dpi": 220,
            "max_vision_pages": 1,
            "ollama_base_url": "http://127.0.0.1:11434",
            "text_model": "test-text",
            "vision_model": "test-vision",
            "ollama_timeout_seconds": 30,
        },
    )

    with (
        patch(
            "health_importer.graph.invoice_nodes.extract_invoice_from_text",
            return_value=_text_extraction_with_patient_as_doctor(),
        ),
        patch(
            "health_importer.graph.invoice_nodes.render_pages",
            return_value=[rendered],
        ),
        patch(
            "health_importer.graph.invoice_nodes.extract_invoice_from_vision_pages",
            return_value=[_vision_page_extraction()],
        ),
    ):
        result = extract_structured_invoice(state)

    assert cast(Any, result).get("extraction_method") == "vision_doctor_similarity_fallback"
    invoice_extraction = cast(Any, result).get("invoice_extraction")
    assert invoice_extraction is not None
    assert invoice_extraction["doctor_name"]["value"] == "Dr. Testarzt Patient"
    assert any(
        event["status"] == "DOCTOR_PATIENT_SIMILARITY_FALLBACK" for event in result["events"]
    )


def test_extract_structured_invoice_keeps_text_when_names_distinct(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    distinct = _text_extraction_with_patient_as_doctor().model_copy(
        update={
            "doctor_name": ExtractedField(
                value="Dr. Testarzt Patient",
                confidence=0.9,
                evidence="Dr. Testarzt Patient",
                page=1,
            )
        }
    )

    state = cast(
        GraphState,
        {
            "file_path": str(pdf_path),
            "status": "TEXT_QUALITY_EVALUATED",
            "events": [],
            "next_route": "llm_text_extraction",
            "pdf_text": {
                "method": "embedded_text",
                "page_count": 1,
                "total_chars": 10,
                "pages": [{"page_number": 1, "text": "Max", "char_count": 4}],
            },
            "render_dpi": 220,
            "max_vision_pages": 1,
            "text_model": "test-text",
            "vision_model": "test-vision",
            "ollama_timeout_seconds": 30,
        },
    )

    with patch(
        "health_importer.graph.invoice_nodes.extract_invoice_from_text",
        return_value=distinct,
    ):
        result = extract_structured_invoice(state)

    assert cast(Any, result).get("extraction_method") == "text"
    invoice_extraction = cast(Any, result).get("invoice_extraction")
    assert invoice_extraction is not None
    assert invoice_extraction["doctor_name"]["value"] == "Dr. Testarzt Patient"
