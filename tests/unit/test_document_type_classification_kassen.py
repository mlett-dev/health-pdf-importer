"""Test that Kassen PDF fixtures contain expected document-type keywords."""

from pathlib import Path

from health_importer.pdf.extract_text import extract_embedded_text

PDF_DIR = Path(__file__).parent.parent / "fixtures" / "pdfs" / "kassen"


def _extract_text(pdf_name: str) -> str:
    path = PDF_DIR / pdf_name
    result = extract_embedded_text(path)
    return " ".join(page.text for page in result.pages)


def test_kasse_positiv_max_contains_kassen_keywords() -> None:
    text = _extract_text("kasse_positiv_max.pdf")
    assert "Erstattungsbetrag" in text
    assert "Bescheidsdatum" in text
    assert "Patient: Max" in text
    assert "Aktenzeichen" in text


def test_kasse_positiv_anna_contains_kassen_keywords() -> None:
    text = _extract_text("kasse_positiv_anna_ohne_aktenzeichen.pdf")
    assert "Erstattungsbetrag" in text
    assert "Patient: Anna" in text
    assert "Bescheidsdatum" in text


def test_kasse_unsicher_contains_multiple_amounts() -> None:
    text = _extract_text("kasse_unsicher_mehrdeutig.pdf")
    assert "Rechnungsbetrag" in text
    assert "Erstattungsbetrag" in text
    assert "Eigenanteil" in text
    assert "Zuzahlung" in text
