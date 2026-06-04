from pathlib import Path

import pytest

from health_importer.config import ConfigError, check_production_warnings, load_config
from health_importer.graph.runner import run_once


def _replace_placeholders(config_text: str) -> str:
    """Replace all <your-...> placeholders with test values so the example config loads."""
    return (
        config_text.replace('"<your-space-id>"', '"bafyrei-test-space"')
        .replace('"<your-collection-id>"', '"bafyrei-test-collection"')
        .replace('"<your-gkk-property-id>"', '"test-gkk-id"')
        .replace('"<your-pkv-property-id>"', '"test-pkv-id"')
        .replace('"<your-pkv-eingereicht-property-id>"', '"test-pkv-eingereicht-id"')
        .replace('"<your-attachment-property-id>"', '"test-attachment-id"')
        .replace('"<your-done-property-id>"', '"test-done-id"')
        .replace('"<your-patient-tag-property-id>"', '"test-patient-tag-id"')
        .replace('"<your-amount-property-id>"', '"test-amount-id"')
        .replace('"<your-date-property-id>"', '"test-date-id"')
        .replace('"<your-doctor-property-id>"', '"test-doctor-id"')
        .replace('"<your-max-tag-id>"', '"test-max-tag"')
        .replace('"<your-anna-tag-id>"', '"test-anna-tag"')
    )


def test_load_example_config(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_text = Path("config/app.example.yaml").read_text(encoding="utf-8")
    config_path.write_text(_replace_placeholders(config_text), encoding="utf-8")
    config = load_config(config_path)

    assert config.anytype.collection_name == "Wahlarzt Rechnungen"
    assert config.anytype.custom_type_key == "wahlarztrechnung"
    assert config.patients.allowed_first_names == ("Max", "Anna")
    assert config.anytype.dry_run is True
    assert config.anytype.gkk_property_id == "test-gkk-id"
    assert config.anytype.pkv_property_id == "test-pkv-id"
    assert config.anytype.pkv_eingereicht_property_id == "test-pkv-eingereicht-id"
    assert config.anytype.attachment_property_id == "test-attachment-id"
    assert config.anytype.done_property_id == "test-done-id"
    assert config.anytype.patient_tag_property_id == "test-patient-tag-id"
    assert config.anytype.amount_property_id == "test-amount-id"
    assert config.anytype.date_property_id == "test-date-id"
    assert config.anytype.doctor_property_id == "test-doctor-id"
    assert config.anytype.extension_command == "anytype-extension-mcp-wrapper"
    assert config.anytype.patient_tags == {
        "Max": "test-max-tag",
        "Anna": "test-anna-tag",
    }
    assert config.privacy.allow_external_services is False
    assert config.privacy.sidecar_policy == "always"
    assert config.logging.trace_full_text is False
    assert config.pkv_insurers.names == ("Uniqua", "Donau", "Merkur")


def test_pkv_insurers_names_can_be_configured(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_text = Path("config/app.example.yaml").read_text(encoding="utf-8")
    config_path.write_text(
        _replace_placeholders(config_text)
        + """
pkv_insurers:
  names:
    - Allianz
    - Wiener Staedtische
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.pkv_insurers.names == ("Allianz", "Wiener Staedtische")


def test_pkv_insurers_names_reject_invalid_entries(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_text = Path("config/app.example.yaml").read_text(encoding="utf-8")
    config_path.write_text(
        _replace_placeholders(config_text)
        + """
pkv_insurers:
  names:
    - Uniqua
    - 123
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="non-empty string entries"):
        load_config(config_path)


def test_placeholder_space_id_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_text = Path("config/app.example.yaml").read_text(encoding="utf-8")
    config_path.write_text(
        config_text.replace('"<your-space-id>"', '"<your-real-space-id>"'),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="placeholder"):
        load_config(config_path)


def test_placeholder_collection_id_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_text = Path("config/app.example.yaml").read_text(encoding="utf-8")
    config_path.write_text(
        config_text.replace('"<your-space-id>"', '"real-space"').replace(
            '"<your-collection-id>"', '"<your-real-collection-id>"'
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="placeholder"):
        load_config(config_path)


def test_production_warnings_when_dry_run_disabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_text = Path("config/app.example.yaml").read_text(encoding="utf-8")
    config_path.write_text(
        _replace_placeholders(config_text).replace("dry_run: true", "dry_run: false"),
        encoding="utf-8",
    )
    config = load_config(config_path)
    warnings = check_production_warnings(config)
    assert any(w["setting"] == "anytype.dry_run" for w in warnings)


def test_production_warnings_when_email_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_text = Path("config/app.example.yaml").read_text(encoding="utf-8")
    config_path.write_text(
        _replace_placeholders(config_text).replace(
            "allow_external_services: false", "allow_external_services: true"
        )
        + """
email:
  enabled: true
  provider: gmx
  draft_folder: review/drafts
  pkv_recipient: pkv-service@example.invalid
  pkv_subject_template: "Test"
  pkv_body_template: "Body"
  pkv_sender_name: ""
  pkv_sender_policy_number: ""
  imap_host: imap.gmx.net
  imap_port: 993
  imap_username: test@example.com
  imap_password_env_key: TEST_PW
""",
        encoding="utf-8",
    )
    config = load_config(config_path)
    warnings = check_production_warnings(config)
    assert any(w["setting"] == "email.enabled" for w in warnings)


def test_anytype_extension_command_can_be_configured(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_text = Path("config/app.example.yaml").read_text(encoding="utf-8")
    config_path.write_text(
        _replace_placeholders(config_text).replace(
            "extension_command: anytype-extension-mcp-wrapper",
            "extension_command: /opt/anytype/custom-wrapper",
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.anytype.extension_command == "/opt/anytype/custom-wrapper"


def test_production_warnings_when_external_services_allowed(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_text = Path("config/app.example.yaml").read_text(encoding="utf-8")
    config_path.write_text(
        _replace_placeholders(config_text).replace(
            "allow_external_services: false", "allow_external_services: true"
        ),
        encoding="utf-8",
    )
    config = load_config(config_path)
    warnings = check_production_warnings(config)
    assert any(w["setting"] == "privacy.allow_external_services" for w in warnings)


def test_no_production_warnings_in_safe_default_config(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_text = Path("config/app.example.yaml").read_text(encoding="utf-8")
    config_path.write_text(_replace_placeholders(config_text), encoding="utf-8")
    config = load_config(config_path)
    warnings = check_production_warnings(config)
    assert warnings == []


def test_external_ollama_url_requires_explicit_privacy_opt_in(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_text = Path("config/app.example.yaml").read_text(encoding="utf-8")
    config_path.write_text(
        _replace_placeholders(config_text).replace(
            "base_url: http://127.0.0.1:11434",
            "base_url: https://ollama.example.test",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="allow_external_services"):
        load_config(config_path)


def test_external_ollama_url_can_be_explicitly_allowed(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_text = Path("config/app.example.yaml").read_text(encoding="utf-8")
    config_path.write_text(
        _replace_placeholders(config_text)
        .replace(
            "base_url: http://127.0.0.1:11434",
            "base_url: https://ollama.example.test",
        )
        .replace(
            "allow_external_services: false",
            "allow_external_services: true",
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.privacy.allow_external_services is True


def test_external_email_provider_requires_explicit_privacy_opt_in(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_text = Path("config/app.example.yaml").read_text(encoding="utf-8")
    config_path.write_text(
        _replace_placeholders(config_text)
        + """
email:
  enabled: true
  provider: gmx
  draft_folder: review/drafts
  pkv_recipient: pkv-service@example.invalid
  pkv_subject_template: "Einreichung {patient}"
  pkv_body_template: "{details}"
  pkv_sender_name: ""
  pkv_sender_policy_number: ""
  imap_username: test@example.com
  imap_password_env_key: TEST_PASSWORD
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="email.provider"):
        load_config(config_path)


def test_run_once_rejects_external_ollama_url_without_opt_in(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    with pytest.raises(ConfigError, match="ollama_base_url"):
        run_once(pdf_path, ollama_base_url="https://ollama.example.test")
