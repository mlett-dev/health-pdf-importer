from pathlib import Path

import fitz

from health_importer.pdf.extract_text import extract_embedded_text, normalize_pdf_text


def test_extract_embedded_text_keeps_page_context(tmp_path: Path) -> None:
    pdf_path = tmp_path / "text.pdf"
    _write_pdf(pdf_path, ["Rechnung Seite 1", "Betrag EUR 120 Seite 2"])

    result = extract_embedded_text(pdf_path)

    assert result.method == "embedded_text"
    assert result.page_count == 2
    assert result.total_chars > 0
    assert result.pages[0].page_number == 1
    assert "Rechnung Seite 1" in result.pages[0].text
    assert "Betrag EUR 120 Seite 2" in result.pages[1].text
    assert result.is_empty is False


def test_extract_embedded_text_marks_empty_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "empty.pdf"
    _write_pdf(pdf_path, [""])

    result = extract_embedded_text(pdf_path)

    assert result.page_count == 1
    assert result.total_chars == 0
    assert result.is_empty is True


def test_normalize_pdf_text_reduces_spaces_and_preserves_lines() -> None:
    assert normalize_pdf_text("A   B\r\n\r\n\r\nC\tD") == "A B\n\nC D"


def _write_pdf(path: Path, pages: list[str]) -> None:
    document = fitz.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    document.save(path)
    document.close()
