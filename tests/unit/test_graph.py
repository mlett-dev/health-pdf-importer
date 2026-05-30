from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from health_importer.graph.runner import run_once
from health_importer.graph.state import GraphState


def test_run_once_finishes_for_file(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    _write_pdf(pdf_path, "Rechnung\nBetrag EUR 120")

    with (
        patch("health_importer.graph.pdf_nodes.run_local_ocr") as ocr,
        patch("health_importer.ai.extractors.OllamaTextClient", _client(_invoice_responses())),
    ):
        _mock_good_ocr(ocr, tmp_path)
        result = run_once(
            pdf_path,
            done_folder=tmp_path / "done",
            review_folder=tmp_path / "review",
            error_folder=tmp_path / "error",
        )

    assert result["ok"] is True
    assert result["status"] == "DONE"
    assert result["file_name"] == "invoice.pdf"
    assert result["file_size"] > 0
    assert len(result["sha256"]) == 64
    assert result["pdf_text"]["method"] == "embedded_text"
    assert result["pdf_text"]["total_chars"] > 0
    assert result["text_quality"]["route"] in {"llm_text_extraction", "ocr"}
    assert isinstance(result["text_quality"]["score"], float)
    assert [event["node"] for event in result["events"]] == [
        "load_file_metadata",
        "mark_started",
        "extract_embedded_pdf_text",
        "evaluate_embedded_text_quality",
        "run_ocr_if_needed",
        "render_vision_pages_if_needed",
        "extract_structured_invoice",
        "route_by_document_type",
        "apply_manual_corrections",
        "verify_structured_invoice",
        "validate_structured_invoice",
        "verify_invoice_text_values",
        "decide_import_route",
        "prepare_import_plan",
        "rename_file_to_target",
        "execute_anytype_import",
        "move_invoice_to_target",
        "mark_finished",
        "cleanup_vision_temp",
    ]
    assert result["invoice_extraction"]["patient_first_name"]["value"] == "Max"
    assert result["routing_decision"]["action"] == "AUTO_CREATE"
    assert result["import_plan"]["target_filename"] == "2026_05_10_Max_Kontrolle.pdf"
    assert result["anytype_execution"]["executed"] is False
    assert result["anytype_execution"]["reason"] == "dry_run"


def test_run_once_returns_structured_error_for_missing_file(tmp_path: Path) -> None:
    result = run_once(tmp_path / "missing.pdf")

    assert result["ok"] is False
    assert result["status"] == "ERROR"
    assert result["error"]["type"] == "FileNotFoundError"


def test_run_once_routes_text_mismatch_to_review(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    _write_pdf(pdf_path, "Rechnung")

    with (
        patch("health_importer.graph.pdf_nodes.run_local_ocr") as ocr,
        patch(
            "health_importer.ai.extractors.OllamaTextClient",
            _client(_invoice_responses(amount=999.0, amount_evidence="EUR 999")),
        ),
    ):
        _mock_good_ocr(ocr, tmp_path)
        result = run_once(
            pdf_path,
            done_folder=tmp_path / "done",
            review_folder=tmp_path / "review",
            error_folder=tmp_path / "error",
        )

    assert result["ok"] is True
    assert result["status"] == "REVIEW"
    assert result["routing_decision"]["action"] == "REVIEW_ONLY"
    assert "amount_not_found_in_text" in result["routing_decision"]["blocking_reasons"]


def test_verify_invoice_text_values_uses_vision_for_vision_extraction(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from health_importer.ai.schemas import VisionValueVerification
    from health_importer.graph.invoice_nodes import verify_invoice_text_values

    image = tmp_path / "page.png"
    image.write_bytes(b"png")

    def fake_verify_invoice_values_vision(images, **kwargs):
        assert images == [(1, image)]
        assert kwargs["amount"] == "190.0"
        assert kwargs["target_date"] == "2026-05-15"
        return VisionValueVerification(
            amount_found=True,
            date_found=True,
            amount_evidence="EUR 190,00",
            date_evidence="15.05.2026",
            warnings=[],
            confidence=0.92,
        )

    monkeypatch.setattr(
        "health_importer.graph.invoice_nodes.verify_invoice_values_vision",
        fake_verify_invoice_values_vision,
    )
    state = cast(
        GraphState,
        {
            "events": [],
            "extraction_method": "vision",
            "vision_model": "qwen3.6:35b-a3b-q8_0",
            "vision_pages": [{"page_number": 1, "path": str(image), "width": 10, "height": 10}],
            "pdf_text": {"pages": [{"page_number": 1, "text": ""}]},
            "validation": {
                "ok": True,
                "invoice": {
                    "patient_first_name": "Max",
                    "date": "2026-05-15",
                    "date_source": "appointment_date",
                    "topic": "Kardiologische Untersuchung",
                    "total_amount_eur": "190.0",
                    "doctor_name": "Dr. Testarzt Delta",
                    "warnings": [],
                },
                "errors": [],
                "warnings": [],
            },
        },
    )

    result = verify_invoice_text_values(state)

    tv = cast(Any, result).get("text_verification")
    assert tv is not None
    assert tv["source"] == "vision"
    assert tv["amount_found"] is True
    assert tv["date_found"] is True
    assert tv["amount_evidence"] == "EUR 190,00"
    assert tv["warnings"] == []


def test_run_once_applies_manual_corrections(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    _write_pdf(pdf_path, "Rechnung")

    with (
        patch("health_importer.graph.pdf_nodes.run_local_ocr") as ocr,
        patch(
            "health_importer.ai.extractors.OllamaTextClient",
            _client(_invoice_responses(amount=999.0, amount_evidence="EUR 999")),
        ),
    ):
        _mock_good_ocr(ocr, tmp_path)
        result = run_once(
            pdf_path,
            done_folder=tmp_path / "done",
            review_folder=tmp_path / "review",
            error_folder=tmp_path / "error",
            correction_overrides={
                "betrag": 120.0,
                "termin": "2026-05-10",
                "patient": "Max",
                "thema": "Kontrolle",
            },
        )

    assert result["ok"] is True
    assert result["status"] == "DONE"
    assert result["invoice_extraction"]["total_amount_eur"]["value"] == 120.0
    assert "apply_manual_corrections" in [event["node"] for event in result["events"]]


def _write_pdf(path: Path, text: str) -> None:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def _mock_good_ocr(ocr, tmp_path: Path) -> None:
    text = (
        "Honorarnote Rechnung Patient Max Ordination 10.05.2026 Betrag EUR 120 "
        "Leistung Kontrolle " * 40
    )
    ocr.return_value.output_path = tmp_path / "invoice_ocr.pdf"
    ocr.return_value.text.to_dict.return_value = {
        "method": "embedded_text",
        "page_count": 1,
        "total_chars": len(text),
        "pages": [{"page_number": 1, "text": text, "char_count": len(text)}],
        "is_empty": False,
    }
    ocr.return_value.text.total_chars = len(text)
    ocr.return_value.text.page_count = 1


def _invoice_responses(*, amount=120.0, amount_evidence="EUR 120"):
    return [
        f"""
        {{
          "document_type": {{"value": "honorarnote", "confidence": 0.9, "evidence": "Honorarnote", "page": 1}},
          "patient_first_name": {{"value": "Max", "confidence": 0.9, "evidence": "Patient Max", "page": 1}},
          "doctor_name": {{"value": null, "confidence": 0.0, "evidence": null, "page": null}},
          "appointment_date": {{"value": "2026-05-10", "confidence": 0.9, "evidence": "10.05.2026", "page": 1}},
          "invoice_date": {{"value": null, "confidence": 0.0, "evidence": null, "page": null}},
          "topic": {{"value": "Kontrolle", "confidence": 0.9, "evidence": "Kontrolle", "page": 1}},
          "total_amount_eur": {{"value": {amount}, "confidence": 0.9, "evidence": "{amount_evidence}", "page": 1}},
          "warnings": [],
          "missing_fields": []
        }}
        """,
        """
        {"status":"valid","issues":[],"confidence":0.9}
        """,
    ]


def _client(responses):
    shared_responses = list(responses)

    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = shared_responses

        def chat(self, messages):
            return self.responses.pop(0)

    return FakeClient


def test_cleanup_vision_temp_node_deletes_directory(tmp_path: Path) -> None:
    from health_importer.graph.finalization_nodes import cleanup_vision_temp

    temp_dir = tmp_path / "vision-pages"
    temp_dir.mkdir()
    (temp_dir / "page.png").write_text("png")

    state = cast(GraphState, {"events": [], "vision_pages_temp_dir": str(temp_dir)})
    result = cleanup_vision_temp(state)

    assert not temp_dir.exists()
    assert result.get("vision_pages_temp_dir") is None
    assert any(e["status"] == "VISION_TEMP_CLEANED" for e in result["events"])


def test_cleanup_vision_temp_node_noop_when_no_dir() -> None:
    from health_importer.graph.finalization_nodes import cleanup_vision_temp

    state = cast(GraphState, {"events": []})
    result = cleanup_vision_temp(state)

    assert result.get("vision_pages_temp_dir") is None
    assert any(e["status"] == "VISION_TEMP_CLEANED" for e in result["events"])


def test_prepare_import_plan_uses_topic_as_object_name() -> None:
    """Regression: target_object_name must be the full topic, not the filename stem.

    When the topic is longer than the filename-truncated part (max_topic_length),
    the Anytype object name should still contain the complete topic text,
    because the object name is not subject to filesystem length limits.
    """

    from health_importer.graph.invoice_nodes import prepare_import_plan

    long_topic = "Kontrolle von Wachstum und Gewicht (Z00.2!)"
    state = cast(
        GraphState,
        {
            "events": [],
            "file_path": "/tmp/invoice.pdf",
            "validation": {
                "ok": True,
                "invoice": {
                    "patient_first_name": "Anna",
                    "date": "2026-05-08",
                    "date_source": "invoice_text",
                    "topic": long_topic,
                    "total_amount_eur": "120.00",
                    "doctor_name": "Dr. Testarzt",
                    "warnings": [],
                },
                "errors": [],
                "warnings": [],
            },
            "routing_decision": {"action": "AUTO_CREATE", "blocking_reasons": []},
        },
    )
    result = prepare_import_plan(state)

    plan = cast(Any, result).get("import_plan")
    assert plan is not None
    # Filename is slugified for the filesystem; topic chars like parentheses are removed
    assert plan["target_filename"] == "2026_05_08_Anna_Kontrolle_von_Wachstum_und_Gewicht_Z00.2.pdf"
    # Object name must contain the full topic, not the truncated filename stem
    assert plan["target_object_name"] == long_topic
