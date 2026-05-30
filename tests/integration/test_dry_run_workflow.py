from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from health_importer.cli import main


def test_cli_run_once_produces_expected_anytype_dry_run_plan(capsys, tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    _write_pdf(
        pdf_path,
        (
            "Honorarnote Rechnung Patient Max Ordination 10.05.2026 "
            "Betrag EUR 120 Leistung Kontrolle " * 40
        ),
    )
    config_path = _write_config(tmp_path)

    with (
        patch("health_importer.ai.extractors.OllamaTextClient", _client(_invoice_responses())),
        patch("health_importer.anytype.client.build_anytype_client") as build_anytype_client,
    ):
        assert main(["--config", str(config_path), "run-once", str(pdf_path)]) == 0

    build_anytype_client.assert_not_called()
    output = json.loads(capsys.readouterr().out)
    operations = output["import_plan"]["anytype_operations"]

    assert output["ok"] is True
    assert output["status"] == "DONE"
    assert output["anytype_dry_run"] is True
    assert output["import_plan"]["target_filename"] == "2026_05_10_Max_Kontrolle.pdf"
    assert operations == [
        {"operation": "upload_file", "dry_run": True},
        {"operation": "create_object", "dry_run": True},
        {"operation": "attach_file", "dry_run": True},
    ]
    done_dir = tmp_path / "done"
    assert any(done_dir.iterdir()), "Expected target file in done folder"
    sidecar_path = next(done_dir.glob("*.import.json"))
    sidecar = json.loads(sidecar_path.read_text())
    assert sidecar["extracted_fields"]["document_type"]["value"] == "honorarnote"


def _write_config(tmp_path: Path) -> Path:
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
        .replace("archive: data/archive", f"archive: {tmp_path / 'archive'}")
        .replace("  dry_run: false", "  dry_run: true"),
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


def _invoice_responses() -> list[str]:
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


def _client(responses: list[str]):
    shared_responses = list(responses)

    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = shared_responses

        def chat(self, messages):
            return self.responses.pop(0)

    return FakeClient
