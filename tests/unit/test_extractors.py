import pytest

from health_importer.ai.extractors import (
    ExtractionError,
    extract_invoice_from_text,
    extract_kassen_ruckmeldung_from_text,
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


def test_text_extractors_send_no_format_schema(monkeypatch) -> None:
    # Ollama 0.33.3 lets the model omit optional properties under the grammar it
    # builds from `format`. A real OeGK response reading "Behandlerin: Dr.
    # Testarzt Zeta" came back with no doctor_name key at all, pydantic
    # filled the null default, and Kassen matching capped at 0.857 -- every OeGK
    # response went to review. fc4ea60 dropped the schema on vision calls only.
    seen = []

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def chat(self, messages, **kwargs):
            seen.append(kwargs)
            return _KASSEN_JSON

    monkeypatch.setattr("health_importer.ai.extractors.OllamaTextClient", FakeClient)

    extraction = extract_kassen_ruckmeldung_from_text(
        {"pages": [{"page_number": 1, "text": "Behandlerin: Dr. Testarzt Zeta"}]},
        model="qwen3.6:35b-a3b-q8_0",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
    )

    assert seen == [{}]
    assert extraction.doctor_name.value == "Dr. Testarzt Zeta"


def test_kassen_text_extraction_repairs_invalid_json(monkeypatch) -> None:
    # Without the grammar nothing guarantees well-formed JSON any more, so the
    # repair loop is what replaces that guarantee on the text path too.
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = ["kein json", _KASSEN_JSON]

        def chat(self, messages, **kwargs):
            calls.append(messages)
            return self.responses.pop(0)

    monkeypatch.setattr("health_importer.ai.extractors.OllamaTextClient", FakeClient)

    extraction = extract_kassen_ruckmeldung_from_text(
        {"pages": [{"page_number": 1, "text": "ORIGINAL KASSEN TEXT"}]},
        model="qwen3.6:35b-a3b-q8_0",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
    )

    assert extraction.doctor_name.value == "Dr. Testarzt Zeta"
    assert "ORIGINAL KASSEN TEXT" in calls[1][1]["content"]


_KASSEN_JSON = """
{
  "document_type": {"value": "krankenkasse_antwort", "confidence": 0.98, "evidence": "OEGK", "page": 1},
  "patient_first_name": {"value": "Nora", "confidence": 0.95, "evidence": "Patientin: Nora", "page": 1},
  "doctor_name": {"value": "Dr. Testarzt Zeta", "confidence": 0.95, "evidence": "Behandlerin: Dr. Testarzt Zeta", "page": 1},
  "erstattungsbetrag_eur": {"value": 63.05, "confidence": 0.95, "evidence": "63,05 Euro erstattet", "page": 1}
}
"""
