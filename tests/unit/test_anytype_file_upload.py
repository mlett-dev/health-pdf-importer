from pathlib import Path
from typing import cast

import pytest

from health_importer.anytype.client import AnytypeClient, AnytypeOperationError, DryRunAnytypeClient
from health_importer.anytype.file_upload import AnytypeFileUploadError, upload_pdf_once
from health_importer.config import AnytypeConfig
from health_importer.state_db import StateDb


def test_upload_pdf_once_uploads_and_stores_file_id(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    db, file_id = _registered_db(tmp_path, pdf_path)
    client = DryRunAnytypeClient(_config())

    result = upload_pdf_once(client, db, file_id=file_id, pdf_path=pdf_path)

    assert result.reused_existing is False
    assert result.file_ref.id == "dry-run-file-1"
    assert db.get_file(file_id).anytype_file_id == "dry-run-file-1"


def test_upload_pdf_once_reuses_existing_file_id(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    db, file_id = _registered_db(tmp_path, pdf_path)
    db.set_anytype_file_id(file_id, "file-existing")
    client = DryRunAnytypeClient(_config())

    result = upload_pdf_once(client, db, file_id=file_id, pdf_path=pdf_path)

    assert result.reused_existing is True
    assert result.file_ref.id == "file-existing"
    assert client.operation_log == []


def test_upload_pdf_once_records_retryable_upload_failure(tmp_path: Path) -> None:
    pdf_path = tmp_path / "missing.pdf"
    db_path = tmp_path / "state.sqlite"
    db = StateDb(db_path)
    db.initialize()
    existing = tmp_path / "placeholder.pdf"
    existing.write_bytes(b"%PDF-1.4\n% test\n")
    record, _ = db.register_file(existing)
    client = DryRunAnytypeClient(_config())

    with pytest.raises(AnytypeFileUploadError):
        upload_pdf_once(client, db, file_id=record.id, pdf_path=pdf_path)

    assert db.list_events(record.id)[-1]["event_type"] == "anytype_file_upload_failed"


def test_upload_pdf_once_translates_client_upload_errors(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    db, file_id = _registered_db(tmp_path, pdf_path)

    class FailingClient:
        def upload_file(self, path: Path):
            raise AnytypeOperationError("network unavailable")

    with pytest.raises(AnytypeFileUploadError, match="network unavailable"):
        upload_pdf_once(
            cast(AnytypeClient, FailingClient()), db, file_id=file_id, pdf_path=pdf_path
        )


def _registered_db(tmp_path: Path, pdf_path: Path) -> tuple[StateDb, int]:
    db = StateDb(tmp_path / "state.sqlite")
    db.initialize()
    record, _ = db.register_file(pdf_path)
    return db, record.id


def _config() -> AnytypeConfig:
    return AnytypeConfig(
        space_id="space-id",
        collection_name="Wahlarzt Rechnungen",
        collection_id="collection-id",
        custom_type_name="Wahlarztrechnung",
        custom_type_key="wahlarztrechnung",
        dry_run=True,
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
