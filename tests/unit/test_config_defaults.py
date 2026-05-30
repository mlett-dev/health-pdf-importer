"""Regression tests for config dataclass default values."""

from health_importer.config import KassenFileNamingConfig


def test_kassen_file_naming_config_defaults() -> None:
    """Regression: KassenFileNamingConfig must accept partial dict construction."""
    cfg = KassenFileNamingConfig(enabled=True)
    assert cfg.enabled is True
    assert cfg.pattern == "{date}_{patient}_GKK_{topic}.pdf"
    assert cfg.date_format == "%Y_%m_%d"
    assert cfg.max_topic_length == 40


def test_kassen_file_naming_config_all_fields() -> None:
    cfg = KassenFileNamingConfig(
        enabled=True,
        pattern="{date}_{patient}.pdf",
        date_format="%d-%m-%Y",
        max_topic_length=20,
    )
    assert cfg.pattern == "{date}_{patient}.pdf"
    assert cfg.date_format == "%d-%m-%Y"
    assert cfg.max_topic_length == 20
