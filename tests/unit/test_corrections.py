import pytest

from health_importer.workflow.corrections import load_correction_file


def test_load_correction_file_parses_supported_fields(tmp_path) -> None:
    path = tmp_path / "invoice.correction.yaml"
    path.write_text(
        """
patient: Anna
termin: 2026-05-08
thema: Kontrolle
betrag: 120.50
arzt: "Testarzt Eins"
""",
        encoding="utf-8",
    )

    assert load_correction_file(path) == {
        "patient": "Anna",
        "termin": "2026-05-08",
        "thema": "Kontrolle",
        "betrag": 120.50,
        "arzt": "Testarzt Eins",
    }


def test_load_correction_file_rejects_unknown_key(tmp_path) -> None:
    path = tmp_path / "invoice.correction.yaml"
    path.write_text("unknown: value\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported correction key"):
        load_correction_file(path)
