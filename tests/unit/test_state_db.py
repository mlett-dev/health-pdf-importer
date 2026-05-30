from pathlib import Path
from unittest.mock import patch

from health_importer.graph.runner import run_once
from health_importer.state_db import StateDb, compute_sha256


def test_register_file_detects_duplicate(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    db = StateDb(tmp_path / "state.sqlite")
    db.initialize()

    first, first_created = db.register_file(pdf_path)
    second, second_created = db.register_file(pdf_path)

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert second.sha256 == compute_sha256(pdf_path)


def test_run_once_skips_already_done_duplicate(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    _write_pdf(pdf_path, "Rechnung")
    db_path = tmp_path / "state.sqlite"

    with (
        patch("health_importer.graph.pdf_nodes.run_local_ocr") as ocr,
        patch("health_importer.ai.extractors.OllamaTextClient", _client(_invoice_responses())),
    ):
        _mock_good_ocr(ocr, tmp_path)
        first = run_once(
            pdf_path,
            state_db_path=db_path,
            done_folder=tmp_path / "done",
            review_folder=tmp_path / "review",
            error_folder=tmp_path / "error",
        )
    new_path = Path(first["file_path"])
    second = run_once(
        new_path,
        state_db_path=db_path,
        done_folder=tmp_path / "done",
        review_folder=tmp_path / "review",
        error_folder=tmp_path / "error",
    )

    assert first["ok"] is True
    assert first["status"] == "DONE"
    assert second["ok"] is True
    assert second["status"] == "SKIPPED_DUPLICATE"
    assert second["duplicate_of_file_id"] == first["file_id"]


def test_error_record_can_retry(tmp_path: Path) -> None:
    missing = tmp_path / "invoice.pdf"
    db_path = tmp_path / "state.sqlite"

    failed = run_once(
        missing,
        state_db_path=db_path,
        done_folder=tmp_path / "done",
        review_folder=tmp_path / "review",
        error_folder=tmp_path / "error",
    )
    _write_pdf(missing, "Rechnung")
    with (
        patch("health_importer.graph.pdf_nodes.run_local_ocr") as ocr,
        patch("health_importer.ai.extractors.OllamaTextClient", _client(_invoice_responses())),
    ):
        _mock_good_ocr(ocr, tmp_path)
        retried = run_once(
            missing,
            state_db_path=db_path,
            done_folder=tmp_path / "done",
            review_folder=tmp_path / "review",
            error_folder=tmp_path / "error",
        )

    assert failed["ok"] is False
    assert failed["status"] == "ERROR"
    assert retried["ok"] is True
    assert retried["status"] == "DONE"
    assert retried["attempt_count"] == 1


def test_anytype_file_id_can_be_stored(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    db = StateDb(tmp_path / "state.sqlite")
    db.initialize()
    record, _ = db.register_file(pdf_path)

    updated = db.set_anytype_file_id(record.id, "file-1")

    assert updated.anytype_file_id == "file-1"
    assert db.list_events(record.id)[-1]["event_type"] == "anytype_file_uploaded"


def test_list_files_can_filter_by_status(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    first.write_bytes(b"%PDF-1.4\n% first\n")
    second.write_bytes(b"%PDF-1.4\n% second\n")
    db = StateDb(tmp_path / "state.sqlite")
    db.initialize()
    first_record, _ = db.register_file(first)
    second_record, _ = db.register_file(second)
    db.set_status(first_record.id, "REVIEW")
    db.set_status(second_record.id, "DONE")

    records = db.list_files(status="REVIEW")

    assert [record.id for record in records] == [first_record.id]


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


def _invoice_responses():
    return [
        """
        {
          "document_type": {"value": "honorarnote", "confidence": 0.9, "evidence": "Honorarnote", "page": 1},
          "patient_first_name": {"value": "Max", "confidence": 0.9, "evidence": "Patient Max", "page": 1},
          "doctor_name": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
          "appointment_date": {"value": "2026-05-10", "confidence": 0.9, "evidence": "10.05.2026", "page": 1},
          "invoice_date": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
          "topic": {"value": "Kontrolle", "confidence": 0.9, "evidence": "Kontrolle", "page": 1},
          "total_amount_eur": {"value": 120.0, "confidence": 0.9, "evidence": "EUR 120", "page": 1},
          "warnings": [],
          "missing_fields": []
        }
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
