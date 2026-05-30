from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from health_importer.config import (
    AnytypeConfig,
    FileNamingConfig,
    KassenFileNamingConfig,
    KassenMatchConfig,
)
from health_importer.graph.runner import run_once


def _invoice_responses() -> list[str]:
    import json

    return [
        json.dumps(
            {
                "document_type": {
                    "value": "honorarnote",
                    "confidence": 0.9,
                    "evidence": "Honorarnote",
                    "page": 1,
                },
                "patient_first_name": {
                    "value": "Max",
                    "confidence": 0.9,
                    "evidence": "Patient Max",
                    "page": 1,
                },
                "doctor_name": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
                "appointment_date": {
                    "value": "2026-05-10",
                    "confidence": 0.9,
                    "evidence": "10.05.2026",
                    "page": 1,
                },
                "invoice_date": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
                "topic": {
                    "value": "Kontrolle",
                    "confidence": 0.9,
                    "evidence": "Kontrolle",
                    "page": 1,
                },
                "total_amount_eur": {
                    "value": 120.0,
                    "confidence": 0.9,
                    "evidence": "EUR 120",
                    "page": 1,
                },
                "warnings": [],
                "missing_fields": [],
            }
        ),
        json.dumps({"status": "valid", "issues": [], "confidence": 0.9}),
    ]


def _kassen_responses() -> list[str]:
    import json

    return [
        json.dumps(
            {
                "document_type": {
                    "value": "krankenkasse_antwort",
                    "confidence": 0.95,
                    "evidence": "Krankenkasse",
                    "page": 1,
                },
                "patient_first_name": {
                    "value": "Max",
                    "confidence": 0.9,
                    "evidence": "Max",
                    "page": 1,
                },
                "doctor_name": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
                "appointment_date": {
                    "value": "2026-05-15",
                    "confidence": 0.9,
                    "evidence": "15.05.2026",
                    "page": 1,
                },
                "invoice_date": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
                "topic": {
                    "value": "Kontrolle",
                    "confidence": 0.9,
                    "evidence": "Kontrolle",
                    "page": 1,
                },
                "total_amount_eur": {
                    "value": 120.0,
                    "confidence": 0.9,
                    "evidence": "EUR 120",
                    "page": 1,
                },
                "invoice_number": {
                    "value": None,
                    "confidence": 0.0,
                    "evidence": None,
                    "page": None,
                },
                "iban": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
                "diagnosis": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
                "line_items": [],
                "warnings": [],
                "missing_fields": [],
            }
        ),
        json.dumps(
            {
                "document_type": {
                    "value": "krankenkasse_antwort",
                    "confidence": 0.95,
                    "evidence": "Krankenkasse",
                    "page": 1,
                },
                "patient_first_name": {
                    "value": "Max",
                    "confidence": 0.95,
                    "evidence": "Max",
                    "page": 1,
                },
                "doctor_name": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
                "bescheids_datum": {
                    "value": "2026-05-15",
                    "confidence": 0.9,
                    "evidence": "15.05.2026",
                    "page": 1,
                },
                "aufwendungsbetrag_eur": {
                    "value": None,
                    "confidence": 0.0,
                    "evidence": None,
                    "page": None,
                },
                "erstattungsbetrag_eur": {
                    "value": "85.00",
                    "confidence": 0.95,
                    "evidence": "85,00 EUR",
                    "page": 1,
                },
                "rechnungsnummer": {
                    "value": None,
                    "confidence": 0.0,
                    "evidence": None,
                    "page": None,
                },
                "aktenzeichen": {
                    "value": "XY123",
                    "confidence": 0.9,
                    "evidence": "XY123",
                    "page": 1,
                },
                "betreffender_termin": {
                    "value": None,
                    "confidence": 0.0,
                    "evidence": None,
                    "page": None,
                },
                "warnings": [],
                "missing_fields": [],
            }
        ),
    ]


def _pkv_responses() -> list[str]:
    import json

    return [
        json.dumps(
            {
                "document_type": {
                    "value": "pkv_antwort",
                    "confidence": 0.95,
                    "evidence": "Pkv",
                    "page": 1,
                },
                "patient_first_name": {
                    "value": "Max",
                    "confidence": 0.9,
                    "evidence": "Max",
                    "page": 1,
                },
                "doctor_name": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
                "appointment_date": {
                    "value": "2026-05-20",
                    "confidence": 0.9,
                    "evidence": "20.05.2026",
                    "page": 1,
                },
                "invoice_date": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
                "topic": {
                    "value": "Kontrolle",
                    "confidence": 0.9,
                    "evidence": "Kontrolle",
                    "page": 1,
                },
                "total_amount_eur": {
                    "value": 120.0,
                    "confidence": 0.9,
                    "evidence": "EUR 120",
                    "page": 1,
                },
                "invoice_number": {
                    "value": None,
                    "confidence": 0.0,
                    "evidence": None,
                    "page": None,
                },
                "iban": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
                "diagnosis": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
                "line_items": [],
                "warnings": [],
                "missing_fields": [],
            }
        ),
        json.dumps(
            {
                "document_type": {
                    "value": "pkv_antwort",
                    "confidence": 0.95,
                    "evidence": "Pkv",
                    "page": 1,
                },
                "patient_first_name": {
                    "value": "Max",
                    "confidence": 0.95,
                    "evidence": "Max",
                    "page": 1,
                },
                "erstattungsbetrag_eur": {
                    "value": "42.50",
                    "confidence": 0.95,
                    "evidence": "42,50 EUR",
                    "page": 1,
                },
                "bescheids_datum": {
                    "value": None,
                    "confidence": 0.0,
                    "evidence": None,
                    "page": None,
                },
                "aufwendungsbetrag_eur": {
                    "value": None,
                    "confidence": 0.0,
                    "evidence": None,
                    "page": None,
                },
                "rechnungsnummer": {
                    "value": "R-456",
                    "confidence": 0.9,
                    "evidence": "R-456",
                    "page": 1,
                },
                "betreffender_termin": {
                    "value": None,
                    "confidence": 0.0,
                    "evidence": None,
                    "page": None,
                },
                "warnings": [],
                "missing_fields": [],
            }
        ),
    ]


def _run_once_kwargs(tmp_path, dry_run_config, file_naming, *, email_config=None):
    kwargs = {
        "anytype_config": dry_run_config,
        "anytype_dry_run": True,
        "file_naming": file_naming,
        "review_folder": tmp_path / "review",
        "done_folder": tmp_path / "done",
        "error_folder": tmp_path / "error",
        "allow_external_services": True,
    }
    if email_config is not None:
        kwargs["email_config"] = email_config
    return kwargs


def fake_ollama_client(responses):
    shared = list(responses)

    class Client:
        def __init__(self, **kwargs):
            self.responses = shared

        def chat(self, messages):
            return self.responses.pop(0)

    return Client


class _FakeMatchKassen:
    @staticmethod
    def __call__(state):
        from copy import deepcopy

        from health_importer.graph.state import (
            STATE_EVENTS,
            STATE_MATCHING_CANDIDATES,
            STATE_SELECTED_MATCH,
            STATE_STATUS,
        )
        from health_importer.graph.state_helpers import event

        next_state = deepcopy(state)
        next_state[STATE_SELECTED_MATCH] = {
            "object_id": "obj-kassen-123",
            "name": "Test Rechnung",
            "score": 0.97,
            "reasons": ["patient_match", "date_match"],
            "invoice_file_id": "file-old-1",
            "properties": {"rechnung,_gkk": {"files": ["file-old-1"]}},
        }
        next_state[STATE_MATCHING_CANDIDATES] = []
        next_state[STATE_STATUS] = "KASSEN_MATCHED"
        next_state[STATE_EVENTS] = list(next_state.get(STATE_EVENTS, []))
        next_state[STATE_EVENTS].append(
            event(
                "match_kassen_invoice", "KASSEN_MATCHED", "Top match: Test Rechnung (score=0.97)."
            )
        )
        return next_state


class _FakeMatchPkv:
    @staticmethod
    def __call__(state):
        from copy import deepcopy

        from health_importer.graph.state import (
            STATE_EVENTS,
            STATE_MATCHING_CANDIDATES,
            STATE_SELECTED_MATCH,
            STATE_STATUS,
        )
        from health_importer.graph.state_helpers import event

        next_state = deepcopy(state)
        next_state[STATE_SELECTED_MATCH] = {
            "object_id": "obj-pkv-456",
            "name": "Pkv Rechnung",
            "score": 0.97,
            "reasons": ["patient_match", "date_match", "amount_match"],
            "invoice_file_id": "file-old-2",
            "properties": {"rechnung,_gkk": {"files": ["file-old-2"]}},
        }
        next_state[STATE_MATCHING_CANDIDATES] = []
        next_state[STATE_STATUS] = "PKV_MATCHED"
        next_state[STATE_EVENTS] = list(next_state.get(STATE_EVENTS, []))
        next_state[STATE_EVENTS].append(
            event("match_pkv_invoice", "PKV_MATCHED", "Top match: Pkv Rechnung (score=0.97).")
        )
        return next_state


def test_invoice_dry_run_end_to_end(
    tmp_path: Path,
    invoice_pdf: Path,
    dry_run_config: AnytypeConfig,
    file_naming: FileNamingConfig,
) -> None:
    kwargs = _run_once_kwargs(tmp_path, dry_run_config, file_naming)

    with (
        patch(
            "health_importer.ai.extractors.OllamaTextClient",
            fake_ollama_client(_invoice_responses()),
        ),
        patch("health_importer.ai.extractors.OllamaVisionClient", fake_ollama_client([])),
        patch("health_importer.anytype.client.build_anytype_client") as mock_build,
    ):
        mock_build.return_value = MagicMock()
        result = run_once(invoice_pdf, **kwargs)

    assert result["ok"] is True
    assert result["status"] == "DONE"
    assert result["anytype_dry_run"] is True
    operations = result.get("import_plan", {}).get("anytype_operations", [])
    assert operations == [
        {"operation": "upload_file", "dry_run": True},
        {"operation": "create_object", "dry_run": True},
        {"operation": "attach_file", "dry_run": True},
    ]
    done_dir = tmp_path / "done"
    assert any(done_dir.iterdir()), "Expected target file in done folder"
    sidecar = json.loads(next(done_dir.glob("*.import.json")).read_text())
    assert sidecar["extracted_fields"]["document_type"]["value"] == "honorarnote"


def test_kassen_positive_dry_run_end_to_end(
    tmp_path: Path,
    kassen_pdf: Path,
    dry_run_config: AnytypeConfig,
    file_naming: FileNamingConfig,
    kassen_file_naming: KassenFileNamingConfig,
    kassen_match: KassenMatchConfig,
    email_config,
) -> None:
    kwargs = _run_once_kwargs(tmp_path, dry_run_config, file_naming, email_config=email_config)
    kwargs["kassen_file_naming"] = kassen_file_naming
    kwargs["kassen_match"] = kassen_match

    with (
        patch(
            "health_importer.ai.extractors.OllamaTextClient",
            fake_ollama_client(_kassen_responses()),
        ),
        patch("health_importer.ai.extractors.OllamaVisionClient", fake_ollama_client([])),
        patch("health_importer.graph.kassen_nodes.find_invoice_candidates") as mock_find,
        patch("health_importer.graph.kassen_nodes.score_match_candidates") as mock_score,
        patch("health_importer.anytype.client.build_anytype_client") as mock_build,
    ):
        from health_importer.anytype.client import AnytypeObjectRef
        from health_importer.anytype.kassen_matching import KassenMatchCandidate

        ref = AnytypeObjectRef(
            id="obj-kassen-123",
            name="Test Rechnung",
            properties={"rechnung,_gkk": {"files": ["file-old-1"]}},
        )
        mock_find.return_value = (
            [ref],
            {"obj-kassen-123": {"rechnung,_gkk": {"files": ["file-old-1"]}}},
        )
        mock_score.return_value = [
            KassenMatchCandidate(
                object_ref=ref,
                score=0.97,
                match_reasons=["patient"],
                invoice_file_id="file-old-1",
                properties={"rechnung,_gkk": {"files": ["file-old-1"]}},
            )
        ]
        mock_build.return_value = MagicMock()
        result = run_once(kassen_pdf, **kwargs)

    if not result["ok"]:
        raise AssertionError(json.dumps(result, indent=2, default=str))
    assert result["ok"] is True
    assert result["status"] == "DONE"
    exec_info = result.get("anytype_execution", {})
    assert exec_info.get("executed") is False
    assert exec_info.get("dry_run") is True
    ops = exec_info.get("operations", [])
    assert [op["operation"] for op in ops] == [
        "attach_kassen_pdf",
        "update_kassen_properties",
        "update_pkv_eingereicht",
    ]
    assert ops[2].get("skipped") is True
    done_dir = tmp_path / "done"
    assert any(done_dir.iterdir()), "Expected target file in done folder"
    sidecar = json.loads(next(done_dir.glob("*.import.json")).read_text())
    assert sidecar["document_type"] == "krankenkasse_antwort"
    assert sidecar["matched_invoice"]["object_id"] == "obj-kassen-123"


def test_pkv_dry_run_end_to_end(
    tmp_path: Path,
    pkv_pdf: Path,
    dry_run_config: AnytypeConfig,
    file_naming: FileNamingConfig,
    kassen_match: KassenMatchConfig,
) -> None:
    kwargs = _run_once_kwargs(tmp_path, dry_run_config, file_naming)
    kwargs["kassen_match"] = kassen_match
    kwargs["state_db_path"] = tmp_path / "state.sqlite"

    with (
        patch(
            "health_importer.ai.extractors.OllamaTextClient", fake_ollama_client(_pkv_responses())
        ),
        patch("health_importer.ai.extractors.OllamaVisionClient", fake_ollama_client([])),
        patch("health_importer.graph.pkv_nodes.find_invoice_candidates") as mock_find,
        patch("health_importer.graph.pkv_nodes.score_pkv_candidates") as mock_score,
        patch("health_importer.anytype.client.build_anytype_client") as mock_build,
    ):
        from health_importer.anytype.client import AnytypeObjectRef
        from health_importer.anytype.pkv_matching import PkvMatchCandidate

        ref = AnytypeObjectRef(
            id="obj-pkv-123",
            name="Pkv Rechnung",
            properties={"rechnung,_gkk": {"files": ["file-old-2"]}},
        )
        mock_find.return_value = (
            [ref],
            {"obj-pkv-123": {"rechnung,_gkk": {"files": ["file-old-2"]}}},
        )
        mock_score.return_value = [
            PkvMatchCandidate(
                object_ref=ref,
                score=0.97,
                match_reasons=["rechnungsnummer_exact:R-456"],
                invoice_file_id="file-old-2",
                properties={"rechnung,_gkk": {"files": ["file-old-2"]}},
            )
        ]
        mock_build.return_value = MagicMock()
        result = run_once(pkv_pdf, **kwargs)

    if not result["ok"]:
        raise AssertionError(json.dumps(result, indent=2, default=str))
    assert result["ok"] is True
    assert result["status"] == "DONE"
    exec_info = result.get("anytype_execution", {})
    assert exec_info.get("executed") is False
    assert exec_info.get("dry_run") is True
    ops = exec_info.get("operations", [])
    assert [op["operation"] for op in ops] == [
        "update_pkv_properties",
        "attach_pkv_pdf",
        "mark_invoice_done",
    ]
    done_dir = tmp_path / "done"
    assert any(done_dir.iterdir()), "Expected target file in done folder"
    sidecar = json.loads(next(done_dir.glob("*.import.json")).read_text())
    assert sidecar["document_type"] == "pkv_antwort"
    assert sidecar["matched_invoice"]["object_id"] == "obj-pkv-123"


def test_pkv_error_after_upload_no_done(
    tmp_path: Path,
    pkv_pdf: Path,
    dry_run_config: AnytypeConfig,
    file_naming: FileNamingConfig,
    kassen_match: KassenMatchConfig,
) -> None:
    kwargs = _run_once_kwargs(tmp_path, dry_run_config, file_naming)
    kwargs["kassen_match"] = kassen_match
    kwargs["state_db_path"] = tmp_path / "state.sqlite"

    from health_importer.anytype.client import AnytypeOperationError
    from health_importer.anytype.pkv_matching import PkvMatchCandidate

    def _fail_property(*args, **kwargs):
        raise AnytypeOperationError("property update failed")

    with (
        patch(
            "health_importer.ai.extractors.OllamaTextClient", fake_ollama_client(_pkv_responses())
        ),
        patch("health_importer.ai.extractors.OllamaVisionClient", fake_ollama_client([])),
        patch("health_importer.graph.pkv_nodes.find_invoice_candidates") as mock_find,
        patch("health_importer.graph.pkv_nodes.score_pkv_candidates") as mock_score,
        patch(
            "health_importer.graph.anytype_update_nodes.update_pkv_properties",
            side_effect=_fail_property,
        ),
        patch("health_importer.anytype.client.build_anytype_client") as mock_build,
    ):
        from health_importer.anytype.client import AnytypeObjectRef

        ref = AnytypeObjectRef(
            id="obj-pkv-123",
            name="Pkv Rechnung",
            properties={"rechnung,_gkk": {"files": ["file-old-2"]}},
        )
        mock_find.return_value = (
            [ref],
            {"obj-pkv-123": {"rechnung,_gkk": {"files": ["file-old-2"]}}},
        )
        mock_score.return_value = [
            PkvMatchCandidate(
                object_ref=ref,
                score=0.97,
                match_reasons=["rechnungsnummer_exact:R-456"],
                invoice_file_id="file-old-2",
                properties={"rechnung,_gkk": {"files": ["file-old-2"]}},
            )
        ]
        client = MagicMock()
        mock_build.return_value = client
        result = run_once(pkv_pdf, **kwargs)

    assert result["ok"] is False
    assert result["status"] == "ERROR"
    done_dir = tmp_path / "done"
    error_dir = tmp_path / "error"
    assert not done_dir.exists() or not any(done_dir.iterdir()), "Done folder should be empty"
    assert error_dir.exists() and any(error_dir.iterdir()), "Error folder should contain the file"
    sidecar = json.loads(next(error_dir.glob("*.import.json")).read_text())
    assert sidecar["status"].endswith("FAILED") or sidecar["status"].endswith("ERROR")
    ops = result.get("anytype_execution", {}).get("operations", [])
    done_ops = [op for op in ops if op["operation"] == "mark_invoice_done"]
    assert not done_ops, "mark_invoice_done should not be in operations on failure"


def test_duplicate_file_skipped(
    tmp_path: Path,
    invoice_pdf: Path,
    dry_run_config: AnytypeConfig,
    file_naming: FileNamingConfig,
) -> None:
    state_db_path = tmp_path / "state.sqlite"
    kwargs = _run_once_kwargs(tmp_path, dry_run_config, file_naming)
    kwargs["state_db_path"] = state_db_path

    with (
        patch(
            "health_importer.ai.extractors.OllamaTextClient",
            fake_ollama_client(_invoice_responses()),
        ),
        patch("health_importer.ai.extractors.OllamaVisionClient", fake_ollama_client([])),
        patch("health_importer.anytype.client.build_anytype_client") as mock_build,
    ):
        mock_build.return_value = MagicMock()
        first = run_once(invoice_pdf, **kwargs)

    assert first["ok"] is True
    assert first["status"] == "DONE"
    assert first.get("file_id") is not None

    # copy file back because run_once moved it to done/
    import shutil

    shutil.copy2(first["file_path"], invoice_pdf)

    with (
        patch(
            "health_importer.ai.extractors.OllamaTextClient",
            fake_ollama_client(_invoice_responses()),
        ),
        patch("health_importer.ai.extractors.OllamaVisionClient", fake_ollama_client([])),
        patch("health_importer.anytype.client.build_anytype_client") as mock_build,
    ):
        mock_build.return_value = MagicMock()
        second = run_once(invoice_pdf, **kwargs)

    assert second["ok"] is True
    assert second["status"] == "SKIPPED_DUPLICATE"
    assert second.get("duplicate_of_file_id") == first["file_id"]
