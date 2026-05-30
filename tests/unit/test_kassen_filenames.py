"""Tests for Kassen PDF filename generation."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from health_importer.config import KassenFileNamingConfig
from health_importer.workflow.filenames import generate_kassen_filename, generate_unique_kassen_path
from health_importer.workflow.validation import ValidatedKassenRuckmeldung


def _make_config(**kwargs) -> KassenFileNamingConfig:
    defaults = {
        "enabled": True,
        "pattern": "{date}_{patient}_GKK_{topic}.pdf",
        "date_format": "%Y_%m_%d",
        "max_topic_length": 30,
    }
    defaults.update(kwargs)
    return KassenFileNamingConfig(**defaults)


def test_generate_kassen_filename_basic() -> None:
    kassen = ValidatedKassenRuckmeldung(
        patient_first_name="Max",
        doctor_name="Dr. Testarzt A",
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("100.00"),
        erstattungsbetrag_eur=Decimal("85.00"),
        rechnungsnummer="R-123",
        aktenzeichen="AZ-456",
        betreffender_termin=date(2024, 3, 1),
    )
    config = _make_config()
    filename = generate_kassen_filename(kassen, config)
    assert filename == "2024_03_15_Max_GKK_Dr._Testarzt_A.pdf"


def test_generate_kassen_filename_disabled() -> None:
    kassen = ValidatedKassenRuckmeldung(
        patient_first_name="Max",
        doctor_name="Dr. Testarzt A",
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("100.00"),
        erstattungsbetrag_eur=Decimal("85.00"),
        rechnungsnummer="R-123",
        aktenzeichen="AZ-456",
        betreffender_termin=date(2024, 3, 1),
    )
    config = _make_config(enabled=False)
    filename = generate_kassen_filename(kassen, config)
    assert filename == ""


def test_generate_kassen_filename_no_date() -> None:
    kassen = ValidatedKassenRuckmeldung(
        patient_first_name="Anna",
        doctor_name=None,
        bescheids_datum=None,
        aufwendungsbetrag_eur=Decimal("60.00"),
        erstattungsbetrag_eur=Decimal("50.00"),
        rechnungsnummer="R-456",
        aktenzeichen="AZ-789",
        betreffender_termin=None,
    )
    config = _make_config()
    filename = generate_kassen_filename(kassen, config)
    assert filename == "unknown_date_Anna_GKK_GKK_Rueckmeldung.pdf"


def test_generate_kassen_filename_topic_truncated() -> None:
    kassen = ValidatedKassenRuckmeldung(
        patient_first_name="Max",
        doctor_name="Sehr langer Arztname mit vielen Buchstaben",
        bescheids_datum=date(2024, 1, 1),
        aufwendungsbetrag_eur=Decimal("20.00"),
        erstattungsbetrag_eur=Decimal("10.00"),
        rechnungsnummer="R-789",
        aktenzeichen="AZ-012",
        betreffender_termin=date(2023, 12, 15),
    )
    config = _make_config(max_topic_length=10)
    filename = generate_kassen_filename(kassen, config)
    assert "Sehr_lange" in filename
    assert filename.endswith(".pdf")


def test_generate_unique_kassen_path_avoids_collision(tmp_path: Path) -> None:
    kassen = ValidatedKassenRuckmeldung(
        patient_first_name="Max",
        doctor_name="Dr. Testarzt",
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("100.00"),
        erstattungsbetrag_eur=Decimal("85.00"),
        rechnungsnummer="R-123",
        aktenzeichen="AZ-456",
        betreffender_termin=date(2024, 3, 1),
    )
    config = _make_config()
    # Pre-create a file at the expected destination
    expected = tmp_path / "2024_03_15_Max_GKK_Dr._Testarzt.pdf"
    expected.write_text("existing")

    path = generate_unique_kassen_path(kassen, config, tmp_path)
    assert path is not None
    # unique_destination starts counter at 2
    assert path.name == "2024_03_15_Max_GKK_Dr._Testarzt_2.pdf"


def test_generate_unique_kassen_path_disabled() -> None:
    kassen = ValidatedKassenRuckmeldung(
        patient_first_name="Max",
        doctor_name="Dr. Testarzt",
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("100.00"),
        erstattungsbetrag_eur=Decimal("85.00"),
        rechnungsnummer="R-123",
        aktenzeichen="AZ-456",
        betreffender_termin=date(2024, 3, 1),
    )
    config = _make_config(enabled=False)
    path = generate_unique_kassen_path(kassen, config, Path("/tmp"))
    assert path is None


def test_generate_kassen_filename_doctor_placeholders() -> None:
    kassen = ValidatedKassenRuckmeldung(
        patient_first_name="Max",
        doctor_name="Dr. Testarzt F",
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("100.00"),
        erstattungsbetrag_eur=Decimal("85.50"),
        rechnungsnummer="R-123",
        aktenzeichen="AZ-456",
        betreffender_termin=date(2024, 3, 1),
    )
    config = _make_config(
        pattern="{date}_{patient}_{doctor}_{doctor_last_name}_{total_amount_eur}.pdf"
    )
    filename = generate_kassen_filename(kassen, config)
    assert filename == "2024_03_15_Max_Dr._Testarzt_F_F_85,50.pdf"


def test_generate_kassen_filename_no_doctor_fallback() -> None:
    kassen = ValidatedKassenRuckmeldung(
        patient_first_name="Anna",
        doctor_name=None,
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("60.00"),
        erstattungsbetrag_eur=Decimal("50.00"),
        rechnungsnummer="R-456",
        aktenzeichen="AZ-789",
        betreffender_termin=None,
    )
    config = _make_config(
        pattern="{date}_{patient}_{doctor}_{doctor_last_name}_{total_amount_eur}.pdf"
    )
    filename = generate_kassen_filename(kassen, config)
    assert filename == "2024_03_15_Anna_Unbekannt_Unbekannt_50,00.pdf"


def test_generate_kassen_filename_uses_invoice_topic() -> None:
    kassen = ValidatedKassenRuckmeldung(
        patient_first_name="Max",
        doctor_name="Dr. Testarzt A",
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("100.00"),
        erstattungsbetrag_eur=Decimal("85.00"),
        rechnungsnummer="R-123",
        aktenzeichen="AZ-456",
        betreffender_termin=date(2024, 3, 1),
    )
    config = _make_config()
    filename = generate_kassen_filename(kassen, config, invoice_topic="Kontrolle von Wachstum")
    assert filename == "2024_03_15_Max_GKK_Kontrolle_von_Wachstum.pdf"


def test_generate_kassen_filename_service_date_placeholder() -> None:
    kassen = ValidatedKassenRuckmeldung(
        patient_first_name="Max",
        doctor_name="Dr. Testarzt A",
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("100.00"),
        erstattungsbetrag_eur=Decimal("85.00"),
        rechnungsnummer="R-123",
        aktenzeichen="AZ-456",
        betreffender_termin=date(2024, 3, 1),
    )
    config = _make_config(pattern="{service_date}_{patient}_{topic}.pdf")
    filename = generate_kassen_filename(kassen, config)
    assert filename == "2024_03_01_Max_Dr._Testarzt_A.pdf"


def test_generate_kassen_filename_service_date_fallback() -> None:
    kassen = ValidatedKassenRuckmeldung(
        patient_first_name="Anna",
        doctor_name=None,
        bescheids_datum=date(2024, 3, 15),
        aufwendungsbetrag_eur=Decimal("60.00"),
        erstattungsbetrag_eur=Decimal("50.00"),
        rechnungsnummer="R-456",
        aktenzeichen="AZ-789",
        betreffender_termin=None,
    )
    config = _make_config(pattern="{service_date}_{patient}_{topic}.pdf")
    filename = generate_kassen_filename(kassen, config)
    assert filename == "unknown_date_Anna_GKK_Rueckmeldung.pdf"
