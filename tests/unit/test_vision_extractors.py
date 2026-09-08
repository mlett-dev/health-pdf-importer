import json
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import pytest

from health_importer.ai.extractors import (
    ExtractionError,
    verify_extraction_vision,
    consolidate_vision_pages,
    extract_kassen_ruckmeldung_from_vision_pages,
    extract_invoice_from_vision_pages,
    extract_pkv_antwort_from_vision_pages,
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


def test_extract_kassen_ruckmeldung_from_vision_pages_validates_json(
    monkeypatch, tmp_path: Path
) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(
        "health_importer.ai.extractors.OllamaVisionClient",
        _vision_client(
            [
                """
                {
                  "document_type": {"value": "krankenkasse_antwort", "confidence": 0.9, "evidence": "Bescheid", "page": 1},
                  "patient_first_name": {"value": "Max", "confidence": 0.9, "evidence": "Max", "page": 1},
                  "doctor_name": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
                  "bescheids_datum": {"value": "2026-05-10", "confidence": 0.9, "evidence": "10.05.2026", "page": 1},
                  "aufwendungsbetrag_eur": {"value": 120.0, "confidence": 0.8, "evidence": "120,00", "page": 1},
                  "erstattungsbetrag_eur": {"value": 42.5, "confidence": 0.9, "evidence": "42,50", "page": 1},
                  "rechnungsnummer": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
                  "aktenzeichen": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
                  "betreffender_termin": {"value": "2026-05-08", "confidence": 0.8, "evidence": "08.05.2026", "page": 1},
                  "warnings": [],
                  "missing_fields": []
                }
                """
            ]
        ),
    )

    extraction = extract_kassen_ruckmeldung_from_vision_pages(
        [(1, image)],
        model="qwen3.6:35b-a3b-q8_0",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
    )

    assert extraction.document_type.value == "krankenkasse_antwort"
    assert extraction.patient_first_name.value == "Max"
    assert extraction.erstattungsbetrag_eur.value == 42.5


def test_extract_pkv_antwort_from_vision_pages_validates_json(
    monkeypatch, tmp_path: Path
) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(
        "health_importer.ai.extractors.OllamaVisionClient",
        _vision_client(
            [
                """
                {
                  "document_type": {"value": "pkv_antwort", "confidence": 0.9, "evidence": "Pkv", "page": 1},
                  "patient_first_name": {"value": "Max", "confidence": 0.9, "evidence": "Max", "page": 1},
                  "doctor_name": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
                  "erstattungsbetrag_eur": {"value": 42.5, "confidence": 0.9, "evidence": "42,50", "page": 1},
                  "bescheids_datum": {"value": "2026-05-10", "confidence": 0.9, "evidence": "10.05.2026", "page": 1},
                  "aufwendungsbetrag_eur": {"value": 120.0, "confidence": 0.8, "evidence": "120,00", "page": 1},
                  "rechnungsnummer": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
                  "betreffender_termin": {"value": "2026-05-08", "confidence": 0.8, "evidence": "08.05.2026", "page": 1},
                  "warnings": [],
                  "missing_fields": []
                }
                """
            ]
        ),
    )

    extraction = extract_pkv_antwort_from_vision_pages(
        [(1, image)],
        model="qwen3.6:35b-a3b-q8_0",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
    )

    assert extraction.document_type.value == "pkv_antwort"
    assert extraction.patient_first_name.value == "Max"
    assert extraction.erstattungsbetrag_eur.value == 42.5


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


def _vision_client(responses, prompts=None):
    class FakeVisionClient:
        def __init__(self, **kwargs):
            self.responses = list(responses)

        def describe_image(self, image_path, prompt):
            return self.chat_with_images([image_path], prompt)

        def chat_with_images(self, images, prompt, *, response_format=None, num_predict=2048):
            if prompts is not None:
                prompts.append(prompt)
            return self.responses.pop(0)

    return FakeVisionClient


_VALID_PAGE = json.dumps(
    {
        "page_number": 1,
        "document_type": _field("honorarnote", 0.9, "HONORARNOTE"),
        "patient_first_name": _field("Anna", 0.9, "Patient: Anna"),
        "doctor_name": _field("Dr. Test", 0.9, "Dr. Test"),
        "appointment_date": _field("2026-09-02", 0.9, "02.09.2026"),
        "invoice_date": _field(None, 0.0, None),
        "topic": _field("Beratung", 0.9, "Beratung"),
        "total_amount_eur": _field(140.0, 0.9, "140,00"),
    }
)


def test_vision_invoice_accepts_fenced_json_without_schema(tmp_path: Path) -> None:
    # Without a `format` grammar the model wraps its JSON in a ```json fence.
    fenced = f"```json\n{_VALID_PAGE}\n```"
    with patch(
        "health_importer.ai.extractors.OllamaVisionClient", _vision_client([fenced])
    ):
        pages = extract_invoice_from_vision_pages(
            [(1, tmp_path / "p1.png")],
            model="vision",
            base_url="http://127.0.0.1:11434",
            timeout_seconds=5,
        )

    assert pages[0].total_amount_eur.value == 140.0


def test_vision_invoice_reasks_once_on_invalid_json(tmp_path: Path) -> None:
    prompts: list[str] = []
    with patch(
        "health_importer.ai.extractors.OllamaVisionClient",
        _vision_client(["kein JSON, nur Fliesstext", _VALID_PAGE], prompts),
    ):
        pages = extract_invoice_from_vision_pages(
            [(1, tmp_path / "p1.png")],
            model="vision",
            base_url="http://127.0.0.1:11434",
            timeout_seconds=5,
        )

    assert pages[0].doctor_name.value == "Dr. Test"
    assert len(prompts) == 2
    assert "korrigiertem JSON" in prompts[1]
    assert "kein JSON, nur Fliesstext" in prompts[1]


def test_vision_invoice_raises_after_failed_repair(tmp_path: Path) -> None:
    with patch(
        "health_importer.ai.extractors.OllamaVisionClient",
        _vision_client(["kaputt", "immer noch kaputt"]),
    ):
        with pytest.raises(ExtractionError, match="Vision extraction on page 1"):
            extract_invoice_from_vision_pages(
                [(1, tmp_path / "p1.png")],
                model="vision",
                base_url="http://127.0.0.1:11434",
                timeout_seconds=5,
            )


_PAGE_WITHOUT_PATIENT = json.dumps(
    {
        "page_number": 1,
        "document_type": _field("honorarnote", 0.9, "HONORARNOTE"),
        "patient_first_name": {"value": None, "confidence": 0.0, "evidence": None, "page": None},
        "doctor_name": _field("Dr. Testarzt Epsilon", 0.9, "Dr. Testarzt Epsilon"),
        "appointment_date": _field("2026-09-02", 0.9, "02.09.2026"),
        "invoice_date": _field(None, 0.0, None),
        "topic": _field("Beratung", 0.9, "Beratung"),
        "total_amount_eur": _field(140.0, 0.9, "140,00"),
    }
)


def _png(path: Path) -> Path:
    Image.new("RGB", (400, 600), "white").save(path)
    return path


def test_patient_falls_back_to_address_block(tmp_path: Path) -> None:
    # The full page makes the model name the letterhead doctor as addressee;
    # a cropped second pass reads the real recipient.
    address = json.dumps({"first_name": "Katharina", "evidence": "Frau Katharina Musterfrau"})
    with patch(
        "health_importer.ai.extractors.OllamaVisionClient",
        _vision_client([_PAGE_WITHOUT_PATIENT, address]),
    ):
        pages = extract_invoice_from_vision_pages(
            [(1, _png(tmp_path / "p1.png"))],
            model="vision",
            base_url="http://127.0.0.1:11434",
            timeout_seconds=5,
        )

    assert pages[0].patient_first_name.value == "Katharina"
    assert pages[0].patient_first_name.evidence == "Frau Katharina Musterfrau"
    assert pages[0].patient_first_name.confidence == 0.6


def test_patient_fallback_rejects_the_doctor(tmp_path: Path) -> None:
    address = json.dumps({"first_name": "Testarzt", "evidence": "Dr. Testarzt Epsilon"})
    with patch(
        "health_importer.ai.extractors.OllamaVisionClient",
        _vision_client([_PAGE_WITHOUT_PATIENT, address]),
    ):
        pages = extract_invoice_from_vision_pages(
            [(1, _png(tmp_path / "p1.png"))],
            model="vision",
            base_url="http://127.0.0.1:11434",
            timeout_seconds=5,
        )

    assert pages[0].patient_first_name.value is None


def test_patient_fallback_skipped_when_page_already_has_patient(tmp_path: Path) -> None:
    with patch(
        "health_importer.ai.extractors.OllamaVisionClient", _vision_client([_VALID_PAGE])
    ):
        pages = extract_invoice_from_vision_pages(
            [(1, _png(tmp_path / "p1.png"))],
            model="vision",
            base_url="http://127.0.0.1:11434",
            timeout_seconds=5,
        )

    assert pages[0].patient_first_name.value == "Anna"


def _invoice_extraction_with_patient(*, confidence: float):
    from health_importer.ai.schemas import InvoiceExtraction

    return InvoiceExtraction.model_validate(
        {
            "document_type": _field("honorarnote", 0.9, "HONORARNOTE"),
            "patient_first_name": {
                "value": "Katharina",
                "confidence": confidence,
                "evidence": "Frau Katharina Musterfrau",
                "page": 1,
            },
            "doctor_name": _field("Dr. Testarzt Epsilon", 0.9, "Dr. Testarzt Epsilon"),
            "appointment_date": _field("2026-09-02", 0.9, "02.09.2026"),
            "invoice_date": _field(None, 0.0, None),
            "topic": _field("Beratung", 0.9, "Beratung"),
            "total_amount_eur": _field(140.0, 0.9, "140,00"),
        }
    )


def _verification(status: str = "valid") -> str:
    return json.dumps({"status": status, "issues": [], "confidence": 0.9})


def test_confirmed_address_patient_gets_higher_confidence(tmp_path: Path) -> None:
    extraction = _invoice_extraction_with_patient(confidence=0.6)
    with patch(
        "health_importer.ai.extractors.OllamaVisionClient",
        _vision_client([_verification(), "Katharina Musterfrau"]),
    ):
        result = verify_extraction_vision(
            [(1, _png(tmp_path / "p1.png"))],
            extraction,
            model="vision",
            base_url="http://127.0.0.1:11434",
            timeout_seconds=5,
        )

    assert result is not None and result.issues == []
    assert extraction.patient_first_name.confidence == 0.85


def test_contradicting_address_patient_becomes_an_issue(tmp_path: Path) -> None:
    extraction = _invoice_extraction_with_patient(confidence=0.6)
    with patch(
        "health_importer.ai.extractors.OllamaVisionClient",
        _vision_client([_verification(), "Testarzt Epsilon"]),
    ):
        result = verify_extraction_vision(
            [(1, _png(tmp_path / "p1.png"))],
            extraction,
            model="vision",
            base_url="http://127.0.0.1:11434",
            timeout_seconds=5,
        )

    assert result is not None
    assert result.status.value == "needs_review"
    assert any("Anschriftenblock" in issue for issue in result.issues)
    assert extraction.patient_first_name.confidence == 0.6
