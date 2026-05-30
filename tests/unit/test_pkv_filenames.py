"""Tests for Pkv PDF filename generation."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from health_importer.config import PkvFileNamingConfig
from health_importer.workflow.filenames import generate_pkv_filename, generate_unique_pkv_path
from health_importer.workflow.validation import ValidatedPkvAntwort


def _make_config(**kwargs) -> PkvFileNamingConfig:
    defaults = {
        "enabled": True,
        "pattern": "{date}_{patient}_PKV_{topic}.pdf",
        "date_format": "%Y_%m_%d",
        "max_topic_length": 30,
    }
    defaults.update(kwargs)
    return PkvFileNamingConfig(**defaults)


def test_generate_pkv_filename_basic() -> None:
    pkv = ValidatedPkvAntwort(
        patient_first_name="Max",
        doctor_name="Dr. Testarzt A",
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("100.00"),
        erstattungsbetrag_eur=Decimal("85.00"),
        rechnungsnummer="R-123",
        betreffender_termin=date(2024, 3, 1),
    )
    config = _make_config()
    filename = generate_pkv_filename(pkv, config)
    assert filename == "2024_03_15_Max_PKV_Dr._Testarzt_A.pdf"


def test_generate_pkv_filename_disabled() -> None:
    pkv = ValidatedPkvAntwort(
        patient_first_name="Max",
        doctor_name="Dr. Testarzt A",
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("100.00"),
        erstattungsbetrag_eur=Decimal("85.00"),
        rechnungsnummer="R-123",
        betreffender_termin=date(2024, 3, 1),
    )
    config = _make_config(enabled=False)
    filename = generate_pkv_filename(pkv, config)
    assert filename == ""


def test_generate_pkv_filename_no_date() -> None:
    pkv = ValidatedPkvAntwort(
        patient_first_name="Anna",
        doctor_name=None,
        bescheids_datum=None,
        aufwendungsbetrag_eur=Decimal("60.00"),
        erstattungsbetrag_eur=Decimal("50.00"),
        rechnungsnummer="R-456",
        betreffender_termin=None,
    )
    config = _make_config()
    filename = generate_pkv_filename(pkv, config)
    assert filename == "unknown_date_Anna_PKV_PKV_Rueckmeldung.pdf"


def test_generate_pkv_filename_service_date_placeholder() -> None:
    pkv = ValidatedPkvAntwort(
        patient_first_name="Max",
        doctor_name="Dr. Testarzt A",
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("100.00"),
        erstattungsbetrag_eur=Decimal("85.00"),
        rechnungsnummer="R-123",
        betreffender_termin=date(2024, 3, 1),
    )
    config = _make_config(pattern="{service_date}_{patient}_{topic}.pdf")
    filename = generate_pkv_filename(pkv, config)
    assert filename == "2024_03_01_Max_Dr._Testarzt_A.pdf"


def test_generate_pkv_filename_service_date_fallback() -> None:
    pkv = ValidatedPkvAntwort(
        patient_first_name="Anna",
        doctor_name=None,
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("60.00"),
        erstattungsbetrag_eur=Decimal("50.00"),
        rechnungsnummer="R-456",
        betreffender_termin=None,
    )
    config = _make_config(pattern="{service_date}_{patient}_{topic}.pdf")
    filename = generate_pkv_filename(pkv, config)
    assert filename == "unknown_date_Anna_PKV_Rueckmeldung.pdf"


def test_generate_pkv_filename_doctor_placeholders() -> None:
    pkv = ValidatedPkvAntwort(
        patient_first_name="Max",
        doctor_name="Dr. Testarzt F",
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("100.00"),
        erstattungsbetrag_eur=Decimal("85.50"),
        rechnungsnummer="R-123",
        betreffender_termin=date(2024, 3, 1),
    )
    config = _make_config(
        pattern="{date}_{patient}_{doctor}_{doctor_last_name}_{total_amount_eur}.pdf"
    )
    filename = generate_pkv_filename(pkv, config)
    assert filename == "2024_03_15_Max_Dr._Testarzt_F_F_85,50.pdf"


def test_generate_pkv_filename_no_doctor_fallback() -> None:
    pkv = ValidatedPkvAntwort(
        patient_first_name="Anna",
        doctor_name=None,
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("60.00"),
        erstattungsbetrag_eur=Decimal("50.00"),
        rechnungsnummer="R-456",
        betreffender_termin=None,
    )
    config = _make_config(
        pattern="{date}_{patient}_{doctor}_{doctor_last_name}_{total_amount_eur}.pdf"
    )
    filename = generate_pkv_filename(pkv, config)
    assert filename == "2024_03_15_Anna_Unbekannt_Unbekannt_50,00.pdf"


def test_generate_pkv_filename_uses_invoice_topic() -> None:
    pkv = ValidatedPkvAntwort(
        patient_first_name="Max",
        doctor_name="Dr. Testarzt A",
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("100.00"),
        erstattungsbetrag_eur=Decimal("85.00"),
        rechnungsnummer="R-123",
        betreffender_termin=date(2024, 3, 1),
    )
    config = _make_config()
    filename = generate_pkv_filename(pkv, config, invoice_topic="Kontrolle von Wachstum")
    assert filename == "2024_03_15_Max_PKV_Kontrolle_von_Wachstum.pdf"


def test_generate_unique_pkv_path_avoids_collision(tmp_path: Path) -> None:
    pkv = ValidatedPkvAntwort(
        patient_first_name="Max",
        doctor_name="Dr. Testarzt",
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("100.00"),
        erstattungsbetrag_eur=Decimal("85.00"),
        rechnungsnummer="R-123",
        betreffender_termin=date(2024, 3, 1),
    )
    config = _make_config()
    expected = tmp_path / "2024_03_15_Max_PKV_Dr._Testarzt.pdf"
    expected.write_text("existing")

    path = generate_unique_pkv_path(pkv, config, tmp_path)
    assert path is not None
    assert path.name == "2024_03_15_Max_PKV_Dr._Testarzt_2.pdf"


def test_generate_unique_pkv_path_disabled() -> None:
    pkv = ValidatedPkvAntwort(
        patient_first_name="Max",
        doctor_name="Dr. Testarzt",
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("100.00"),
        erstattungsbetrag_eur=Decimal("85.00"),
        rechnungsnummer="R-123",
        betreffender_termin=date(2024, 3, 1),
    )
    config = _make_config(enabled=False)
    path = generate_unique_pkv_path(pkv, config, Path("/tmp"))
    assert path is None
