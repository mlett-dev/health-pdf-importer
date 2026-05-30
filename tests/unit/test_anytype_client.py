from pathlib import Path

import pytest

from health_importer.anytype.client import (
    AnytypeOperationError,
    DryRunAnytypeClient,
    build_anytype_client,
)
from health_importer.anytype.mcp_client import AnytypeMcpClient
from health_importer.config import AnytypeConfig


def test_dry_run_client_searches_configured_collection() -> None:
    client = DryRunAnytypeClient(_config(dry_run=True))

    collection = client.search_collection("Wahlarzt Rechnungen")

    assert collection is not None
    assert collection.id == "collection-id"
    assert collection.type_key == "collection"
    assert client.operation_log[-1].operation == "search_collection"


def test_dry_run_client_returns_none_for_unknown_collection() -> None:
    client = DryRunAnytypeClient(_config(dry_run=True))

    assert client.search_collection("Other") is None


def test_dry_run_client_records_redacted_object_operations(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    client = DryRunAnytypeClient(_config(dry_run=True))

    obj = client.create_object(
        "wahlarztrechnung",
        {"Patient": ["Anna"], "Betrag (€)": 120.0},
        name="Kontrolle",
    )
    client.set_property(obj.id, "done", False)
    file_ref = client.upload_file(pdf_path)
    client.attach_file(obj.id, "rechnung,_gkk", file_ref.id)

    assert obj.id == "dry-run-object-1"
    assert file_ref.id == "dry-run-file-1"
    assert [entry.operation for entry in client.operation_log] == [
        "create_object",
        "set_property",
        "upload_file",
        "attach_file",
    ]
    assert client.operation_log[0].payload_keys == ["Betrag (€)", "Patient"]
    assert client.operation_log[0].dry_run is True


def test_dry_run_upload_rejects_missing_file(tmp_path: Path) -> None:
    client = DryRunAnytypeClient(_config(dry_run=True))

    with pytest.raises(AnytypeOperationError):
        client.upload_file(tmp_path / "missing.pdf")


def test_build_anytype_client_uses_mcp_for_productive_mode(monkeypatch) -> None:
    assert isinstance(build_anytype_client(_config(dry_run=True)), DryRunAnytypeClient)
    monkeypatch.setenv("ANYTYPE_API_KEY", "test-key")
    assert isinstance(build_anytype_client(_config(dry_run=False)), AnytypeMcpClient)


def test_build_anytype_client_uses_configured_extension_command(monkeypatch) -> None:
    monkeypatch.setenv("ANYTYPE_API_KEY", "test-key")

    client = build_anytype_client(
        _config(dry_run=False, extension_command="/opt/anytype/custom-wrapper")
    )

    assert isinstance(client, AnytypeMcpClient)
    assert client.settings.extension_command == "/opt/anytype/custom-wrapper"


def _config(
    *, dry_run: bool, extension_command: str = "anytype-extension-mcp-wrapper"
) -> AnytypeConfig:
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
        extension_command=extension_command,
    )
