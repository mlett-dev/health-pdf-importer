import pytest

from health_importer.ai.extractors import ExtractionError, verify_extraction
from health_importer.ai.schemas import InvoiceExtraction, VerificationStatus


def test_verify_extraction_returns_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "health_importer.ai.extractors.OllamaTextClient",
        _client(['{"status":"needs_review","issues":["Betrag mehrfach"],"confidence":0.7}']),
    )

    result = verify_extraction(
        "Gesamtbetrag EUR 120",
        _extraction(),
        model="qwen3.6:35b-a3b-q8_0",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
    )

    assert result is not None
    assert result.status == VerificationStatus.NEEDS_REVIEW
    assert result.issues == ["Betrag mehrfach"]


def test_verify_extraction_can_be_disabled() -> None:
    assert (
        verify_extraction(
            "Text",
            _extraction(),
            model="qwen3.6:35b-a3b-q8_0",
            base_url="http://127.0.0.1:11434",
            timeout_seconds=30,
            enabled=False,
        )
        is None
    )


def test_verify_extraction_rejects_invalid_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "health_importer.ai.extractors.OllamaTextClient",
        _client(['{"status":"maybe","issues":[],"confidence":0.7}']),
    )

    with pytest.raises(ExtractionError):
        verify_extraction(
            "Text",
            _extraction(),
            model="qwen3.6:35b-a3b-q8_0",
            base_url="http://127.0.0.1:11434",
            timeout_seconds=30,
        )


def _extraction() -> InvoiceExtraction:
    return InvoiceExtraction.model_validate(
        {
            "document_type": _field("honorarnote", "Honorarnote"),
            "patient_first_name": _field("Max", "Max"),
            "doctor_name": _field(None, None),
            "appointment_date": _field("2026-05-08", "08.05.2026"),
            "invoice_date": _field(None, None),
            "topic": _field("Kontrolle", "Kontrolle"),
            "total_amount_eur": _field(120.0, "EUR 120"),
        }
    )


def _field(value, evidence):
    return {"value": value, "confidence": 0.8, "evidence": evidence, "page": 1}


def _client(responses):
    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = list(responses)

        def chat(self, messages):
            return self.responses.pop(0)

    return FakeClient
