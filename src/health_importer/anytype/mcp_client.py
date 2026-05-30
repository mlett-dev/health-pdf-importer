from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from health_importer.anytype.client import (
    AnytypeAuthError,
    AnytypeClientError,
    AnytypeConfigError,
    AnytypeFileRef,
    AnytypeObjectRef,
    AnytypeOperationError,
    AnytypeSchemaError,
    AnytypeTransientError,
)
from health_importer.config import AnytypeConfig
from health_importer.env import load_dotenv


@dataclass(frozen=True)
class AnytypeMcpSettings:
    api_base_url: str = "http://127.0.0.1:31012"
    api_version: str = "2025-11-08"
    env_path: Path = Path(".env")
    extension_command: str = "anytype-extension-mcp-wrapper"
    extension_input_root: Path = Path("/data/in")
    official_command: str = "npx"
    official_args: tuple[str, ...] = ("-y", "@anyproto/anytype-mcp")


class AnytypeMcpClient:
    def __init__(
        self,
        config: AnytypeConfig,
        *,
        settings: AnytypeMcpSettings | None = None,
        runner: "McpToolRunner | None" = None,
    ) -> None:
        self.config = config
        self.settings = settings or AnytypeMcpSettings(
            extension_command=config.extension_command
        )
        self.runner = runner or McpToolRunner(self.settings)

    def search_collection(self, name: str) -> AnytypeObjectRef | None:
        result = self.runner.call_extension(
            "search-space-compact",
            {
                "space_id": self.config.space_id,
                "query": name,
                "types": ["collection"],
                "limit": 10,
                "fields": ["id", "name", "type"],
            },
        )
        for item in _items_from_result(result):
            if item.get("name") == name:
                return AnytypeObjectRef(
                    id=str(item["id"]),
                    name=str(item["name"]),
                    type_key=_type_key(item),
                )
        return None

    def search_object_by_type(self, type_name: str, query: str) -> list[AnytypeObjectRef]:
        result = self.runner.call_extension(
            "search-space-compact",
            {
                "space_id": self.config.space_id,
                "query": query,
                "types": [type_name],
                "limit": 50,
                "fields": ["id", "name", "type", "properties"],
            },
        )
        refs = []
        for item in _items_from_result(result):
            raw_props = item.get("properties")
            props = raw_props if isinstance(raw_props, dict) else {}
            refs.append(
                AnytypeObjectRef(
                    id=str(item["id"]),
                    name=str(item["name"]),
                    type_key=_type_key(item),
                    properties=props,
                )
            )
        return refs

    def create_object(
        self,
        type_name: str,
        properties: dict[str, Any],
        *,
        name: str | None = None,
    ) -> AnytypeObjectRef:
        payload = {
            "space_id": self.config.space_id,
            "type_key": type_name,
            "properties": _property_dict_to_list(properties),
        }
        if name is not None:
            payload["name"] = name
        result = self.runner.call_official(
            "API-create-object",
            payload,
        )
        data = _object_from_result(result)
        return AnytypeObjectRef(
            id=str(data["id"]),
            name=str(data.get("name") or name or ""),
            type_key=str(data.get("type_key") or type_name),
        )

    def set_property(self, object_id: str, property_id: str, value: Any) -> None:
        self.runner.call_extension(
            "update-object-compact",
            {
                "space_id": self.config.space_id,
                "object_id": object_id,
                "properties": [{"key": property_id, **_typed_property_value(value)}],
                "fields": ["id", "name"],
            },
        )

    def upload_file(self, path: Path) -> AnytypeFileRef:
        staged_path = self._stage_file(path)
        try:
            result = self.runner.call_extension(
                "file-upload",
                {
                    "space_id": self.config.space_id,
                    "staged_path": staged_path,
                    "type": "file",
                    "style": "link",
                },
            )
            data = _file_from_result(result)
            return AnytypeFileRef(
                id=str(data["id"]),
                name=str(data.get("name") or path.name),
                path=str(path),
            )
        finally:
            _cleanup_staged_file(staged_path, self.settings)

    def attach_file(self, object_id: str, property_id: str, file_id: str) -> None:
        self.set_property(object_id, property_id, {"files": [file_id]})

    def download_file(self, file_id: str) -> Path:
        result = self.runner.call_extension(
            "file-download",
            {"object_id": file_id},
        )
        local_path = result.get("local_path") or result.get("server_path")
        if not local_path:
            raise AnytypeClientError(f"file-download did not return a path: {result}")
        return _container_path_to_host(Path(str(local_path)))

    def add_object_to_collection(self, collection_id: str, object_id: str) -> None:
        self.runner.call_official(
            "API-add-list-objects",
            {
                "space_id": self.config.space_id,
                "list_id": collection_id,
                "objects": [object_id],
            },
        )

    def _stage_file(self, path: Path) -> str:
        if not path.exists():
            raise AnytypeConfigError(f"Cannot upload missing file: {path}")
        host_input_root = _extension_host_input_root(self.settings)
        staging_dir = host_input_root / "health-pdf-importer"
        staging_dir.mkdir(parents=True, exist_ok=True)
        upload_dir = staging_dir / uuid.uuid4().hex
        upload_dir.mkdir(parents=True, exist_ok=True)
        staged = upload_dir / path.name
        shutil.copy2(path, staged)
        return str(
            self.settings.extension_input_root
            / "health-pdf-importer"
            / upload_dir.name
            / staged.name
        )


class McpToolRunner:
    def __init__(self, settings: AnytypeMcpSettings) -> None:
        self.settings = settings
        self.env = _mcp_env(settings)

    def call_extension(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(
            self._call(
                StdioServerParameters(
                    command=self.settings.extension_command,
                    args=[],
                    env={
                        **self.env,
                        "ANYTYPE_API_BASE_URL": self.settings.api_base_url,
                        "ANYTYPE_API_KEY": self.env["ANYTYPE_API_KEY"],
                        "ANYTYPE_API_VERSION": self.settings.api_version,
                    },
                ),
                tool_name,
                arguments,
            )
        )

    def call_official(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(
            self._call(
                StdioServerParameters(
                    command=sys.executable,
                    args=[
                        "-m",
                        "health_importer.anytype.official_mcp_stderr_filter",
                        self.settings.official_command,
                        *self.settings.official_args,
                    ],
                    env={
                        **self.env,
                        "ANYTYPE_API_BASE_URL": self.settings.api_base_url,
                        "OPENAPI_MCP_HEADERS": json.dumps(
                            {
                                "Authorization": f"Bearer {self.env['ANYTYPE_API_KEY']}",
                                "Anytype-Version": self.settings.api_version,
                            }
                        ),
                    },
                ),
                tool_name,
                arguments,
            )
        )

    async def _call(
        self,
        parameters: StdioServerParameters,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        result: types.CallToolResult | None = None
        try:
            async with stdio_client(parameters) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
        except Exception as exc:  # noqa: BLE001 - MCP startup/tool failures need one boundary.
            _reraise_classified_mcp_exception(tool_name, exc)
        if result is None:
            raise RuntimeError("MCP tool call did not return a result")
        return _call_tool_result_to_dict(result)


def _mcp_env(settings: AnytypeMcpSettings) -> dict[str, str]:
    env = {**os.environ, **load_dotenv(settings.env_path)}
    if not env.get("ANYTYPE_API_KEY"):
        raise AnytypeConfigError("ANYTYPE_API_KEY is missing; set it in .env or the environment")
    return env


def _extension_host_input_root(settings: AnytypeMcpSettings) -> Path:
    env = {**os.environ, **load_dotenv(settings.env_path)}
    files_data_dir = env.get("ANYTYPE_FILES_DATA_DIR")
    if files_data_dir:
        return Path(files_data_dir).expanduser() / "in"
    return settings.extension_input_root


def _cleanup_staged_file(staged_path: str, settings: AnytypeMcpSettings) -> None:
    """Best-effort removal of the staged file and its UUID directory after upload."""
    host_input_root = _extension_host_input_root(settings)
    staged = Path(staged_path)
    if len(staged.parts) < 2:
        return
    uuid_dir = host_input_root / "health-pdf-importer" / staged.parts[-2]
    if uuid_dir.exists() and uuid_dir.is_dir():
        shutil.rmtree(uuid_dir, ignore_errors=True)


def _container_path_to_host(path: Path) -> Path:
    """Translate Docker container path to host path for Anytype extension MCP.

    The extension MCP runs in a Docker container where the host's
    ANYTYPE_FILES_DATA_DIR is mounted at /data. Returned paths are
    container-internal, so we map them back to the host filesystem.
    """
    container_root = Path("/data")
    default_data_dir = Path.home() / ".local/share/health-pdf-importer/anytype-files"
    data_dir = os.environ.get("ANYTYPE_FILES_DATA_DIR", str(default_data_dir))
    try:
        rel = path.relative_to(container_root)
    except ValueError:
        return path
    return Path(data_dir).expanduser() / rel


def _call_tool_result_to_dict(result: types.CallToolResult) -> dict[str, Any]:
    if result.isError:
        _raise_classified_mcp_error(_content_to_text(result.content))
    text = _content_to_text(result.content)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnytypeOperationError(f"MCP tool did not return JSON: {text[:200]}") from exc
    if isinstance(data, dict):
        return data
    return {"result": data}


def _content_to_text(content: list[types.ContentBlock]) -> str:
    chunks = [block.text for block in content if isinstance(block, types.TextContent)]
    return "\n".join(chunks).strip()


def _items_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = result.get("items") or result.get("results") or result.get("objects") or []
    if not isinstance(raw_items, list):
        raise AnytypeClientError("MCP list response does not contain an item list")
    return [item for item in raw_items if isinstance(item, dict)]


def _object_from_result(result: dict[str, Any]) -> dict[str, Any]:
    for key in ("object", "result", "file"):
        value = result.get(key)
        if isinstance(value, dict):
            return value
    if "id" in result:
        return result
    raise AnytypeClientError("MCP response does not contain an object")


def _file_from_result(result: dict[str, Any]) -> dict[str, Any]:
    try:
        return _object_from_result(result)
    except AnytypeClientError:
        # file-upload returns object_id + preload_file_id.
        # Empirical test shows object_id works for linking in a files
        # property; preload_file_id was empty string and failed.
        object_id = result.get("object_id")
        if object_id:
            return {"id": object_id}
        preload_file_id = result.get("preload_file_id")
        if preload_file_id:
            return {"id": preload_file_id}
        raise


def _reraise_classified_mcp_exception(tool_name: str, exc: Exception) -> None:
    """Re-raise an MCP exception with a specific AnytypeClientError subclass."""
    msg = f"MCP tool call failed: {tool_name}: {exc}"
    if isinstance(exc, (FileNotFoundError, PermissionError)):
        raise AnytypeConfigError(msg) from exc
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        raise AnytypeTransientError(msg) from exc
    raise AnytypeOperationError(msg) from exc


def _raise_classified_mcp_error(error_text: str) -> None:
    """Raise the appropriate AnytypeClientError subclass based on MCP error text."""
    lower = error_text.lower()
    if any(
        k in lower
        for k in ("unauthorized", "authentication", "api key", "invalid token", "forbidden")
    ):
        raise AnytypeAuthError(f"MCP tool returned an error: {error_text}")
    if any(
        k in lower
        for k in (
            "invalid property",
            "schema",
            "type mismatch",
            "unsupported value",
            "invalid file reference",
        )
    ):
        raise AnytypeSchemaError(f"MCP tool returned an error: {error_text}")
    if any(k in lower for k in ("timeout", "connection", "temporarily", "unavailable", "network")):
        raise AnytypeTransientError(f"MCP tool returned an error: {error_text}")
    raise AnytypeOperationError(f"MCP tool returned an error: {error_text}")


def _type_key(item: dict[str, Any]) -> str | None:
    item_type = item.get("type")
    if isinstance(item_type, dict):
        key = item_type.get("key")
        return str(key) if key else None
    key = item.get("type_key")
    return str(key) if key else None


def _property_dict_to_list(properties: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"key": key, **_typed_property_value(value)} for key, value in properties.items()]


def _typed_property_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        typed_keys = {
            "text",
            "number",
            "select",
            "multi_select",
            "date",
            "files",
            "checkbox",
            "url",
            "email",
            "phone",
            "objects",
        }
        if len(typed_keys.intersection(value)) == 1:
            return value
    raise AnytypeSchemaError(f"Unsupported Anytype property value: {value!r}")
