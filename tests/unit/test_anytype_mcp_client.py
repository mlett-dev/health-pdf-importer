from pathlib import Path
from unittest.mock import patch

import pytest
from mcp import types
from pytest import MonkeyPatch

from health_importer.anytype.client import (
    AnytypeAuthError,
    AnytypeConfigError,
    AnytypeFileRef,
    AnytypeOperationError,
    AnytypeSchemaError,
    AnytypeTransientError,
)
from health_importer.anytype.mcp_client import (
    AnytypeMcpClient,
    AnytypeMcpSettings,
    McpToolRunner,
    _call_tool_result_to_dict,
    _container_path_to_host,
    _mcp_env,
    _reraise_classified_mcp_exception,
    _typed_property_value,
)
from health_importer.config import AnytypeConfig


def test_mcp_client_uploads_file_via_extension_input_root(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.delenv("ANYTYPE_FILES_DATA_DIR", raising=False)
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    runner = FakeRunner()
    client = AnytypeMcpClient(
        _config(),
        settings=AnytypeMcpSettings(
            env_path=tmp_path / "missing.env",
            extension_input_root=tmp_path / "mcp-in",
        ),
        runner=runner,
    )

    with patch("health_importer.anytype.mcp_client._cleanup_staged_file") as mock_cleanup:
        file_ref = client.upload_file(pdf_path)
        mock_cleanup.assert_called_once()

    assert isinstance(file_ref, AnytypeFileRef)
    assert file_ref.id == "file-1"
    tool_name, arguments = runner.extension_calls[-1]
    assert tool_name == "file-upload"
    assert Path(arguments["staged_path"]).is_file()
    assert arguments["space_id"] == "space-id"


def test_mcp_client_stages_file_in_anytype_files_data_dir(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    env_path = tmp_path / ".env"
    files_data_dir = tmp_path / "anytype-files"
    env_path.write_text(f"ANYTYPE_FILES_DATA_DIR={files_data_dir}\n", encoding="utf-8")
    runner = FakeRunner()
    client = AnytypeMcpClient(
        _config(),
        settings=AnytypeMcpSettings(
            env_path=env_path,
            extension_input_root=Path("/data/in"),
        ),
        runner=runner,
    )

    with patch("health_importer.anytype.mcp_client._cleanup_staged_file") as mock_cleanup:
        client.upload_file(pdf_path)
        mock_cleanup.assert_called_once()

    _, arguments = runner.extension_calls[-1]
    staged_path = Path(arguments["staged_path"])
    # staged file is now in a UUID-named subdirectory to preserve original filename
    assert staged_path.parent.name != "health-pdf-importer"  # has UUID subdir
    assert str(staged_path).startswith("/data/in/health-pdf-importer/")
    # reconstruct host path: .../health-pdf-importer/<uuid>/invoice.pdf
    host_staged_path = (
        files_data_dir / "in" / "health-pdf-importer" / staged_path.parent.name / staged_path.name
    )
    assert host_staged_path.is_file()


def test_mcp_client_creates_object_with_typed_properties_and_adds_to_collection() -> None:
    runner = FakeRunner()
    client = AnytypeMcpClient(_config(), runner=runner)

    object_ref = client.create_object(
        "wahlarztrechnung",
        {
            "termin": {"date": "2026-05-10"},
            "betrag": {"number": 120},
        },
        name="Kontrolle",
    )
    client.add_object_to_collection("collection-id", object_ref.id)

    assert object_ref.id == "object-1"
    assert runner.official_calls[0] == (
        "API-create-object",
        {
            "space_id": "space-id",
            "type_key": "wahlarztrechnung",
            "name": "Kontrolle",
            "properties": [
                {"key": "termin", "date": "2026-05-10"},
                {"key": "betrag", "number": 120},
            ],
        },
    )
    assert runner.official_calls[1] == (
        "API-add-list-objects",
        {"space_id": "space-id", "list_id": "collection-id", "objects": ["object-1"]},
    )


def test_mcp_client_searches_objects_via_extension_compact_tools() -> None:
    runner = FakeRunner()
    client = AnytypeMcpClient(_config(), runner=runner)

    collection = client.search_collection("Wahlarzt Rechnungen")
    doctors = client.search_object_by_type("arzt", "Muster")

    assert collection is not None
    assert collection.id == "collection-id"
    assert doctors[0].name == "Dr. Testarzt"
    assert [call[0] for call in runner.extension_calls] == [
        "search-space-compact",
        "search-space-compact",
    ]


def test_mcp_client_sets_file_property_via_extension_compact_update() -> None:
    runner = FakeRunner()
    client = AnytypeMcpClient(_config(), runner=runner)

    collection = client.search_collection("Wahlarzt Rechnungen")
    doctors = client.search_object_by_type("arzt", "Muster")
    client.attach_file("object-1", "rechnung_pdf", "file-1")

    assert collection is not None
    assert collection.id == "collection-id"
    assert doctors[0].name == "Dr. Testarzt"
    assert [call[0] for call in runner.extension_calls] == [
        "search-space-compact",
        "search-space-compact",
        "update-object-compact",
    ]
    assert runner.extension_calls[-1][1]["properties"] == [
        {"key": "rechnung_pdf", "files": ["file-1"]}
    ]


def test_mcp_tool_result_wraps_non_object_json() -> None:
    result = types.CallToolResult(
        content=[types.TextContent(type="text", text="true")],
    )

    assert _call_tool_result_to_dict(result) == {"result": True}


class FakeRunner(McpToolRunner):
    def __init__(self) -> None:
        self.extension_calls = []
        self.official_calls = []

    def call_extension(self, tool_name: str, arguments: dict):
        self.extension_calls.append((tool_name, arguments))
        if tool_name == "file-upload":
            return {"object_id": "file-1", "staged_path": arguments["staged_path"]}
        if tool_name == "search-space-compact" and arguments["types"] == ["collection"]:
            return {
                "items": [
                    {
                        "id": "collection-id",
                        "name": "Wahlarzt Rechnungen",
                        "type": {"key": "collection"},
                    }
                ]
            }
        if tool_name == "search-space-compact":
            return {"items": [{"id": "doctor-1", "name": "Dr. Testarzt", "type": {"key": "arzt"}}]}
        if tool_name == "update-object-compact":
            return {"object": {"id": arguments["object_id"], "name": "Kontrolle"}}
        raise AssertionError(tool_name)

    def call_official(self, tool_name: str, arguments: dict):
        self.official_calls.append((tool_name, arguments))
        if tool_name == "API-create-object":
            return {"object": {"id": "object-1", "name": arguments["name"]}}
        if tool_name == "API-add-list-objects":
            return {"ok": True}
        raise AssertionError(tool_name)


def _config() -> AnytypeConfig:
    return AnytypeConfig(
        space_id="space-id",
        collection_name="Wahlarzt Rechnungen",
        collection_id="collection-id",
        custom_type_name="Wahlarztrechnung",
        custom_type_key="wahlarztrechnung",
        dry_run=False,
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


def test_container_path_to_host_translates_data_prefix(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setenv("ANYTYPE_FILES_DATA_DIR", str(tmp_path / "anytype-files"))
    result = _container_path_to_host(Path("/data/out/invoice.pdf"))
    assert result == tmp_path / "anytype-files" / "out" / "invoice.pdf"


def test_container_path_to_host_passthrough_non_data_path() -> None:
    result = _container_path_to_host(Path("/home/user/invoice.pdf"))
    assert result == Path("/home/user/invoice.pdf")


def test_mcp_client_upload_cleans_up_staging_directory(tmp_path: Path) -> None:
    """Regression: _stage_file must not leave orphaned UUID directories behind."""

    monkeypatch = MonkeyPatch()
    monkeypatch.delenv("ANYTYPE_FILES_DATA_DIR", raising=False)
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    runner = FakeRunner()
    client = AnytypeMcpClient(
        _config(),
        settings=AnytypeMcpSettings(
            env_path=tmp_path / "missing.env",
            extension_input_root=tmp_path / "mcp-in",
        ),
        runner=runner,
    )

    client.upload_file(pdf_path)

    # The staged directory should have been removed after upload.
    staging_root = tmp_path / "mcp-in" / "health-pdf-importer"
    if staging_root.exists():
        assert not any(d.is_dir() for d in staging_root.iterdir())


def test_cleanup_staged_file_removes_uuid_directory(tmp_path: Path) -> None:
    from health_importer.anytype.mcp_client import (
        AnytypeMcpSettings,
        _cleanup_staged_file,
    )

    uuid_dir = tmp_path / "health-pdf-importer" / "abc123"
    uuid_dir.mkdir(parents=True)
    staged = uuid_dir / "invoice.pdf"
    staged.write_text("PDF")

    _cleanup_staged_file(
        str(tmp_path / "health-pdf-importer" / "abc123" / "invoice.pdf"),
        AnytypeMcpSettings(env_path=tmp_path / "missing.env", extension_input_root=tmp_path),
    )

    assert not uuid_dir.exists()


def test_call_tool_result_raises_auth_error_on_unauthorized() -> None:
    result = types.CallToolResult(
        isError=True,
        content=[types.TextContent(type="text", text="unauthorized: invalid api key")],
    )
    with pytest.raises(AnytypeAuthError):
        _call_tool_result_to_dict(result)


def test_call_tool_result_raises_schema_error_on_invalid_property() -> None:
    result = types.CallToolResult(
        isError=True,
        content=[types.TextContent(type="text", text="invalid property: type mismatch")],
    )
    with pytest.raises(AnytypeSchemaError):
        _call_tool_result_to_dict(result)


def test_call_tool_result_raises_transient_error_on_timeout() -> None:
    result = types.CallToolResult(
        isError=True,
        content=[types.TextContent(type="text", text="connection timeout")],
    )
    with pytest.raises(AnytypeTransientError):
        _call_tool_result_to_dict(result)


def test_call_tool_result_raises_operation_error_on_unknown() -> None:
    result = types.CallToolResult(
        isError=True,
        content=[types.TextContent(type="text", text="something went wrong")],
    )
    with pytest.raises(AnytypeOperationError):
        _call_tool_result_to_dict(result)


def test_reraise_classified_mcp_exception_config_on_file_not_found() -> None:
    with pytest.raises(AnytypeConfigError):
        _reraise_classified_mcp_exception("test-tool", FileNotFoundError("binary missing"))


def test_reraise_classified_mcp_exception_transient_on_timeout() -> None:
    with pytest.raises(AnytypeTransientError):
        _reraise_classified_mcp_exception("test-tool", TimeoutError("connection timed out"))


def test_reraise_classified_mcp_exception_operation_on_generic() -> None:
    with pytest.raises(AnytypeOperationError):
        _reraise_classified_mcp_exception("test-tool", RuntimeError("boom"))


def test_typed_property_value_raises_schema_error() -> None:
    with pytest.raises(AnytypeSchemaError):
        _typed_property_value("unsupported")


def test_mcp_env_raises_config_error_when_api_key_missing(tmp_path: Path) -> None:
    with pytest.raises(AnytypeConfigError):
        _mcp_env(AnytypeMcpSettings(env_path=tmp_path / "missing.env"))
