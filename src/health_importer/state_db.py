from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

FileStatus = Literal[
    "NEW",
    "PROCESSING",
    "EXTRACTED",
    "VALIDATED",
    "ANYTYPE_CREATED",
    "DONE",
    "REVIEW",
    "ERROR",
]

STATUSES: set[str] = {
    "NEW",
    "PROCESSING",
    "EXTRACTED",
    "VALIDATED",
    "ANYTYPE_CREATED",
    "DONE",
    "REVIEW",
    "ERROR",
}


@dataclass(frozen=True)
class FileRecord:
    id: int
    sha256: str
    original_path: str
    current_path: str
    status: str
    attempt_count: int
    anytype_object_id: str | None
    anytype_file_id: str | None
    last_error: str | None
    created_at: str
    updated_at: str


class StateDb:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sha256 TEXT NOT NULL UNIQUE,
                    original_path TEXT NOT NULL,
                    current_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    anytype_object_id TEXT,
                    anytype_file_id TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(file_id) REFERENCES files(id)
                );
                """
            )
            _ensure_column(connection, "files", "anytype_file_id", "TEXT")

    def register_file(self, path: Path) -> tuple[FileRecord, bool]:
        digest = compute_sha256(path)
        existing = self.get_by_sha256(digest)
        if existing:
            self.add_event(
                existing.id,
                "duplicate_seen",
                {"path": str(path), "existing_status": existing.status},
            )
            return existing, False

        now = _now()
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO files (
                        sha256, original_path, current_path, status, attempt_count,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (digest, str(path), str(path), "NEW", 0, now, now),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("INSERT succeeded but lastrowid is None")
                file_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            concurrent = self.get_by_sha256(digest)
            if concurrent is None:
                raise
            self.add_event(
                concurrent.id,
                "duplicate_seen",
                {"path": str(path), "existing_status": concurrent.status},
            )
            return concurrent, False
        self.add_event(file_id, "file_registered", {"path": str(path), "sha256": digest})
        return self.get_file(file_id), True

    def begin_attempt(self, file_id: int, current_path: Path) -> FileRecord:
        record = self.get_file(file_id)
        if record.status == "DONE":
            self.add_event(file_id, "already_done", {"current_path": str(current_path)})
            return record

        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE files
                SET current_path = ?, status = ?, attempt_count = attempt_count + 1,
                    last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (str(current_path), "PROCESSING", now, file_id),
            )
        self.add_event(file_id, "attempt_started", {"path": str(current_path)})
        return self.get_file(file_id)

    def set_status(
        self,
        file_id: int,
        status: FileStatus,
        *,
        anytype_object_id: str | None = None,
        last_error: str | None = None,
    ) -> FileRecord:
        if status not in STATUSES:
            raise ValueError(f"Unsupported file status: {status}")
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE files
                SET status = ?, anytype_object_id = COALESCE(?, anytype_object_id),
                    last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, anytype_object_id, last_error, now, file_id),
            )
        self.add_event(file_id, "status_changed", {"status": status, "last_error": last_error})
        return self.get_file(file_id)

    def set_anytype_file_id(self, file_id: int, anytype_file_id: str) -> FileRecord:
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE files
                SET anytype_file_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (anytype_file_id, now, file_id),
            )
        self.add_event(file_id, "anytype_file_uploaded", {"anytype_file_id": anytype_file_id})
        return self.get_file(file_id)

    def set_current_path(self, file_id: int, current_path: Path) -> FileRecord:
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE files
                SET current_path = ?, updated_at = ?
                WHERE id = ?
                """,
                (str(current_path), now, file_id),
            )
        self.add_event(file_id, "file_moved", {"current_path": str(current_path)})
        return self.get_file(file_id)

    def add_event(self, file_id: int, event_type: str, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO events (file_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (file_id, event_type, json.dumps(payload, sort_keys=True), _now()),
            )

    def get_file(self, file_id: int) -> FileRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown file id: {file_id}")
        return _record_from_row(row)

    def get_by_sha256(self, sha256: str) -> FileRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM files WHERE sha256 = ?", (sha256,)).fetchone()
        return _record_from_row(row) if row else None

    def get_by_anytype_object_id(self, anytype_object_id: str) -> FileRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM files WHERE anytype_object_id = ?",
                (anytype_object_id,),
            ).fetchone()
        return _record_from_row(row) if row else None

    def list_files(self, *, status: FileStatus | None = None) -> list[FileRecord]:
        with self._connect() as connection:
            if status is None:
                rows = connection.execute("SELECT * FROM files ORDER BY updated_at DESC").fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM files WHERE status = ? ORDER BY updated_at DESC",
                    (status,),
                ).fetchall()
        return [_record_from_row(row) for row in rows]

    def list_events(self, file_id: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_type, payload_json, created_at
                FROM events
                WHERE file_id = ?
                ORDER BY id
                """,
                (file_id,),
            ).fetchall()
        return [
            {
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_from_row(row: sqlite3.Row) -> FileRecord:
    return FileRecord(
        id=row["id"],
        sha256=row["sha256"],
        original_path=row["original_path"],
        current_path=row["current_path"],
        status=row["status"],
        attempt_count=row["attempt_count"],
        anytype_object_id=row["anytype_object_id"],
        anytype_file_id=row["anytype_file_id"],
        last_error=row["last_error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    if column_name not in {row["name"] for row in rows}:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
