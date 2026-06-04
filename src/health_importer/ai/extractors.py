from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from health_importer.ai.ollama_client import OllamaTextClient, OllamaVisionClient
from health_importer.ai.prompts import load_invoice_prompt, load_prompt, page_text_for_prompt, vision_prompt_for_page
from health_importer.ai.schemas import (
    ExtractionVerification,
    InvoiceExtraction,
    KassenRuckmeldungExtraction,
    PkvAntwortExtraction,
    VisionPageExtraction,
    VisionValueVerification,
)


class ExtractionError(RuntimeError):
    """Raised when local text extraction cannot produce valid schema JSON."""


def extract_invoice_from_text(
    pdf_text: dict,
    *,
    model: str,
    base_url: str,
    timeout_seconds: int,
    pkv_insurer_names: tuple[str, ...] = ("Uniqua", "Donau", "Merkur"),
    max_retries: int = 1,
) -> InvoiceExtraction:
    prompt = load_invoice_prompt("extract_invoice_text.md", pkv_insurer_names=pkv_insurer_names)
    text = page_text_for_prompt(pdf_text)
    client = OllamaTextClient(base_url=base_url, model=model, timeout_seconds=timeout_seconds)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Extrahiere aus diesem Text:\n\n{text}"},
    ]

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        response = _chat_schema(client, messages, InvoiceExtraction.model_json_schema())
        try:
            return InvoiceExtraction.model_validate(_loads_json_object(response))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            messages = [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        "Die vorherige Antwort war kein valides JSON nach Schema. "
                        "Antworte jetzt ausschließlich mit korrigiertem JSON.\n\n"
                        f"Originaltext:\n{text}\n\nFehler: {exc}\n\n"
                        f"Vorherige Antwort:\n{response}"
                    ),
                },
            ]
            if attempt >= max_retries:
                break
    raise ExtractionError(f"Text extraction failed: {last_error}") from last_error


def extract_kassen_ruckmeldung_from_text(
    pdf_text: dict,
    *,
    model: str,
    base_url: str,
    timeout_seconds: int,
    max_retries: int = 1,
) -> KassenRuckmeldungExtraction:
    prompt = load_prompt("extract_kassen_ruckmeldung.md")
    text = page_text_for_prompt(pdf_text)
    client = OllamaTextClient(base_url=base_url, model=model, timeout_seconds=timeout_seconds)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Extrahiere aus diesem Text:\n\n{text}"},
    ]

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        response = _chat_schema(client, messages, KassenRuckmeldungExtraction.model_json_schema())
        try:
            return KassenRuckmeldungExtraction.model_validate(_loads_json_object(response))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            messages = [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        "Die vorherige Antwort war kein valides JSON nach Schema. "
                        "Antworte jetzt ausschließlich mit korrigiertem JSON.\n\n"
                        f"Originaltext:\n{text}\n\nFehler: {exc}\n\n"
                        f"Vorherige Antwort:\n{response}"
                    ),
                },
            ]
            if attempt >= max_retries:
                break
    raise ExtractionError(f"Kassen extraction failed: {last_error}") from last_error


def extract_pkv_antwort_from_text(
    pdf_text: dict,
    *,
    model: str,
    base_url: str,
    timeout_seconds: int,
    max_retries: int = 1,
) -> PkvAntwortExtraction:
    prompt = load_prompt("extract_pkv_antwort.md")
    text = page_text_for_prompt(pdf_text)
    client = OllamaTextClient(base_url=base_url, model=model, timeout_seconds=timeout_seconds)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Extrahiere aus diesem Text:\n\n{text}"},
    ]

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        response = _chat_schema(client, messages, PkvAntwortExtraction.model_json_schema())
        try:
            return PkvAntwortExtraction.model_validate(_loads_json_object(response))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            messages = [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        "Die vorherige Antwort war kein valides JSON nach Schema. "
                        "Antworte jetzt ausschließlich mit korrigiertem JSON.\n\n"
                        f"Originaltext:\n{text}\n\nFehler: {exc}\n\n"
                        f"Vorherige Antwort:\n{response}"
                    ),
                },
            ]
            if attempt >= max_retries:
                break
    raise ExtractionError(f"Pkv extraction failed: {last_error}") from last_error


def extract_kassen_ruckmeldung_from_vision_pages(
    images: list[tuple[int, Path]],
    *,
    model: str,
    base_url: str,
    timeout_seconds: int,
) -> KassenRuckmeldungExtraction:
    prompt = load_prompt("extract_kassen_ruckmeldung_vision.md")
    image_paths = [image_path for _page_number, image_path in images]
    client = OllamaVisionClient(base_url=base_url, model=model, timeout_seconds=timeout_seconds)
    response = client.chat_with_images(
        image_paths,
        prompt,
        response_format=KassenRuckmeldungExtraction.model_json_schema(),
        num_predict=2048,
    )
    try:
        return KassenRuckmeldungExtraction.model_validate(_loads_json_object(response))
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ExtractionError(f"Kassen vision extraction failed: {exc}") from exc


def extract_pkv_antwort_from_vision_pages(
    images: list[tuple[int, Path]],
    *,
    model: str,
    base_url: str,
    timeout_seconds: int,
) -> PkvAntwortExtraction:
    prompt = load_prompt("extract_pkv_antwort_vision.md")
    image_paths = [image_path for _page_number, image_path in images]
    client = OllamaVisionClient(base_url=base_url, model=model, timeout_seconds=timeout_seconds)
    response = client.chat_with_images(
        image_paths,
        prompt,
        response_format=PkvAntwortExtraction.model_json_schema(),
        num_predict=2048,
    )
    try:
        return PkvAntwortExtraction.model_validate(_loads_json_object(response))
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ExtractionError(f"Pkv vision extraction failed: {exc}") from exc


def extract_invoice_from_vision_pages(
    images: list[tuple[int, Path]],
    *,
    model: str,
    base_url: str,
    timeout_seconds: int,
    pkv_insurer_names: tuple[str, ...] = ("Uniqua", "Donau", "Merkur"),
) -> list[VisionPageExtraction]:
    client = OllamaVisionClient(base_url=base_url, model=model, timeout_seconds=timeout_seconds)
    results = []
    for page_number, image_path in images:
        response = client.describe_image(
            image_path, vision_prompt_for_page(page_number, pkv_insurer_names=pkv_insurer_names)
        )
        try:
            results.append(VisionPageExtraction.model_validate(_loads_json_object(response)))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise ExtractionError(f"Vision extraction failed on page {page_number}: {exc}") from exc
    return results


def consolidate_vision_pages(pages: list[VisionPageExtraction]) -> InvoiceExtraction:
    def best(field_name: str):
        fields = [getattr(page, field_name) for page in pages]
        populated = [field for field in fields if field.value is not None]
        if not populated:
            return fields[0]
        return max(populated, key=lambda field: field.confidence)

    def merge_line_items():
        items = []
        for page in pages:
            for item in page.line_items:
                if item.value is not None:
                    items.append(item)
        return items

    if not pages:
        raise ExtractionError("Cannot consolidate empty vision page list")

    warnings = []
    for page in pages:
        warnings.extend(page.warnings)

    return InvoiceExtraction(
        document_type=best("document_type"),
        patient_first_name=best("patient_first_name"),
        doctor_name=best("doctor_name"),
        appointment_date=best("appointment_date"),
        invoice_date=best("invoice_date"),
        topic=best("topic"),
        total_amount_eur=best("total_amount_eur"),
        invoice_number=best("invoice_number"),
        iban=best("iban"),
        diagnosis=best("diagnosis"),
        line_items=merge_line_items(),
        warnings=warnings,
        missing_fields=[],
    )


def verify_extraction(
    source_text: str,
    extraction: InvoiceExtraction,
    *,
    model: str,
    base_url: str,
    timeout_seconds: int,
    enabled: bool = True,
) -> ExtractionVerification | None:
    if not enabled:
        return None

    prompt = load_prompt("verify_extraction.md")
    client = OllamaTextClient(base_url=base_url, model=model, timeout_seconds=timeout_seconds)
    response = _chat_schema(
        client,
        [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "Originaltext:\n"
                    f"{source_text}\n\nExtraktion:\n"
                    f"{extraction.model_dump_json(indent=2)}"
                ),
            },
        ],
        ExtractionVerification.model_json_schema(),
    )
    try:
        return ExtractionVerification.model_validate(_loads_json_object(response))
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ExtractionError(f"Verification failed: {exc}") from exc


def verify_extraction_vision(
    images: list[tuple[int, Path]],
    extraction: InvoiceExtraction,
    *,
    model: str,
    base_url: str,
    timeout_seconds: int,
    enabled: bool = True,
) -> ExtractionVerification | None:
    if not enabled:
        return None

    prompt = load_prompt("verify_extraction_vision.md")
    client = OllamaVisionClient(base_url=base_url, model=model, timeout_seconds=timeout_seconds)
    image_paths = [image_path for _page_number, image_path in images]
    response = client.chat_with_images(
        image_paths,
        (f"{prompt}\n\nExtraktion:\n{extraction.model_dump_json(indent=2)}"),
        response_format=ExtractionVerification.model_json_schema(),
    )
    try:
        return ExtractionVerification.model_validate(_loads_json_object(response))
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ExtractionError(f"Vision verification failed: {exc}") from exc


def verify_invoice_values_vision(
    images: list[tuple[int, Path]],
    *,
    amount: str,
    target_date: str,
    model: str,
    base_url: str,
    timeout_seconds: int,
    enabled: bool = True,
) -> VisionValueVerification | None:
    if not enabled:
        return None

    prompt = load_prompt("verify_invoice_values_vision.md")
    client = OllamaVisionClient(base_url=base_url, model=model, timeout_seconds=timeout_seconds)
    image_paths = [image_path for _page_number, image_path in images]
    response = client.chat_with_images(
        image_paths,
        (
            f"{prompt}\n\n"
            "Zu pruefende Werte:\n"
            f"- total_amount_eur: {amount}\n"
            f"- invoice_or_appointment_date: {target_date}\n"
        ),
        response_format=VisionValueVerification.model_json_schema(),
    )
    try:
        return VisionValueVerification.model_validate(_loads_json_object(response))
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ExtractionError(f"Vision value verification failed: {exc}") from exc


def _loads_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    match = _JSON_BLOCK_RE.search(stripped)
    if not match:
        raise ValueError("No JSON object found in model response")
    return json.loads(match.group(1))


def _chat_schema(client: OllamaTextClient, messages: list[dict[str, str]], schema: dict) -> str:
    try:
        return client.chat(messages, response_format=schema)
    except TypeError:
        return client.chat(messages)


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
