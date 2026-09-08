from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class ConfigError(ValueError):
    """Raised when configuration cannot be loaded or validated."""


@dataclass(frozen=True)
class FolderConfig:
    inbox: Path
    processing: Path
    done: Path
    review: Path
    error: Path


@dataclass(frozen=True)
class FileNamingConfig:
    pattern: str
    date_format: str
    max_topic_length: int


@dataclass(frozen=True)
class PatientsConfig:
    allowed_first_names: tuple[str, ...]


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str
    text_model: str
    vision_model: str
    timeout_seconds: int


@dataclass(frozen=True)
class PdfConfig:
    min_text_chars: int
    ocr_language: str
    render_dpi: int
    max_vision_pages: int
    min_area_ratio: float
    min_pixel_width: int
    min_pixel_height: int
    force_vision: bool


@dataclass(frozen=True)
class ConfidenceConfig:
    auto_create_min: float
    review_min: float
    required_fields_min: float


@dataclass(frozen=True)
class PatientEntry:
    name: str
    tag: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AnytypeConfig:
    space_id: str
    collection_name: str
    collection_id: str
    custom_type_name: str
    custom_type_key: str
    dry_run: bool
    gkk_property_id: str
    pkv_property_id: str
    pkv_eingereicht_property_id: str
    attachment_property_id: str
    done_property_id: str
    patient_tag_property_id: str
    amount_property_id: str
    date_property_id: str
    doctor_property_id: str
    patients: tuple[PatientEntry, ...] = field(default_factory=tuple)
    extension_command: str = "anytype-extension-mcp-wrapper"

    @property
    def patient_tags(self) -> dict[str, str]:
        return {p.name: p.tag for p in self.patients}

    @property
    def patient_alias_map(self) -> dict[str, str]:
        """Return a casefolded alias-to-name mapping derived from patients."""
        mapping: dict[str, str] = {}
        for p in self.patients:
            mapping[p.name.casefold()] = p.name
            for alias in p.aliases:
                mapping[alias.casefold()] = p.name
        return mapping


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    trace_full_text: bool


@dataclass(frozen=True)
class PrivacyConfig:
    store_extracted_text: bool
    store_full_text_debug: bool
    write_sidecar_json: bool
    sidecar_policy: str
    allow_external_services: bool


@dataclass(frozen=True)
class StateDbConfig:
    path: Path


@dataclass(frozen=True)
class KassenFileNamingConfig:
    enabled: bool = True
    pattern: str = "{date}_{patient}_GKK_{topic}.pdf"
    date_format: str = "%Y_%m_%d"
    max_topic_length: int = 40


@dataclass(frozen=True)
class PkvFileNamingConfig:
    enabled: bool = True
    pattern: str = "{date}_{patient}_PKV.pdf"
    date_format: str = "%Y_%m_%d"
    max_topic_length: int = 40


@dataclass(frozen=True)
class PkvInsurersConfig:
    names: tuple[str, ...] = ("Uniqua", "Donau", "Merkur")


@dataclass(frozen=True)
class KassenMatchConfig:
    auto_match_min: float
    review_match_min: float


@dataclass(frozen=True)
class EmailConfig:
    enabled: bool
    provider: str
    draft_folder: Path
    pkv_recipient: str
    pkv_subject_template: str
    pkv_body_template: str
    pkv_sender_name: str
    pkv_sender_policy_number: str
    smtp_config: dict[str, Any] | None = None


@dataclass(frozen=True)
class AppConfig:
    folders: FolderConfig
    file_naming: FileNamingConfig
    patients: PatientsConfig
    ollama: OllamaConfig
    pdf: PdfConfig
    confidence: ConfidenceConfig
    anytype: AnytypeConfig
    logging: LoggingConfig
    privacy: PrivacyConfig
    state_db: StateDbConfig
    kassen_file_naming: KassenFileNamingConfig
    pkv_file_naming: PkvFileNamingConfig
    pkv_insurers: PkvInsurersConfig
    kassen_match: KassenMatchConfig
    email: EmailConfig


def load_config(path: Path, *, raise_on_placeholder: bool = True) -> AppConfig:
    if not path.exists():
        raise ConfigError(f"Config file does not exist: {path}")
    data = _parse_simple_yaml(path.read_text(encoding="utf-8"))
    config = _build_config(data)
    _validate_privacy_boundaries(config)
    placeholder_errors = check_placeholder_values(config)
    if placeholder_errors and raise_on_placeholder:
        raise ConfigError(placeholder_errors[0]["message"])
    return config


def _build_config(data: dict[str, Any]) -> AppConfig:
    _require_sections(
        data,
        [
            "folders",
            "file_naming",
            "ollama",
            "pdf",
            "confidence",
            "anytype",
            "logging",
            "privacy",
            "state_db",
        ],
    )
    anytype_patients = _parse_anytype_patients(data.get("anytype", {}))
    allowed_first_names = tuple(p.name for p in anytype_patients)
    if not allowed_first_names:
        # Fallback for old configs that use patients.allowed_first_names
        allowed_first_names = tuple(data.get("patients", {}).get("allowed_first_names", []))
    if not allowed_first_names:
        raise ConfigError(
            "No patients configured. Add anytype.patients or patients.allowed_first_names."
        )

    return AppConfig(
        folders=FolderConfig(**{key: Path(value) for key, value in data["folders"].items()}),
        file_naming=FileNamingConfig(
            pattern=_str(data, "file_naming", "pattern"),
            date_format=_str(data, "file_naming", "date_format"),
            max_topic_length=_int(data, "file_naming", "max_topic_length"),
        ),
        patients=PatientsConfig(allowed_first_names=allowed_first_names),
        ollama=OllamaConfig(
            base_url=_str(data, "ollama", "base_url"),
            text_model=_str(data, "ollama", "text_model"),
            vision_model=_str(data, "ollama", "vision_model"),
            timeout_seconds=_int(data, "ollama", "timeout_seconds"),
        ),
        pdf=PdfConfig(
            min_text_chars=_int(data, "pdf", "min_text_chars"),
            ocr_language=_str(data, "pdf", "ocr_language"),
            render_dpi=_int(data, "pdf", "render_dpi"),
            max_vision_pages=_int(data, "pdf", "max_vision_pages"),
            min_area_ratio=_float_section_default(data.get("pdf", {}), "min_area_ratio", 0.01),
            min_pixel_width=_int_section_default(data.get("pdf", {}), "min_pixel_width", 80),
            min_pixel_height=_int_section_default(data.get("pdf", {}), "min_pixel_height", 40),
            force_vision=bool(data.get("pdf", {}).get("force_vision", False)),
        ),
        confidence=ConfidenceConfig(
            auto_create_min=_float(data, "confidence", "auto_create_min"),
            review_min=_float(data, "confidence", "review_min"),
            required_fields_min=_float(data, "confidence", "required_fields_min"),
        ),
        anytype=AnytypeConfig(
            space_id=_str(data, "anytype", "space_id"),
            collection_name=_str(data, "anytype", "collection_name"),
            collection_id=_str(data, "anytype", "collection_id"),
            custom_type_name=_str(data, "anytype", "custom_type_name"),
            custom_type_key=_str(data, "anytype", "custom_type_key"),
            dry_run=_bool(data, "anytype", "dry_run"),
            gkk_property_id=_str(data, "anytype", "gkk_property_id"),
            pkv_property_id=_str(data, "anytype", "pkv_property_id"),
            pkv_eingereicht_property_id=_str(
                data,
                "anytype",
                "pkv_eingereicht_property_id",
            ),
            attachment_property_id=_str(data, "anytype", "attachment_property_id"),
            done_property_id=_str(data, "anytype", "done_property_id"),
            patients=anytype_patients,
            patient_tag_property_id=_str(data, "anytype", "patient_tag_property_id"),
            amount_property_id=_str(data, "anytype", "amount_property_id"),
            date_property_id=_str(data, "anytype", "date_property_id"),
            doctor_property_id=_str(data, "anytype", "doctor_property_id"),
            extension_command=_str_section_default(
                data.get("anytype", {}), "extension_command", "anytype-extension-mcp-wrapper"
            ),
        ),
        logging=LoggingConfig(
            level=_str(data, "logging", "level"),
            trace_full_text=_bool(data, "logging", "trace_full_text"),
        ),
        privacy=PrivacyConfig(
            store_extracted_text=_bool(data, "privacy", "store_extracted_text"),
            store_full_text_debug=_bool(data, "privacy", "store_full_text_debug"),
            write_sidecar_json=_bool(data, "privacy", "write_sidecar_json"),
            sidecar_policy=_sidecar_policy(data),
            allow_external_services=_bool(data, "privacy", "allow_external_services"),
        ),
        state_db=StateDbConfig(path=Path(_str(data, "state_db", "path"))),
        kassen_file_naming=_kassen_file_naming_config(data),
        pkv_file_naming=_pkv_file_naming_config(data),
        pkv_insurers=_pkv_insurers_config(data),
        kassen_match=_kassen_match_config(data),
        email=_email_config(data),
    )


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    import yaml

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("Config file must contain a YAML mapping at the top level")
    return data


def _require_sections(data: dict[str, Any], sections: list[str]) -> None:
    missing = [section for section in sections if section not in data]
    if missing:
        raise ConfigError(f"Missing config sections: {', '.join(missing)}")


def _str(data: dict[str, Any], section: str, key: str) -> str:
    value = data[section][key]
    if not isinstance(value, str) or not value:
        raise ConfigError(f"Expected non-empty string for {section}.{key}")
    return value


def _str_with_default(data: dict[str, Any], section: str, key: str, default: str) -> str:
    value = data.get(section, {}).get(key, default)
    if not isinstance(value, str) or not value:
        return default
    return value


def _int(data: dict[str, Any], section: str, key: str) -> int:
    value = data[section][key]
    if not isinstance(value, int):
        raise ConfigError(f"Expected integer for {section}.{key}")
    return value


def _float(data: dict[str, Any], section: str, key: str) -> float:
    value = data[section][key]
    if not isinstance(value, int | float):
        raise ConfigError(f"Expected number for {section}.{key}")
    return float(value)


def _bool(data: dict[str, Any], section: str, key: str) -> bool:
    value = data[section][key]
    if not isinstance(value, bool):
        raise ConfigError(f"Expected boolean for {section}.{key}")
    return value


def _dict_str_str(data: dict[str, Any], section: str, key: str) -> dict[str, str]:
    value = data[section][key]
    if not isinstance(value, dict):
        raise ConfigError(f"Expected mapping for {section}.{key}")
    return {str(k): str(v) for k, v in value.items()}


def _parse_anytype_patients(section: dict[str, Any]) -> tuple[PatientEntry, ...]:
    """Parse anytype.patients list or fall back to legacy patient_tags mapping."""
    patients_list = section.get("patients")
    if isinstance(patients_list, list):
        entries: list[PatientEntry] = []
        seen_names: set[str] = set()
        for item in patients_list:
            if not isinstance(item, dict):
                raise ConfigError("anytype.patients must be a list of objects")
            name = str(item.get("name", "")).strip()
            tag = str(item.get("tag", "")).strip()
            if not name:
                raise ConfigError("Each anytype.patients entry must have a 'name'")
            if not tag:
                raise ConfigError(f"anytype.patients entry '{name}' must have a 'tag'")
            if name in seen_names:
                raise ConfigError(f"Duplicate patient name in anytype.patients: {name}")
            seen_names.add(name)
            aliases_raw = item.get("aliases", [])
            if not isinstance(aliases_raw, list):
                raise ConfigError(f"anytype.patients entry '{name}' aliases must be a list")
            aliases = tuple(str(a).strip() for a in aliases_raw if str(a).strip())
            entries.append(PatientEntry(name=name, tag=tag, aliases=aliases))
        return tuple(entries)

    # Legacy fallback: anytype.patient_tags dict -> PatientEntry without aliases
    legacy_tags = section.get("patient_tags")
    if isinstance(legacy_tags, dict):
        return tuple(PatientEntry(name=str(k), tag=str(v)) for k, v in legacy_tags.items())

    return ()


def _sidecar_policy(data: dict[str, Any]) -> str:
    policy = str(data["privacy"].get("sidecar_policy", "always"))
    if policy not in {"always", "review_error", "never"}:
        raise ConfigError("privacy.sidecar_policy must be one of: always, review_error, never")
    return policy


def _kassen_file_naming_config(data: dict[str, Any]) -> KassenFileNamingConfig:
    section = data.get("kassen_file_naming", {})
    return KassenFileNamingConfig(
        enabled=_bool_section_default(section, "enabled", True),
        pattern=_str_section_default(section, "pattern", "{date}_{patient}_GKK_{topic}.pdf"),
        date_format=_str_section_default(section, "date_format", "%Y_%m_%d"),
        max_topic_length=_int_section_default(section, "max_topic_length", 40),
    )


def _pkv_file_naming_config(data: dict[str, Any]) -> PkvFileNamingConfig:
    section = data.get("pkv_file_naming", {})
    return PkvFileNamingConfig(
        enabled=_bool_section_default(section, "enabled", True),
        pattern=_str_section_default(section, "pattern", "{date}_{patient}_PKV.pdf"),
        date_format=_str_section_default(section, "date_format", "%Y_%m_%d"),
        max_topic_length=_int_section_default(section, "max_topic_length", 40),
    )


def _pkv_insurers_config(data: dict[str, Any]) -> PkvInsurersConfig:
    section = data.get("pkv_insurers", {})
    names = _str_list_section_default(section, "names", ["Uniqua", "Donau", "Merkur"])
    return PkvInsurersConfig(names=tuple(names))


def _kassen_match_config(data: dict[str, Any]) -> KassenMatchConfig:
    section = data.get("kassen_match", {})
    return KassenMatchConfig(
        auto_match_min=_float_section_default(section, "auto_match_min", 0.90),
        review_match_min=_float_section_default(section, "review_match_min", 0.60),
    )


def _email_config(data: dict[str, Any]) -> EmailConfig:
    section = data.get("email", {})
    draft_folder = section.get("draft_folder", "review/drafts")
    imap_config = _build_imap_config(section)
    _default_body_template = (
        "Sehr geehrte Damen und Herren,\n\n"
        "hiermit reiche ich die Wahlarztrechnung für {patient} ein.\n\n"
        "{details}\n\n"
        "Mit freundlichen Grüßen,\n\n"
    )
    return EmailConfig(
        enabled=_bool_section_default(section, "enabled", False),
        provider=_str_section_default(section, "provider", "file_only"),
        draft_folder=Path(draft_folder),
        pkv_recipient=_str_section_default(section, "pkv_recipient", "pkv-service@example.invalid"),
        pkv_subject_template=_str_section_default(
            section, "pkv_subject_template", "Einreichung Wahlarztrechnung — {patient} — {date}"
        ),
        pkv_body_template=_str_section_default(
            section, "pkv_body_template", _default_body_template
        ),
        pkv_sender_name=_str_or_empty_section_default(section, "pkv_sender_name", ""),
        pkv_sender_policy_number=_str_or_empty_section_default(
            section, "pkv_sender_policy_number", ""
        ),
        smtp_config=imap_config,
    )


def _build_imap_config(section: dict[str, Any]) -> dict[str, Any] | None:
    imap_keys = [
        "imap_host",
        "imap_port",
        "imap_username",
        "imap_password_env_key",
        "imap_draft_folder_name",
        "imap_from_addr",
    ]
    config: dict[str, Any] = {}
    for key in imap_keys:
        if key in section:
            config[key.replace("imap_", "")] = section[key]
    return config if config else None


def _bool_section_default(section: dict[str, Any], key: str, default: bool) -> bool:
    value = section.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"Expected boolean for section config {key}")
    return value


def _str_section_default(section: dict[str, Any], key: str, default: str) -> str:
    value = section.get(key, default)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"Expected non-empty string for section config {key}")
    return value


def _str_or_empty_section_default(section: dict[str, Any], key: str, default: str = "") -> str:
    value = section.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"Expected string for section config {key}")
    return value


def _str_list_section_default(
    section: dict[str, Any], key: str, default: list[str]
) -> list[str]:
    value = section.get(key, default)
    if not isinstance(value, list):
        raise ConfigError(f"Expected list for section config {key}")
    names = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"Expected non-empty string entries for section config {key}")
        names.append(item.strip())
    if not names:
        raise ConfigError(f"Expected at least one entry for section config {key}")
    return names


def _int_section_default(section: dict[str, Any], key: str, default: int) -> int:
    value = section.get(key, default)
    if not isinstance(value, int):
        raise ConfigError(f"Expected integer for section config {key}")
    return value


def _float_section_default(section: dict[str, Any], key: str, default: float) -> float:
    value = section.get(key, default)
    if not isinstance(value, int | float):
        raise ConfigError(f"Expected number for section config {key}")
    return float(value)


def _validate_privacy_boundaries(config: AppConfig) -> None:
    if config.privacy.allow_external_services:
        return
    if not is_local_http_url(config.ollama.base_url):
        raise ConfigError(
            "privacy.allow_external_services is false, but ollama.base_url is not local: "
            f"{config.ollama.base_url}"
        )
    if config.email.enabled and config.email.provider != "file_only":
        raise ConfigError(
            "privacy.allow_external_services is false, but email.provider is external: "
            f"{config.email.provider}"
        )


def check_production_warnings(config: AppConfig) -> list[dict]:
    """Return non-empty list of warning dicts when productive modes are detected."""
    warnings: list[dict] = []
    if not config.anytype.dry_run:
        warnings.append(
            {
                "severity": "warning",
                "setting": "anytype.dry_run",
                "message": "Anytype dry_run is disabled. Updates will write to your Anytype workspace.",
            }
        )
    if config.email.enabled:
        warnings.append(
            {
                "severity": "warning",
                "setting": "email.enabled",
                "message": f"Email is enabled (provider={config.email.provider}). Drafts or sends may use external services.",
            }
        )
    if config.privacy.allow_external_services:
        warnings.append(
            {
                "severity": "warning",
                "setting": "privacy.allow_external_services",
                "message": "External services are allowed. Ollama/email may use non-local endpoints.",
            }
        )
    return warnings


def check_placeholder_values(config: AppConfig) -> list[dict]:
    """Return errors for placeholder values that must be replaced."""
    errors: list[dict] = []
    placeholder_pattern = "<your-"
    if placeholder_pattern in config.anytype.space_id:
        errors.append(
            {
                "severity": "error",
                "setting": "anytype.space_id",
                "message": "space_id contains a placeholder. Replace it with your real Anytype space ID.",
            }
        )
    if placeholder_pattern in config.anytype.collection_id:
        errors.append(
            {
                "severity": "error",
                "setting": "anytype.collection_id",
                "message": "collection_id contains a placeholder. Replace it with your real Anytype collection ID.",
            }
        )
    return errors


def is_local_http_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = (parsed.hostname or "").casefold()
    return hostname in {"localhost", "127.0.0.1", "::1"}
