from pathlib import Path

from health_importer.ai.extractors import (
    consolidate_vision_pages,
    extract_invoice_from_vision_pages,
    verify_invoice_values_vision,
)
from health_importer.ai.schemas import VisionPageExtraction


def test_extract_invoice_from_vision_pages_validates_page_json(monkeypatch, tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(
        "health_importer.ai.extractors.OllamaVisionClient",
        _vision_client(
            [
                """
                {
                  "page_number": 1,
                  "document_type": {"value": "honorarnote", "confidence": 0.9, "evidence": "Honorarnote", "page": 1},
                  "patient_first_name": {"value": "Max", "confidence": 0.9, "evidence": "Max", "page": 1},
                  "doctor_name": {"value": null, "confidence": 0.0, "evidence": null, "page": 1},
                  "appointment_date": {"value": null, "confidence": 0.0, "evidence": null, "page": 1},
                  "invoice_date": {"value": null, "confidence": 0.0, "evidence": null, "page": 1},
                  "topic": {"value": "Kontrolle", "confidence": 0.7, "evidence": "Kontrolle", "page": 1},
                  "total_amount_eur": {"value": 120.0, "confidence": 0.9, "evidence": "EUR 120", "page": 1},
                  "warnings": []
                }
                """
            ]
        ),
    )

    results = extract_invoice_from_vision_pages(
        [(1, image)],
        model="qwen3.6:35b-a3b-q8_0",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
    )

    assert results[0].patient_first_name.value == "Max"
    assert results[0].page_number == 1


def test_consolidate_vision_pages_chooses_highest_confidence_values() -> None:
    pages = [
        _page("Max", 0.6, None, 0.0),
        _page("Max", 0.9, 120.0, 0.8),
    ]

    extraction = consolidate_vision_pages(pages)

    assert extraction.patient_first_name.confidence == 0.9
    assert extraction.total_amount_eur.value == 120.0


def test_verify_invoice_values_vision_validates_value_json(monkeypatch, tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(
        "health_importer.ai.extractors.OllamaVisionClient",
        _vision_client(
            [
                """
                {
                  "amount_found": true,
                  "date_found": true,
                  "amount_evidence": "EUR 120,00",
                  "date_evidence": "08.05.2026",
                  "warnings": [],
                  "confidence": 0.9
                }
                """
            ]
        ),
    )

    result = verify_invoice_values_vision(
        [(1, image)],
        amount="120.00",
        target_date="2026-05-08",
        model="qwen3.6:35b-a3b-q8_0",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
    )

    assert result is not None
    assert result.amount_found is True
    assert result.date_found is True
    assert result.amount_evidence == "EUR 120,00"


def _page(patient, patient_confidence, amount, amount_confidence):
    return VisionPageExtraction.model_validate(
        {
            "page_number": 1,
            "document_type": _field("honorarnote", 0.8, "Honorarnote"),
            "patient_first_name": _field(patient, patient_confidence, "Patient"),
            "doctor_name": _field(None, 0.0, None),
            "appointment_date": _field("2026-05-08", 0.8, "08.05.2026"),
            "invoice_date": _field(None, 0.0, None),
            "topic": _field("Kontrolle", 0.8, "Kontrolle"),
            "total_amount_eur": _field(amount, amount_confidence, "EUR 120" if amount else None),
            "warnings": [],
        }
    )


def _field(value, confidence, evidence):
    return {"value": value, "confidence": confidence, "evidence": evidence, "page": 1}


def _vision_client(responses):
    class FakeVisionClient:
        def __init__(self, **kwargs):
            self.responses = list(responses)

        def describe_image(self, image_path, prompt):
            return self.responses.pop(0)

        def chat_with_images(self, images, prompt, *, response_format=None, num_predict=2048):
            return self.responses.pop(0)

    return FakeVisionClient
