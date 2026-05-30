from __future__ import annotations

import shutil
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from health_importer.config import FolderConfig


@dataclass(frozen=True)
class MoveResult:
    source: Path
    destination: Path
    collision_resolved: bool


def ensure_workflow_folders(folders: FolderConfig) -> None:
    for path in (
        folders.inbox,
        folders.processing,
        folders.done,
        folders.review,
        folders.error,
    ):
        path.mkdir(parents=True, exist_ok=True)


def safe_move(source: Path, destination_dir: Path) -> MoveResult:
    if not source.exists():
        raise FileNotFoundError(f"Source file does not exist: {source}")
    if not source.is_file():
        raise ValueError(f"Source path is not a file: {source}")

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = reserve_unique_destination(destination_dir / source.name)
    try:
        shutil.move(str(source), str(destination))
    except Exception:
        if destination.exists() and destination.stat().st_size == 0:
            destination.unlink()
        raise
    return MoveResult(
        source=source,
        destination=destination,
        collision_resolved=destination.name != source.name,
    )


def unique_destination(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def reserve_unique_destination(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = path if counter == 1 else parent / f"{stem}_{counter}{suffix}"
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            counter += 1
            continue
        else:
            os.close(fd)
            return candidate


def cleanup_temporary_artifacts(root: Path, *, older_than_hours: int = 24) -> list[Path]:
    if older_than_hours < 0:
        raise ValueError("older_than_hours must not be negative")
    if not root.exists():
        return []

    cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
    removed: list[Path] = []
    for path in sorted(root.rglob("*"), reverse=True):
        if not _is_temporary_artifact(path):
            continue
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        if modified_at > cutoff:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(path)
    return removed


def _is_temporary_artifact(path: Path) -> bool:
    if path.is_dir():
        return path.name.endswith("_vision_pages")
    return path.name.endswith("_ocr.pdf") or path.suffix.lower() in {".tmp", ".part"}
