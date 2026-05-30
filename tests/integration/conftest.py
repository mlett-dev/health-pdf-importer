from __future__ import annotations

import json
from pathlib import Path

import pytest

from health_importer.config import (
    AnytypeConfig,
    EmailConfig,
    FileNamingConfig,
    KassenFileNamingConfig,
    KassenMatchConfig,
)


def _write_pdf(path: Path, text: str) -> None:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


@pytest.fixture
def dry_run_config(tmp_path: Path) -> AnytypeConfig:
    return AnytypeConfig(
        space_id="test-space-id",
        collection_name="Wahlarzt Rechnungen",
        collection_id="test-collection-id",
        custom_type_name="Wahlarztrechnung",
        custom_type_key="wahlarztrechnung",
        dry_run=True,
        gkk_property_id="test-gkk-id",
        pkv_property_id="test-pkv-id",
        pkv_eingereicht_property_id="test-pkv-eingereicht-id",
        attachment_property_id="test-attachment-id",
        done_property_id="test-done-id",
        patient_tag_property_id="test-patient-tag-id",
        amount_property_id="test-amount-id",
        date_property_id="test-date-id",
        doctor_property_id="test-doctor-id",
    )


@pytest.fixture
def file_naming() -> FileNamingConfig:
    return FileNamingConfig(
        pattern="{date}_{patient}_{topic}.pdf",
        date_format="%Y_%m_%d",
        max_topic_length=60,
    )


@pytest.fixture
def kassen_file_naming() -> KassenFileNamingConfig:
    return KassenFileNamingConfig(
        enabled=True,
        pattern="{date}_{patient}_Kasse.pdf",
        date_format="%Y_%m_%d",
        max_topic_length=60,
    )


@pytest.fixture
def kassen_match() -> KassenMatchConfig:
    return KassenMatchConfig(auto_match_min=0.90, review_match_min=0.60)


@pytest.fixture
def email_config(tmp_path: Path) -> EmailConfig:
    return EmailConfig(
        enabled=False,
        provider="file_only",
        draft_folder=tmp_path / "drafts",
        pkv_recipient="pkv-service@example.invalid",
        pkv_subject_template="Einreichung — {patient} — {date}",
        pkv_body_template="Sehr geehrte Damen und Herren,\n\n{details}\n\n",
        pkv_sender_name="",
        pkv_sender_policy_number="",
        smtp_config=None,
    )


@pytest.fixture
def invoice_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "invoice.pdf"
    _write_pdf(
        path,
        (
            "Honorarnote Rechnung Patient Max Ordination 10.05.2026 "
            "Betrag EUR 120 Leistung Kontrolle " * 40
        ),
    )
    return path


@pytest.fixture
def kassen_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "kasse.pdf"
    _write_pdf(
        path,
        (
            "Bescheid Krankenkasse Max Erstattungsbetrag 85,00 EUR "
            "Aktenzeichen XY123 Bescheidsdatum 15.05.2026 " * 20
        ),
    )
    return path


@pytest.fixture
def pkv_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "pkv.pdf"
    _write_pdf(
        path,
        (
            "Pkv Antwort Max Erstattungsbetrag 42,50 EUR "
            "Datum 20.05.2026 Rechnungsnummer R-456 " * 20
        ),
    )
    return path


class FakeOllamaClient:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)

    def chat(self, messages):
        return self.responses.pop(0)


def fake_ollama_client(responses: list[str]):
    shared = list(responses)

    class Client:
        def __init__(self, **kwargs):
            self.responses = shared

        def chat(self, messages):
            return self.responses.pop(0)

    return Client


def _invoice_responses() -> list[str]:
    return [
        json.dumps(
            {
                "document_type": {
                    "value": "honorarnote",
                    "confidence": 0.9,
                    "evidence": "Honorarnote",
                    "page": 1,
                },
                "patient_first_name": {
                    "value": "Max",
                    "confidence": 0.9,
                    "evidence": "Patient Max",
                    "page": 1,
                },
                "doctor_name": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
                "appointment_date": {
                    "value": "2026-05-10",
                    "confidence": 0.9,
                    "evidence": "10.05.2026",
                    "page": 1,
                },
                "invoice_date": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
                "topic": {
                    "value": "Kontrolle",
                    "confidence": 0.9,
                    "evidence": "Kontrolle",
                    "page": 1,
                },
                "total_amount_eur": {
                    "value": 120.0,
                    "confidence": 0.9,
                    "evidence": "EUR 120",
                    "page": 1,
                },
                "warnings": [],
                "missing_fields": [],
            }
        ),
        json.dumps({"status": "valid", "issues": [], "confidence": 0.9}),
    ]


def _kassen_responses() -> list[str]:
    return [
        json.dumps(
            {
                "document_type": {
                    "value": "krankenkasse_antwort",
                    "confidence": 0.95,
                    "evidence": "Krankenkasse",
                    "page": 1,
                },
                "patient_first_name": {
                    "value": "Max",
                    "confidence": 0.95,
                    "evidence": "Max",
                    "page": 1,
                },
                "doctor_name": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
                "bescheids_datum": {
                    "value": "2026-05-15",
                    "confidence": 0.9,
                    "evidence": "15.05.2026",
                    "page": 1,
                },
                "aufwendungsbetrag_eur": {
                    "value": None,
                    "confidence": 0.0,
                    "evidence": None,
                    "page": None,
                },
                "erstattungsbetrag_eur": {
                    "value": "85.00",
                    "confidence": 0.95,
                    "evidence": "85,00 EUR",
                    "page": 1,
                },
                "rechnungsnummer": {
                    "value": None,
                    "confidence": 0.0,
                    "evidence": None,
                    "page": None,
                },
                "aktenzeichen": {
                    "value": "XY123",
                    "confidence": 0.9,
                    "evidence": "XY123",
                    "page": 1,
                },
                "betreffender_termin": {
                    "value": None,
                    "confidence": 0.0,
                    "evidence": None,
                    "page": None,
                },
                "warnings": [],
                "missing_fields": [],
            }
        ),
        json.dumps({"status": "valid", "issues": [], "confidence": 0.95}),
    ]


def _pkv_responses() -> list[str]:
    return [
        json.dumps(
            {
                "document_type": {
                    "value": "pkv_antwort",
                    "confidence": 0.95,
                    "evidence": "Pkv",
                    "page": 1,
                },
                "patient_first_name": {
                    "value": "Max",
                    "confidence": 0.95,
                    "evidence": "Max",
                    "page": 1,
                },
                "erstattungsbetrag_eur": {
                    "value": "42.50",
                    "confidence": 0.95,
                    "evidence": "42,50 EUR",
                    "page": 1,
                },
                "bescheids_datum": {
                    "value": None,
                    "confidence": 0.0,
                    "evidence": None,
                    "page": None,
                },
                "aufwendungsbetrag_eur": {
                    "value": None,
                    "confidence": 0.0,
                    "evidence": None,
                    "page": None,
                },
                "rechnungsnummer": {
                    "value": "R-456",
                    "confidence": 0.9,
                    "evidence": "R-456",
                    "page": 1,
                },
                "betreffender_termin": {
                    "value": None,
                    "confidence": 0.0,
                    "evidence": None,
                    "page": None,
                },
                "warnings": [],
                "missing_fields": [],
            }
        ),
        json.dumps({"status": "valid", "issues": [], "confidence": 0.95}),
    ]


def _run_once_kwargs(
    tmp_path: Path, dry_run_config: AnytypeConfig, file_naming: FileNamingConfig
) -> dict:
    return {
        "anytype_config": dry_run_config,
        "anytype_dry_run": True,
        "file_naming": file_naming,
        "review_folder": tmp_path / "review",
        "done_folder": tmp_path / "done",
        "error_folder": tmp_path / "error",
        "allow_external_services": True,
    }
