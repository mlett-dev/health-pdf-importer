"""Tests for Anytype Kassen property updates."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from health_importer.anytype.kassen_update import (
    update_kassen_properties,
    update_pkv_eingereicht,
)


def test_update_kassen_properties_dry_run() -> None:
    """Dry-run should NOT call set_property and should return the planned update."""
    client = MagicMock()
    client.set_property = MagicMock()

    result = update_kassen_properties(
        client,
        object_id="obj-123",
        erstattungsbetrag_eur=Decimal("146.86"),
        gkk_property_id="gkk-prop-001",
        dry_run=True,
    )

    client.set_property.assert_not_called()
    assert result.object_id == "obj-123"
    assert result.property_id == "gkk-prop-001"
    assert result.property_name == "GKK (€)"
    assert result.value == {"number": 146.86}
    assert result.dry_run is True


def test_update_kassen_properties_live() -> None:
    """Live mode should call set_property with the correct number value."""
    client = MagicMock()

    result = update_kassen_properties(
        client,
        object_id="obj-456",
        erstattungsbetrag_eur=Decimal("85.00"),
        gkk_property_id="gkk-prop-002",
        dry_run=False,
    )

    client.set_property.assert_called_once_with(
        "obj-456",
        "gkk-prop-002",
        {"number": 85.00},
    )
    assert result.dry_run is False
    assert result.value == {"number": 85.00}


def test_update_kassen_properties_zero_amount() -> None:
    """Zero amount should still be passed as number: 0.0."""
    client = MagicMock()

    result = update_kassen_properties(
        client,
        object_id="obj-789",
        erstattungsbetrag_eur=Decimal("0.00"),
        gkk_property_id="gkk-prop-003",
        dry_run=True,
    )

    assert result.value == {"number": 0.0}
    client.set_property.assert_not_called()


def test_update_kassen_properties_rounding() -> None:
    """Decimal with many places should convert to float."""
    client = MagicMock()

    result = update_kassen_properties(
        client,
        object_id="obj-abc",
        erstattungsbetrag_eur=Decimal("123.4567"),
        gkk_property_id="gkk-prop-004",
        dry_run=True,
    )

    assert result.value == {"number": 123.4567}


def test_update_pkv_eingereicht_dry_run() -> None:
    """Dry-run should NOT call set_property and should return planned date update."""
    client = MagicMock()
    client.set_property = MagicMock()

    result = update_pkv_eingereicht(
        client,
        object_id="obj-pkv-1",
        pkv_property_id="pkv-prop-001",
        eingereicht_datum=date(2024, 5, 14),
        dry_run=True,
    )

    client.set_property.assert_not_called()
    assert result.object_id == "obj-pkv-1"
    assert result.property_id == "pkv-prop-001"
    assert result.property_name == "Pkv eingereicht"
    assert result.value == {"date": "2024-05-14"}
    assert result.dry_run is True


def test_update_pkv_eingereicht_live() -> None:
    """Live mode should call set_property with the correct date value."""
    client = MagicMock()

    result = update_pkv_eingereicht(
        client,
        object_id="obj-pkv-2",
        pkv_property_id="pkv-prop-002",
        eingereicht_datum=date(2024, 6, 1),
        dry_run=False,
    )

    client.set_property.assert_called_once_with(
        "obj-pkv-2",
        "pkv-prop-002",
        {"date": "2024-06-01"},
    )
    assert result.dry_run is False
    assert result.value == {"date": "2024-06-01"}


def test_update_pkv_eingereicht_defaults_to_today() -> None:
    """When no date is provided, today() should be used."""
    client = MagicMock()

    result = update_pkv_eingereicht(
        client,
        object_id="obj-pkv-3",
        pkv_property_id="pkv-prop-003",
        dry_run=True,
    )

    today_iso = date.today().isoformat()
    assert result.value == {"date": today_iso}
