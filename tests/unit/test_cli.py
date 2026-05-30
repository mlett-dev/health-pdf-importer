import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from health_importer.anytype.client import DryRunAnytypeClient
from health_importer.cli import main
from health_importer.state_db import StateDb


def test_help_exits_successfully(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "health-importer" in output
    assert "config-check" in output


def test_config_check(capsys, tmp_path) -> None:
    config_path = _write_config(tmp_path)
    assert main(["--config", str(config_path), "config-check"]) == 0
    assert "Configuration OK: Wahlarzt Rechnungen" in capsys.readouterr().out


def test_doctor_reports_runtime_checks(capsys, tmp_path) -> None:
    config_path = _write_config(tmp_path)
    for folder in ("inbox", "processing", "done", "review", "error"):
        (tmp_path / folder).mkdir()

    with (
        patch("health_importer.commands.common.shutil.which", return_value="/usr/bin/tool"),
        patch("health_importer.commands.common._ollama_json", side_effect=_fake_ollama_json),
        patch("health_importer.commands.common.build_anytype_client") as build_anytype_client,
    ):
        build_anytype_client.return_value = DryRunAnytypeClient(_anytype_config(dry_run=True))
        assert main(["--config", str(config_path), "doctor"]) == 0

    output = capsys.readouterr().out
    assert '"ok": true' in output
    assert '"name": "folders"' in output
    assert '"name": "vision_model"' in output


def test_doctor_fails_when_required_folder_is_missing(capsys, tmp_path) -> None:
    config_path = _write_config(tmp_path)

    with (
        patch("health_importer.commands.common.shutil.which", return_value="/usr/bin/tool"),
        patch("health_importer.commands.common._ollama_json", side_effect=_fake_ollama_json),
    ):
        assert main(["--config", str(config_path), "doctor"]) == 1

    output = capsys.readouterr().out
    assert '"ok": false' in output
    assert "missing folders" in output


def test_cleanup_removes_old_processing_artifacts(capsys, tmp_path) -> None:
    config_path = _write_config(tmp_path)
    processing = tmp_path / "processing"
    processing.mkdir()
    artifact = processing / "invoice_ocr.pdf"
    artifact.write_text("pdf", encoding="utf-8")
    old_timestamp = time.time() - 48 * 60 * 60
    os.utime(artifact, (old_timestamp, old_timestamp))

    assert main(["--config", str(config_path), "cleanup", "--older-than-hours", "24"]) == 0

    output = capsys.readouterr().out
    assert '"count": 1' in output
    assert not artifact.exists()


def test_run_once_prints_json(capsys, tmp_path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    _write_pdf(pdf_path, "Rechnung")
    config_path = _write_config(tmp_path)

    with (
        patch("health_importer.graph.pdf_nodes.run_local_ocr") as ocr,
        patch("health_importer.ai.extractors.OllamaTextClient", _client(_invoice_responses())),
    ):
        _mock_good_ocr(ocr, tmp_path)
        assert main(["--config", str(config_path), "run-once", str(pdf_path)]) == 0
    output = capsys.readouterr().out
    assert '"ok": true' in output
    assert '"status": "DONE"' in output
    assert '"anytype_dry_run": true' in output


def test_goldstandard_prints_accuracy_report(capsys, tmp_path) -> None:
    config_path = _write_config(tmp_path)
    pdf_dir = tmp_path / "pdfs"
    expected_dir = tmp_path / "expected_json"
    pdf_dir.mkdir()
    expected_dir.mkdir()
    (pdf_dir / "invoice.pdf").write_bytes(b"%PDF-1.4\n")
    (expected_dir / "invoice.json").write_text(
        """
{
  "patient": "Max",
  "arzt": null,
  "termin": "2026-05-10",
  "thema": "Kontrolle",
  "betrag": 120
}
""",
        encoding="utf-8",
    )

    with patch(
        "health_importer.commands.goldstandard.run_once_with_config", _fake_goldstandard_run
    ):
        assert (
            main(
                [
                    "--config",
                    str(config_path),
                    "goldstandard",
                    "--pdf-dir",
                    str(pdf_dir),
                    "--expected-dir",
                    str(expected_dir),
                ]
            )
            == 0
        )

    output = capsys.readouterr().out
    assert '"case_count": 1' in output
    assert '"field_accuracy": 1.0' in output


def test_run_once_rejects_no_dry_run_without_productive_config(capsys, tmp_path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    _write_pdf(pdf_path, "Rechnung")
    config_path = _write_config(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(["--config", str(config_path), "run-once", "--no-dry-run", str(pdf_path)])

    assert exc_info.value.code == 2
    assert "--no-dry-run requires anytype.dry_run: false" in capsys.readouterr().err


def test_run_once_allows_no_dry_run_with_productive_config(capsys, tmp_path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    _write_pdf(pdf_path, "Rechnung")
    config_path = _write_config(tmp_path, dry_run=False)

    with (
        patch("health_importer.graph.pdf_nodes.run_local_ocr") as ocr,
        patch("health_importer.ai.extractors.OllamaTextClient", _client(_invoice_responses())),
        patch("health_importer.graph.invoice_nodes.build_anytype_client") as build_anytype_client,
    ):
        build_anytype_client.return_value = DryRunAnytypeClient(_anytype_config(dry_run=True))
        _mock_good_ocr(ocr, tmp_path)
        assert main(["--config", str(config_path), "run-once", "--no-dry-run", str(pdf_path)]) == 0

    output = capsys.readouterr().out
    assert '"anytype_dry_run": false' in output
    assert '"executed": true' in output
    assert '"anytype_object_id": "dry-run-object-1"' in output


def test_scan_inbox_processes_stable_pdf(capsys, tmp_path) -> None:
    config_path = _write_config(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _write_pdf(inbox / "invoice.pdf", "Rechnung")

    with (
        patch("health_importer.graph.pdf_nodes.run_local_ocr") as ocr,
        patch("health_importer.ai.extractors.OllamaTextClient", _client(_invoice_responses())),
    ):
        _mock_good_ocr(ocr, tmp_path)
        assert main(["--config", str(config_path), "scan-inbox", "--wait-seconds", "0"]) == 0

    output = capsys.readouterr().out
    assert '"count": 1' in output
    assert not (inbox / "invoice.pdf").exists()
    assert not (tmp_path / "done" / "invoice.pdf").exists()
    assert (tmp_path / "done" / "2026_05_10_Max_Kontrolle.pdf").exists()


def test_watch_can_run_one_scan_iteration(capsys, tmp_path) -> None:
    config_path = _write_config(tmp_path)

    assert (
        main(
            [
                "--config",
                str(config_path),
                "watch",
                "--wait-seconds",
                "0",
                "--interval-seconds",
                "0",
                "--max-iterations",
                "1",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert '"ok": true' in output
    assert '"count": 0' in output


def test_review_list_prints_review_records(capsys, tmp_path) -> None:
    config_path = _write_config(tmp_path)
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    db = StateDb(tmp_path / "state.sqlite")
    db.initialize()
    record, _ = db.register_file(pdf_path)
    db.set_status(record.id, "REVIEW")

    assert main(["--config", str(config_path), "review-list"]) == 0

    output = capsys.readouterr().out
    assert '"count": 1' in output
    assert '"status": "REVIEW"' in output


def test_retry_applies_correction_file(capsys, tmp_path) -> None:
    config_path = _write_config(tmp_path)
    pdf_path = tmp_path / "invoice.pdf"
    _write_pdf(pdf_path, "Rechnung")
    correction_path = tmp_path / "invoice.correction.yaml"
    correction_path.write_text(
        """
patient: Max
termin: 2026-05-10
thema: Kontrolle
betrag: 120
""",
        encoding="utf-8",
    )
    db = StateDb(tmp_path / "state.sqlite")
    db.initialize()
    record, _ = db.register_file(pdf_path)
    db.set_status(record.id, "REVIEW")

    with (
        patch("health_importer.graph.pdf_nodes.run_local_ocr") as ocr,
        patch(
            "health_importer.ai.extractors.OllamaTextClient",
            _client(_invoice_responses(amount=999.0, amount_evidence="EUR 999")),
        ),
    ):
        _mock_good_ocr(ocr, tmp_path)
        assert (
            main(
                [
                    "--config",
                    str(config_path),
                    "retry",
                    str(record.id),
                    "--correction",
                    str(correction_path),
                ]
            )
            == 0
        )

    output = capsys.readouterr().out
    assert '"retried_file_id": 1' in output
    assert '"status": "DONE"' in output
    events = db.list_events(record.id)
    assert any(event["event_type"] == "manual_correction_applied" for event in events)


def test_status_prints_recent_records(capsys, tmp_path) -> None:
    config_path = _write_config(tmp_path)
    db = StateDb(tmp_path / "state.sqlite")
    db.initialize()
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    db.register_file(pdf_path)

    assert main(["--config", str(config_path), "status"]) == 0

    output = capsys.readouterr().out
    assert '"count": 1' in output
    assert '"status": "NEW"' in output


def test_show_prints_record_with_events(capsys, tmp_path) -> None:
    config_path = _write_config(tmp_path)
    db = StateDb(tmp_path / "state.sqlite")
    db.initialize()
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    record, _ = db.register_file(pdf_path)

    assert main(["--config", str(config_path), "show", str(record.id)]) == 0

    output = capsys.readouterr().out
    assert '"record"' in output
    assert '"events"' in output
    assert '"event_type": "file_registered"' in output


def _write_config(tmp_path, *, dry_run: bool = True):
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        Path("config/app.example.yaml")
        .read_text(encoding="utf-8")
        .replace('"<your-space-id>"', '"test-space-id"')
        .replace('"<your-collection-id>"', '"test-collection-id"')
        .replace(
            "path: data/state.sqlite",
            f"path: {tmp_path / 'state.sqlite'}",
        )
        .replace("inbox: data/inbox", f"inbox: {tmp_path / 'inbox'}")
        .replace("processing: data/processing", f"processing: {tmp_path / 'processing'}")
        .replace("done: data/done", f"done: {tmp_path / 'done'}")
        .replace("review: data/review", f"review: {tmp_path / 'review'}")
        .replace("error: data/error", f"error: {tmp_path / 'error'}")
        .replace("  dry_run: true", f"  dry_run: {str(dry_run).lower()}")
        .replace("  dry_run: false", f"  dry_run: {str(dry_run).lower()}"),
        encoding="utf-8",
    )
    return config_path


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


def _fake_goldstandard_run(
    pdf_path: Path, config, *, anytype_dry_run: bool, correction_overrides=None
):
    return {
        "ok": True,
        "file_path": str(pdf_path),
        "anytype_dry_run": anytype_dry_run,
        "invoice_extraction": {
            "patient_first_name": {"value": "Max"},
            "doctor_name": {"value": None},
            "appointment_date": {"value": "2026-05-10"},
            "topic": {"value": "Kontrolle"},
            "total_amount_eur": {"value": 120.0},
        },
    }


def _fake_ollama_json(config, path: str, payload: dict | None = None):
    if path == "/api/tags":
        return {"models": []}
    return {"capabilities": ["completion", "vision", "tools", "thinking"]}


def _anytype_config(*, dry_run: bool):
    from health_importer.config import AnytypeConfig

    return AnytypeConfig(
        space_id="space-id",
        collection_name="Wahlarzt Rechnungen",
        collection_id="collection-id",
        custom_type_name="Wahlarztrechnung",
        custom_type_key="wahlarztrechnung",
        dry_run=dry_run,
        gkk_property_id="test-gkk-id",
        pkv_property_id="test-pkv-id",
        pkv_eingereicht_property_id="test-pkv-eingereicht-id",
        attachment_property_id="test-attachment-id",
        done_property_id="test-done-id",
        patient_tag_property_id="test-patient-tag-id",
        amount_property_id="test-amount-id",
        date_property_id="test-date-id",
        doctor_property_id="test-doctor-id",
    )
