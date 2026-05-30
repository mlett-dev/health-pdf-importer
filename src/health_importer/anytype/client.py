from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from health_importer.config import AnytypeConfig


class AnytypeClientError(RuntimeError):
    """Base error for deterministic Anytype client failures."""


class AnytypeOperationError(AnytypeClientError):
    """Raised when an Anytype operation fails."""


class AnytypeTransientError(AnytypeClientError):
    """Raised for retryable failures: network, timeout, temporary MCP unavailability."""


class AnytypeConfigError(AnytypeClientError):
    """Raised for permanent configuration problems: missing env vars, wrong paths."""


class AnytypeAuthError(AnytypeClientError):
    """Raised for authentication/authorization failures."""


class AnytypeSchemaError(AnytypeClientError):
    """Raised for property/schema mismatches or invalid file references."""


@dataclass(frozen=True)
class AnytypeObjectRef:
    id: str
    name: str
    type_key: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnytypeFileRef:
    id: str
    name: str
    path: str


@dataclass(frozen=True)
class AnytypeOperationLog:
    operation: str
    dry_run: bool
    object_id: str | None = None
    file_id: str | None = None
    property_key: str | None = None
    payload_keys: list[str] = field(default_factory=list)


class AnytypeClient(Protocol):
    def search_collection(self, name: str) -> AnytypeObjectRef | None: ...

    def search_object_by_type(self, type_name: str, query: str) -> list[AnytypeObjectRef]: ...

    def create_object(
        self,
        type_name: str,
        properties: dict[str, Any],
        *,
        name: str | None = None,
    ) -> AnytypeObjectRef: ...

    def set_property(self, object_id: str, property_id: str, value: Any) -> None: ...

    def upload_file(self, path: Path) -> AnytypeFileRef: ...

    def attach_file(self, object_id: str, property_id: str, file_id: str) -> None: ...

    def download_file(self, file_id: str) -> Path: ...

    def add_object_to_collection(self, collection_id: str, object_id: str) -> None: ...


class DryRunAnytypeClient:
    def __init__(self, config: AnytypeConfig) -> None:
        self.config = config
        self.operation_log: list[AnytypeOperationLog] = []
        self._created_objects = 0
        self._uploaded_files = 0

    def search_collection(self, name: str) -> AnytypeObjectRef | None:
        self.operation_log.append(AnytypeOperationLog(operation="search_collection", dry_run=True))
        if name != self.config.collection_name:
            return None
        return AnytypeObjectRef(
            id=self.config.collection_id,
            name=self.config.collection_name,
            type_key="collection",
        )

    def search_object_by_type(self, type_name: str, query: str) -> list[AnytypeObjectRef]:
        self.operation_log.append(
            AnytypeOperationLog(
                operation="search_object_by_type",
                dry_run=True,
                payload_keys=["query", "type_name"],
            )
        )
        return []

    def create_object(
        self,
        type_name: str,
        properties: dict[str, Any],
        *,
        name: str | None = None,
    ) -> AnytypeObjectRef:
        self._created_objects += 1
        object_id = f"dry-run-object-{self._created_objects}"
        self.operation_log.append(
            AnytypeOperationLog(
                operation="create_object",
                dry_run=True,
                object_id=object_id,
                payload_keys=sorted(properties),
            )
        )
        return AnytypeObjectRef(
            id=object_id,
            name=name or str(properties.get("name", "Untitled")),
            type_key=type_name,
        )

    def set_property(self, object_id: str, property_id: str, value: Any) -> None:
        self.operation_log.append(
            AnytypeOperationLog(
                operation="set_property",
                dry_run=True,
                object_id=object_id,
                property_key=property_id,
                payload_keys=[_value_kind(value)],
            )
        )

    def upload_file(self, path: Path) -> AnytypeFileRef:
        if not path.exists():
            raise AnytypeOperationError(f"Cannot upload missing file: {path}")
        self._uploaded_files += 1
        file_id = f"dry-run-file-{self._uploaded_files}"
        self.operation_log.append(
            AnytypeOperationLog(
                operation="upload_file",
                dry_run=True,
                file_id=file_id,
                payload_keys=["filename"],
            )
        )
        return AnytypeFileRef(id=file_id, name=path.name, path=str(path))

    def attach_file(self, object_id: str, property_id: str, file_id: str) -> None:
        self.operation_log.append(
            AnytypeOperationLog(
                operation="attach_file",
                dry_run=True,
                object_id=object_id,
                file_id=file_id,
                property_key=property_id,
            )
        )

    def download_file(self, file_id: str) -> Path:
        self.operation_log.append(
            AnytypeOperationLog(
                operation="download_file",
                dry_run=True,
                file_id=file_id,
            )
        )
        return Path(f"/tmp/dry-run-download-{file_id}.pdf")

    def add_object_to_collection(self, collection_id: str, object_id: str) -> None:
        self.operation_log.append(
            AnytypeOperationLog(
                operation="add_object_to_collection",
                dry_run=True,
                object_id=object_id,
                property_key=collection_id,
            )
        )


def build_anytype_client(config: AnytypeConfig) -> AnytypeClient:
    if config.dry_run:
        return DryRunAnytypeClient(config)
    from health_importer.anytype.mcp_client import AnytypeMcpClient

    return AnytypeMcpClient(config)


def _value_kind(value: Any) -> str:
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__
