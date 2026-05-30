from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


SUPPORTED_CORRECTION_KEYS = {
    "patient",
    "patient_first_name",
    "termin",
    "appointment_date",
    "thema",
    "topic",
    "betrag",
    "total_amount_eur",
    "arzt",
    "doctor_name",
    "kassen_match_object_id",
    "kassen_object_id",
    "kassen_match_object_name",
}


def load_correction_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Correction file does not exist: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Correction file must contain a YAML mapping.")

    corrections: dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise ValueError(f"Unsupported correction key: {key}")
        if key not in SUPPORTED_CORRECTION_KEYS:
            raise ValueError(f"Unsupported correction key: {key}")
        corrections[key] = _normalize_value(key, value)
    return corrections


def _normalize_value(key: str, value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        raise ValueError(f"Unsupported correction value for {key}: {value!r}")
    if value is None or isinstance(value, str | int | float):
        return value
    raise ValueError(f"Unsupported correction value for {key}: {value!r}")
