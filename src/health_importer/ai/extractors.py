from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import TypeVar

from PIL import Image
from pydantic import BaseModel, ValidationError

from health_importer.ai.ollama_client import OllamaError, OllamaTextClient, OllamaVisionClient
from health_importer.ai.prompts import load_invoice_prompt, load_prompt, page_text_for_prompt, vision_prompt_for_page
from health_importer.ai.schemas import (
    ExtractedField,
    ExtractionVerification,
    InvoiceExtraction,
    KassenRuckmeldungExtraction,
    PkvAntwortExtraction,
    VerificationStatus,
    VisionPageExtraction,
    VisionValueVerification,
)


class ExtractionError(RuntimeError):
    """Raised when local text extraction cannot produce valid schema JSON."""


_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _text_json(
    client: OllamaTextClient,
    messages: list[dict[str, str]],
    schema_model: type[_ModelT],
    *,
    what: str,
    max_retries: int = 1,
) -> _ModelT:
    """Ask for JSON without a grammar, validate it, and re-ask once if invalid.

    The text client sends no `format` schema either (see ollama_client), so this
    loop is the only thing keeping the answer well-formed -- the same repair
    loop _vision_json runs for the vision path.
    """
    original_user = "\n\n".join(m["content"] for m in messages[1:])
    last_error: Exception | None = None
    current = messages
    for attempt in range(max_retries + 1):
        response = client.chat(current)
        try:
            return schema_model.model_validate(_loads_json_object(response))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            current = [
                messages[0],
                {
                    "role": "user",
                    "content": (
                        "Die vorherige Antwort war kein valides JSON nach Schema. "
                        "Antworte jetzt ausschließlich mit korrigiertem JSON.\n\n"
                        f"{original_user}\n\nFehler: {exc}\n\n"
                        f"Vorherige Antwort:\n{response}"
                    ),
                },
            ]
            if attempt >= max_retries:
                break
    raise ExtractionError(f"{what} failed: {last_error}") from last_error


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

    return _text_json(
        client,
        messages,
        InvoiceExtraction,
        what="Text extraction",
        max_retries=max_retries,
    )


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

    return _text_json(
        client,
        messages,
        KassenRuckmeldungExtraction,
        what="Kassen extraction",
        max_retries=max_retries,
    )


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

    return _text_json(
        client,
        messages,
        PkvAntwortExtraction,
        what="Pkv extraction",
        max_retries=max_retries,
    )


def _vision_json(
    client: OllamaVisionClient,
    image_paths: list[Path],
    prompt: str,
    schema_model: type[_ModelT],
    *,
    what: str,
    num_predict: int = 2048,
    max_retries: int = 1,
) -> _ModelT:
    """Ask for JSON without a grammar, validate it, and re-ask once if invalid.

    The vision client sends no `format` schema (see ollama_client), so nothing
    guarantees well-formed JSON any more -- this loop replaces that guarantee,
    the same way extract_invoice_from_text does for the text path.
    """
    last_error: Exception | None = None
    current = prompt
    for attempt in range(max_retries + 1):
        response = client.chat_with_images(image_paths, current, num_predict=num_predict)
        try:
            return schema_model.model_validate(_loads_json_object(response))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            current = (
                f"{prompt}\n\nDeine vorherige Antwort war kein valides JSON nach Schema.\n"
                f"Fehler: {exc}\n\nVorherige Antwort:\n{response}\n\n"
                "Antworte jetzt ausschließlich mit korrigiertem JSON."
            )
            if attempt >= max_retries:
                break
    raise ExtractionError(f"{what} failed: {last_error}") from last_error


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
    return _vision_json(
        client,
        image_paths,
        prompt,
        KassenRuckmeldungExtraction,
        what="Kassen vision extraction",
    )


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
    return _vision_json(
        client,
        image_paths,
        prompt,
        PkvAntwortExtraction,
        what="Pkv vision extraction",
    )


# Der Anschriftenblock einer Honorarnote wird vom Modell auf der vollen Seite
# regelmaessig mit dem Briefkopf verwechselt (es nennt dann den Arzt als
# Empfaenger). Auf den oberen 35 % allein liest es ihn zuverlaessig.
PATIENT_ADDRESS_CROP_TOP = 0.35
# Der Fallback liest den Anschriftenblock einmal; bestaetigt ihn die Verifikation
# unabhaengig ein zweites Mal, gilt der Name als gesichert.
PATIENT_ADDRESS_FALLBACK_CONFIDENCE = 0.6
PATIENT_ADDRESS_CONFIRMED_CONFIDENCE = 0.85


def _top_crop(image_path: Path, out_dir: Path) -> Path | None:
    """Upper part of a page render, where letterhead and addressee sit."""
    try:
        with Image.open(image_path) as image:
            image.load()
            crop = image.convert("RGB").crop(
                (0, 0, image.width, max(1, int(image.height * PATIENT_ADDRESS_CROP_TOP)))
            )
    except OSError:
        return None
    crop_path = out_dir / "top.png"
    crop.save(crop_path)
    return crop_path


def _patient_from_address_block(
    client: OllamaVisionClient,
    image_path: Path,
    page_number: int,
    doctor_name: object,
) -> ExtractedField | None:
    """Second, cropped pass for the addressee when the full page yielded no patient.

    Only sound where the addressee *is* the patient -- invoices, Befunde,
    Patientenbriefe. On Kassen/PKV Bescheiden the addressee is usually the
    policyholder, so that path deliberately does not use this.
    """
    with tempfile.TemporaryDirectory(prefix="health-importer-address-") as tmp:
        crop_path = _top_crop(image_path, Path(tmp))
        if crop_path is None:
            return None
        try:
            response = client.chat_with_images(
                [crop_path], load_prompt("extract_patient_address_vision.md"), num_predict=200
            )
            parsed = _loads_json_object(response)
        except (OllamaError, json.JSONDecodeError, ValueError):
            return None

    first_name = parsed.get("first_name")
    evidence = parsed.get("evidence")
    if not isinstance(first_name, str) or not first_name.strip() or not evidence:
        return None
    first_name = first_name.strip().split()[0]

    # Guard against the very confusion this pass exists to avoid.
    if isinstance(doctor_name, str) and first_name.casefold() in doctor_name.casefold():
        return None

    return ExtractedField(
        value=first_name,
        confidence=PATIENT_ADDRESS_FALLBACK_CONFIDENCE,
        evidence=str(evidence)[:200],
        page=page_number,
    )


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
        results.append(
            _vision_json(
                client,
                [image_path],
                vision_prompt_for_page(page_number, pkv_insurer_names=pkv_insurer_names),
                VisionPageExtraction,
                what=f"Vision extraction on page {page_number}",
            )
        )

    if results and all(page.patient_first_name.value is None for page in results):
        page_number, image_path = images[0]
        fallback = _patient_from_address_block(
            client, image_path, page_number, results[0].doctor_name.value
        )
        if fallback is not None:
            results[0].patient_first_name = fallback
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
    return _text_json(
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
        ExtractionVerification,
        what="Verification",
    )


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

    # patient_first_name is checked separately, against the cropped address block
    # only. Handing the crop to this call *alongside* the full page does not work:
    # the prominent letterhead wins the model's attention either way, and it then
    # reports a correctly extracted patient as "not visible" (measured -- it even
    # claims the crop contains no addressee block). The same crop asked on its own
    # is read correctly.
    payload = extraction.model_dump(mode="json")
    payload.pop("patient_first_name", None)
    prompt = (
        f"{prompt}\n\n`patient_first_name` ist nicht Teil dieser Prüfung und fehlt "
        "deshalb absichtlich in der Extraktion. Bemängle sein Fehlen nicht."
    )
    verification = _vision_json(
        client,
        image_paths,
        f"{prompt}\n\nExtraktion:\n{json.dumps(payload, ensure_ascii=False, indent=2)}",
        ExtractionVerification,
        what="Vision verification",
    )

    issue, confirmed = _check_patient_against_address_block(
        client, images[0][1], extraction.patient_first_name.value
    )
    if issue is not None:
        verification.issues.append(issue)
        if verification.status == VerificationStatus.VALID:
            verification.status = VerificationStatus.NEEDS_REVIEW
    elif confirmed and extraction.patient_first_name.confidence < (
        PATIENT_ADDRESS_CONFIRMED_CONFIDENCE
    ):
        # Deliberate mutation of the argument: a name the fallback read once and
        # this independent second read confirms is no longer a low-confidence
        # guess. The caller writes the updated extraction back to the state.
        extraction.patient_first_name.confidence = PATIENT_ADDRESS_CONFIRMED_CONFIDENCE
    return verification


def _check_patient_against_address_block(
    client: OllamaVisionClient, image_path: Path, patient_value: object
) -> tuple[str | None, bool]:
    """Check the extracted patient against the address block alone.

    Returns (issue, confirmed). A check that could not be carried out yields
    (None, False) -- it must neither fabricate an issue nor confirm anything.
    """
    if patient_value is None:
        return None, False
    with tempfile.TemporaryDirectory(prefix="health-importer-verify-") as tmp:
        crop_path = _top_crop(image_path, Path(tmp))
        if crop_path is None:
            return None, False
        try:
            answer = client.chat_with_images(
                [crop_path],
                "An welche Person ist dieses Dokument adressiert? Antworte nur mit "
                "Vor- und Nachnamen, sonst nichts. Der Absender im Briefkopf zählt nicht.",
                num_predict=60,
            )
        except OllamaError:
            return None, False
    if str(patient_value).casefold() in answer.casefold():
        return None, True
    return (
        f"patient_first_name: Extrahiert '{patient_value}', der Anschriftenblock "
        f"nennt aber '{answer.strip()[:80]}'."
    ), False


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
    return _vision_json(
        client,
        image_paths,
        (
            f"{prompt}\n\n"
            "Zu pruefende Werte:\n"
            f"- total_amount_eur: {amount}\n"
            f"- invoice_or_appointment_date: {target_date}\n"
        ),
        VisionValueVerification,
        what="Vision value verification",
    )


def _loads_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    match = _JSON_BLOCK_RE.search(stripped)
    if not match:
        raise ValueError("No JSON object found in model response")
    return json.loads(match.group(1))


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
