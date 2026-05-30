from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from health_importer.config import FolderConfig

TEMPORARY_SUFFIXES = {".tmp", ".part", ".crdownload"}


def is_pdf_candidate(path: Path) -> bool:
    if path.name.startswith("."):
        return False
    if path.suffix.lower() != ".pdf":
        return False
    lowered_name = path.name.lower()
    return not any(lowered_name.endswith(suffix) for suffix in TEMPORARY_SUFFIXES)


def is_stable_file(path: Path, *, wait_seconds: float = 2.0) -> bool:
    if not path.exists() or not path.is_file():
        return False
    first_stat = path.stat()
    time.sleep(wait_seconds)
    if not path.exists() or not path.is_file():
        return False
    second_stat = path.stat()
    return (
        first_stat.st_size == second_stat.st_size
        and first_stat.st_mtime_ns == second_stat.st_mtime_ns
    )


def scan_inbox(folders: FolderConfig, *, wait_seconds: float = 2.0) -> list[Path]:
    if not folders.inbox.exists():
        return []
    candidates = sorted(path for path in folders.inbox.iterdir() if is_pdf_candidate(path))
    return [path for path in candidates if is_stable_file(path, wait_seconds=wait_seconds)]


class InboxEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        folders: FolderConfig,
        on_pdf: Callable[[Path], Any],
        *,
        wait_seconds: float = 2.0,
    ) -> None:
        self.folders = folders
        self.on_pdf = on_pdf
        self.wait_seconds = wait_seconds

    def on_created(self, event) -> None:  # type: ignore[override]
        if not isinstance(event, FileCreatedEvent) or event.is_directory:
            return
        path = Path(str(event.src_path))
        if is_pdf_candidate(path) and is_stable_file(path, wait_seconds=self.wait_seconds):
            self.on_pdf(path)


def watch_inbox(
    folders: FolderConfig,
    on_pdf: Callable[[Path], Any],
    *,
    wait_seconds: float = 2.0,
) -> Observer:  # type: ignore[reportInvalidTypeForm]
    observer = Observer()
    handler = InboxEventHandler(folders, on_pdf, wait_seconds=wait_seconds)
    observer.schedule(handler, str(folders.inbox), recursive=False)
    observer.start()
    return observer
