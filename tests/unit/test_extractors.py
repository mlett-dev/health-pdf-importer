import pytest

from health_importer.ai.extractors import (
    ExtractionError,
    extract_invoice_from_text,
    extract_pkv_antwort_from_text,
)


def test_extract_invoice_from_text_validates_model_json(monkeypatch) -> None:
    responses = [
        """
        {
          "document_type": {"value": "honorarnote", "confidence": 0.9, "evidence": "Honorarnote", "page": 1},
          "patient_first_name": {"value": "Max", "confidence": 0.9, "evidence": "Patientin: Max", "page": 1},
          "doctor_name": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
          "appointment_date": {"value": "2026-05-08", "confidence": 0.8, "evidence": "08.05.2026", "page": 1},
          "invoice_date": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
          "topic": {"value": "Kontrolle", "confidence": 0.8, "evidence": "Kontrolle", "page": 1},
          "total_amount_eur": {"value": 120.0, "confidence": 0.9, "evidence": "EUR 120,00", "page": 1},
          "warnings": [],
          "missing_fields": []
        }
        """
    ]
    monkeypatch.setattr("health_importer.ai.extractors.OllamaTextClient", _client(responses))

    extraction = extract_invoice_from_text(
        {"pages": [{"page_number": 1, "text": "Honorarnote Patientin: Max"}]},
        model="qwen3.6:35b-a3b-q8_0",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
    )

    assert extraction.patient_first_name.value == "Max"
    assert extraction.is_ready_for_code_validation() is True


def test_extract_invoice_from_text_retries_invalid_json(monkeypatch) -> None:
    responses = [
        "kein json",
        """
        {
          "document_type": {"value": "sonstiges", "confidence": 0.5, "evidence": "Text", "page": 1},
          "patient_first_name": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
          "doctor_name": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
          "appointment_date": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
          "invoice_date": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
          "topic": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
          "total_amount_eur": {"value": null, "confidence": 0.0, "evidence": null, "page": null}
        }
        """,
    ]
    monkeypatch.setattr("health_importer.ai.extractors.OllamaTextClient", _client(responses))

    extraction = extract_invoice_from_text(
        {"pages": [{"page_number": 1, "text": "Text"}]},
        model="qwen3.6:35b-a3b-q8_0",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
    )

    assert extraction.document_type.value == "sonstiges"


def test_extract_invoice_from_text_fails_after_retry(monkeypatch) -> None:
    monkeypatch.setattr("health_importer.ai.extractors.OllamaTextClient", _client(["no", "still no"]))

    with pytest.raises(ExtractionError):
        extract_invoice_from_text(
            {"pages": [{"page_number": 1, "text": "Text"}]},
            model="qwen3.6:35b-a3b-q8_0",
            base_url="http://127.0.0.1:11434",
            timeout_seconds=30,
        )


def test_extract_pkv_antwort_from_text_validates_model_json(monkeypatch) -> None:
    responses = [
        """
        {
          "document_type": {"value": "pkv_antwort", "confidence": 0.9, "evidence": "Pkv", "page": 1},
          "patient_first_name": {"value": "Max", "confidence": 0.9, "evidence": "Max", "page": 1},
          "erstattungsbetrag_eur": {"value": 42.5, "confidence": 0.9, "evidence": "42,50", "page": 1},
          "bescheids_datum": {"value": "2026-05-10", "confidence": 0.9, "evidence": "10.05.2026", "page": 1},
          "aufwendungsbetrag_eur": {"value": 120.0, "confidence": 0.8, "evidence": "120,00", "page": 1},
          "rechnungsnummer": {"value": "R-1", "confidence": 0.8, "evidence": "R-1", "page": 1},
          "betreffender_termin": {"value": "2026-05-08", "confidence": 0.8, "evidence": "08.05.2026", "page": 1},
          "warnings": [],
          "missing_fields": []
        }
        """
    ]
    monkeypatch.setattr("health_importer.ai.extractors.OllamaTextClient", _client(responses))

    extraction = extract_pkv_antwort_from_text(
        {"pages": [{"page_number": 1, "text": "Pkv Antwort Max"}]},
        model="qwen3.6:35b-a3b-q8_0",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
    )

    assert extraction.document_type.value == "pkv_antwort"
    assert extraction.patient_first_name.value == "Max"
    assert extraction.aufwendungsbetrag_eur.value == 120.0


def test_extract_pkv_antwort_retry_keeps_original_text(monkeypatch) -> None:
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = [
                "kein json",
                """
                {
                  "document_type": {"value": "pkv_antwort", "confidence": 0.9, "evidence": "Pkv", "page": 1},
                  "patient_first_name": {"value": "Max", "confidence": 0.9, "evidence": "Max", "page": 1},
                  "erstattungsbetrag_eur": {"value": 42.5, "confidence": 0.9, "evidence": "42,50", "page": 1}
                }
                """,
            ]

        def chat(self, messages, **kwargs):
            calls.append(messages)
            return self.responses.pop(0)

    monkeypatch.setattr("health_importer.ai.extractors.OllamaTextClient", FakeClient)

    extraction = extract_pkv_antwort_from_text(
        {"pages": [{"page_number": 1, "text": "ORIGINAL PKV TEXT"}]},
        model="qwen3.6:35b-a3b-q8_0",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
    )

    assert extraction.erstattungsbetrag_eur.value == 42.5
    assert "ORIGINAL PKV TEXT" in calls[1][1]["content"]


def test_extract_pkv_antwort_from_text_fails_after_retry(monkeypatch) -> None:
    monkeypatch.setattr("health_importer.ai.extractors.OllamaTextClient", _client(["no", "still no"]))

    with pytest.raises(ExtractionError):
        extract_pkv_antwort_from_text(
            {"pages": [{"page_number": 1, "text": "Pkv"}]},
            model="qwen3.6:35b-a3b-q8_0",
            base_url="http://127.0.0.1:11434",
            timeout_seconds=30,
        )


def _client(responses):
    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = list(responses)

        def chat(self, messages):
            return self.responses.pop(0)

    return FakeClient
