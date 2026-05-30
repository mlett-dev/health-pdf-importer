"""End-to-End test for ÖGK-style Kassen extraction with mocked LLM.

Uses the realistic ÖGK example text and validates the full pipeline:
extract_kassen_ruckmeldung_from_text → KassenRuckmeldungExtraction → validate_kassen_ruckmeldung
"""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from health_importer.ai.extractors import extract_kassen_ruckmeldung_from_text
from health_importer.workflow.validation import validate_kassen_ruckmeldung

# Realistic ÖGK example text (from docs/Beispiel_ÖGK_Antwort.txt)
OEGK_TEXT = """Herr
Max Mustermann
Teststrasse XX
0000 Teststadt

Versicherungsnummer: TEST-VNR-000000
Datum: 15. April 2026
Unser Zeichen: WAHI
Ihre Ansprechperson: Wahlarzthilfe

Bestätigung über die Kostenerstattung
Patientin: TEST VNR 0001 Anna Musterfrau
Versicherter: TEST VNR 0002 Max Mustermann
Behandlerin: Dr. Testarzt OEGK
Für Ihre Aufwendungen in der Höhe von 210,00 Euro für Leistungen vom 08.04.2026 bis
08.04.2026 haben wir Ihnen 146,86 Euro erstattet.
Die Überweisung erfolgte am 14.04.2026 auf nachstehende Bankverbindung:
IBAN: ATXX XXXX XXXX XXXX XXXX
Bankinstitut: Erste Bank der oesterreichischen Sparkassen AG
Bei Inanspruchnahme von Wahlbehandlern (Behandler ohne Kassenvertrag) können von der
ÖGK nur jene Leistungen erstattet werden, für die wir nach den rechtlichen Bestimmungen
leistungszuständig sind. Die Kostenerstattung erfolgt in der Höhe von 80 Prozent der
Vertragspartnertarife (bei Pauschalbeträgen gibt es Sonderregelungen) oder in Form von
Kostenzuschüssen, wenn keine Vertragstarife bestehen.
Da Wahlbehandler bei ihrer Leistungserbringung und Honorargestaltung ungebunden sind,
können hohe Restkosten bleiben.
Diese Bestätigung kann auch für die Erklärung zur Arbeitnehmerveranlagung an das zuständige
Finanzamt und/oder für eine Privatversicherung verwendet werden.
Die eingereichten Unterlagen verbleiben in digitaler Form bei der ÖGK.
Freundliche Grüße
Österreichische Gesundheitskasse."""


# Simulated LLM response (perfect extraction) for the ÖGK text
OEGK_LLM_RESPONSE = json.dumps(
    {
        "document_type": {
            "value": "krankenkasse_antwort",
            "confidence": 0.98,
            "evidence": "Bestätigung über die Kostenerstattung",
        },
        "patient_first_name": {
            "value": "Anna",
            "confidence": 0.95,
            "evidence": "Patientin: TEST VNR 0001 Anna Musterfrau",
        },
        "doctor_name": {
            "value": "Dr. Testarzt OEGK",
            "confidence": 0.95,
            "evidence": "Behandlerin: Dr. Testarzt OEGK",
        },
        "bescheids_datum": {
            "value": "2026-04-15",
            "confidence": 0.92,
            "evidence": "Datum: 15. April 2026",
        },
        "aufwendungsbetrag_eur": {
            "value": 210.0,
            "confidence": 0.98,
            "evidence": "Für Ihre Aufwendungen in der Höhe von 210,00 Euro",
        },
        "erstattungsbetrag_eur": {
            "value": 146.86,
            "confidence": 0.97,
            "evidence": "146,86 Euro erstattet",
        },
        "rechnungsnummer": {
            "value": None,
            "confidence": 0.0,
        },
        "aktenzeichen": {
            "value": "WAHI",
            "confidence": 0.90,
            "evidence": "Unser Zeichen: WAHI",
        },
        "betreffender_termin": {
            "value": "2026-04-08",
            "confidence": 0.96,
            "evidence": "Leistungen vom 08.04.2026",
        },
        "warnings": [],
        "missing_fields": [],
    },
    ensure_ascii=False,
)


def test_ogk_text_prompt_contains_key_fields() -> None:
    """Verify the raw ÖGK text contains the expected amounts and dates."""
    assert "210,00 Euro" in OEGK_TEXT
    assert "146,86 Euro erstattet" in OEGK_TEXT
    assert "08.04.2026" in OEGK_TEXT
    assert "Patientin:" in OEGK_TEXT
    assert "Behandlerin: Dr. Testarzt OEGK" in OEGK_TEXT
    assert "Bestätigung über die Kostenerstattung" in OEGK_TEXT


def test_ogk_extraction_with_mock_llm() -> None:
    """Full pipeline test: mock LLM returns perfect ÖGK JSON, verify extraction."""
    pdf_text = {"pages": [{"page_number": 1, "text": OEGK_TEXT}]}

    with patch("health_importer.ai.extractors.OllamaTextClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.chat.return_value = OEGK_LLM_RESPONSE
        MockClient.return_value = mock_instance

        extraction = extract_kassen_ruckmeldung_from_text(
            pdf_text,
            model="llama3.2:3b",
            base_url="http://localhost:11434",
            timeout_seconds=300,
        )

    # --- Schema assertions ---
    assert extraction.document_type.value is not None
    assert extraction.document_type.value.value == "krankenkasse_antwort"
    assert extraction.patient_first_name.value == "Anna"
    assert extraction.doctor_name.value == "Dr. Testarzt OEGK"
    assert extraction.bescheids_datum.value == "2026-04-15"
    assert extraction.aufwendungsbetrag_eur.value == 210.0
    assert extraction.erstattungsbetrag_eur.value == 146.86
    assert extraction.aktenzeichen.value == "WAHI"
    assert extraction.betreffender_termin.value == "2026-04-08"
    assert extraction.rechnungsnummer.value is None


def test_ogk_extraction_validation_with_mock_llm() -> None:
    """Validate the mocked ÖGK extraction produces a passing validation result."""
    pdf_text = {"pages": [{"page_number": 1, "text": OEGK_TEXT}]}

    with patch("health_importer.ai.extractors.OllamaTextClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.chat.return_value = OEGK_LLM_RESPONSE
        MockClient.return_value = mock_instance

        extraction = extract_kassen_ruckmeldung_from_text(
            pdf_text,
            model="llama3.2:3b",
            base_url="http://localhost:11434",
            timeout_seconds=300,
        )

    result = validate_kassen_ruckmeldung(
        extraction,
        allowed_patients=("Anna", "Max", "Anna"),
        required_confidence_min=0.8,
    )

    assert result.ok is True
    assert result.kassen is not None
    assert result.kassen.patient_first_name == "Anna"
    assert result.kassen.doctor_name == "Dr. Testarzt OEGK"
    assert result.kassen.aufwendungsbetrag_eur == Decimal("210.0")
    assert result.kassen.erstattungsbetrag_eur == Decimal("146.86")
    assert result.kassen.aktenzeichen == "WAHI"
    assert result.kassen.betreffender_termin is not None


def test_ogk_extraction_rejected_for_wrong_patient() -> None:
    """If the LLM extracted 'Anna' but only 'Max' is allowed, reject."""
    pdf_text = {"pages": [{"page_number": 1, "text": OEGK_TEXT}]}

    with patch("health_importer.ai.extractors.OllamaTextClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.chat.return_value = OEGK_LLM_RESPONSE
        MockClient.return_value = mock_instance

        extraction = extract_kassen_ruckmeldung_from_text(
            pdf_text,
            model="llama3.2:3b",
            base_url="http://localhost:11434",
            timeout_seconds=300,
        )

    result = validate_kassen_ruckmeldung(
        extraction,
        allowed_patients=("Max",),
        required_confidence_min=0.8,
    )

    assert result.ok is False
    assert "patient_first_name_not_allowed:Anna" in result.errors
