from pathlib import Path

from health_importer.config import FolderConfig
from health_importer.watcher import is_pdf_candidate, is_stable_file, scan_inbox


def test_is_pdf_candidate_filters_non_import_files() -> None:
    assert is_pdf_candidate(Path("invoice.pdf")) is True
    assert is_pdf_candidate(Path("invoice.PDF")) is True
    assert is_pdf_candidate(Path("invoice.txt")) is False
    assert is_pdf_candidate(Path(".invoice.pdf")) is False
    assert is_pdf_candidate(Path("invoice.pdf.tmp")) is False
    assert is_pdf_candidate(Path("invoice.pdf.part")) is False
    assert is_pdf_candidate(Path("invoice.pdf.crdownload")) is False


def test_is_stable_file_accepts_unchanged_file(tmp_path: Path) -> None:
    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"%PDF-1.4\n")

    assert is_stable_file(path, wait_seconds=0) is True


def test_scan_inbox_returns_stable_pdfs_only(tmp_path: Path) -> None:
    folders = _folders(tmp_path)
    folders.inbox.mkdir()
    (folders.inbox / "a.pdf").write_bytes(b"a")
    (folders.inbox / "b.PDF").write_bytes(b"b")
    (folders.inbox / "c.txt").write_text("c", encoding="utf-8")
    (folders.inbox / "d.pdf.part").write_bytes(b"d")

    found = scan_inbox(folders, wait_seconds=0)

    assert [path.name for path in found] == ["a.pdf", "b.PDF"]


def _folders(tmp_path: Path) -> FolderConfig:
    return FolderConfig(
        inbox=tmp_path / "Inbox",
        processing=tmp_path / "Processing",
        done=tmp_path / "Done",
        review=tmp_path / "Review",
        error=tmp_path / "Error",
    )
