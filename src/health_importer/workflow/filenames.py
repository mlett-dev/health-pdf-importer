from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from pathlib import Path

from health_importer.config import FileNamingConfig, KassenFileNamingConfig, PkvFileNamingConfig
from health_importer.workflow.filesystem import unique_destination
from health_importer.workflow.validation import (
    ValidatedInvoice,
    ValidatedKassenRuckmeldung,
    ValidatedPkvAntwort,
)


def generate_invoice_filename(invoice: ValidatedInvoice, config: FileNamingConfig) -> str:
    values = {
        "date": _slugify(invoice.date.strftime(config.date_format)),
        "patient": _slugify(invoice.patient_first_name),
        "topic": _slugify(invoice.topic, max_length=config.max_topic_length),
        "doctor": _slugify(invoice.doctor_name or "Unbekannt"),
        "doctor_last_name": _slugify(_extract_last_name(invoice.doctor_name)),
        "total_amount_eur": _format_amount_eur(invoice.total_amount_eur),
    }
    return _generate_filename(config.pattern, values, prefix="invoice")


def generate_unique_invoice_path(
    invoice: ValidatedInvoice,
    config: FileNamingConfig,
    destination_dir: Path,
) -> Path:
    return unique_destination(destination_dir / generate_invoice_filename(invoice, config))


def generate_kassen_filename(
    kassen: ValidatedKassenRuckmeldung,
    config: KassenFileNamingConfig,
    *,
    invoice_topic: str | None = None,
) -> str:
    if not config.enabled:
        return ""
    date_str = ""
    if kassen.bescheids_datum is not None:
        date_str = _slugify(kassen.bescheids_datum.strftime(config.date_format))
    elif kassen.betreffender_termin is not None:
        date_str = _slugify(kassen.betreffender_termin.strftime(config.date_format))
    service_date_str = ""
    if kassen.betreffender_termin is not None:
        service_date_str = _slugify(kassen.betreffender_termin.strftime(config.date_format))
    if invoice_topic is not None:
        topic = _slugify(invoice_topic, max_length=config.max_topic_length)
    else:
        topic = _slugify(
            kassen.doctor_name or "GKK_Rueckmeldung", max_length=config.max_topic_length
        )
    values = {
        "date": date_str or "unknown_date",
        "service_date": service_date_str or "unknown_date",
        "patient": _slugify(kassen.patient_first_name),
        "topic": topic,
        "doctor": _slugify(kassen.doctor_name or "Unbekannt"),
        "doctor_last_name": _slugify(_extract_last_name(kassen.doctor_name)),
        "total_amount_eur": _format_amount_eur(kassen.erstattungsbetrag_eur),
    }
    return _generate_filename(config.pattern, values, prefix="kassen")


def generate_unique_kassen_path(
    kassen: ValidatedKassenRuckmeldung,
    config: KassenFileNamingConfig,
    destination_dir: Path,
    *,
    invoice_topic: str | None = None,
) -> Path | None:
    filename = generate_kassen_filename(kassen, config, invoice_topic=invoice_topic)
    if not filename:
        return None
    return unique_destination(destination_dir / filename)


def generate_pkv_filename(
    pkv: ValidatedPkvAntwort,
    config: PkvFileNamingConfig,
    *,
    invoice_topic: str | None = None,
) -> str:
    if not config.enabled:
        return ""
    date_str = ""
    if pkv.bescheids_datum is not None:
        date_str = _slugify(pkv.bescheids_datum.strftime(config.date_format))
    elif pkv.betreffender_termin is not None:
        date_str = _slugify(pkv.betreffender_termin.strftime(config.date_format))
    service_date_str = ""
    if pkv.betreffender_termin is not None:
        service_date_str = _slugify(pkv.betreffender_termin.strftime(config.date_format))
    if invoice_topic is not None:
        topic = _slugify(invoice_topic, max_length=config.max_topic_length)
    else:
        topic = _slugify(
            pkv.doctor_name or "PKV_Rueckmeldung", max_length=config.max_topic_length
        )
    values = {
        "date": date_str or "unknown_date",
        "service_date": service_date_str or "unknown_date",
        "patient": _slugify(pkv.patient_first_name),
        "topic": topic,
        "doctor": _slugify(pkv.doctor_name or "Unbekannt"),
        "doctor_last_name": _slugify(_extract_last_name(pkv.doctor_name)),
        "total_amount_eur": _format_amount_eur(pkv.erstattungsbetrag_eur),
    }
    return _generate_filename(config.pattern, values, prefix="pkv")


def generate_unique_pkv_path(
    pkv: ValidatedPkvAntwort,
    config: PkvFileNamingConfig,
    destination_dir: Path,
    *,
    invoice_topic: str | None = None,
) -> Path | None:
    filename = generate_pkv_filename(pkv, config, invoice_topic=invoice_topic)
    if not filename:
        return None
    return unique_destination(destination_dir / filename)


def _generate_filename(
    pattern: str,
    values: dict[str, str],
    *,
    prefix: str = "filename",
) -> str:
    try:
        filename = pattern.format(**values)
    except KeyError as exc:
        raise ValueError(f"Unsupported {prefix} pattern placeholder: {exc.args[0]}") from exc
    filename = _sanitize_filename(filename)
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"
    return filename


def _slugify(value: str, *, max_length: int | None = None) -> str:
    normalized = unicodedata.normalize("NFKD", _replace_german_umlauts(value))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _UNSAFE_PART_RE.sub("_", ascii_value)
    slug = _UNDERSCORE_RE.sub("_", slug).strip("_")
    if max_length is not None:
        slug = slug[:max_length].rstrip("_")
    return slug or "Unbekannt"


def _sanitize_filename(filename: str) -> str:
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    safe_stem = _slugify(stem)
    if suffix.lower() == ".pdf":
        return f"{safe_stem}.pdf"
    safe_suffix = _slugify(suffix.lstrip(".")) if suffix else ""
    return f"{safe_stem}.{safe_suffix}" if safe_suffix else safe_stem


def _replace_german_umlauts(value: str) -> str:
    replacements = {
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value


def _format_amount_eur(amount: Decimal) -> str:
    return f"{amount:.2f}".replace(".", ",")


def _extract_last_name(name: str | None) -> str:
    if not name:
        return "Unbekannt"
    parts = name.strip().split()
    if not parts:
        return "Unbekannt"
    return parts[-1]


_UNSAFE_PART_RE = re.compile(r"[^A-Za-z0-9.,-]+")
_UNDERSCORE_RE = re.compile(r"_+")
