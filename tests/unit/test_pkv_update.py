"""Tests for Pkv-Antwort Anytype update operations."""

from decimal import Decimal
from unittest.mock import MagicMock

from health_importer.anytype.kassen_update import (
    mark_invoice_done,
    update_pkv_properties,
)


def test_update_pkv_properties_dry_run() -> None:
    """Dry-run should NOT call set_property and should return planned update."""
    client = MagicMock()
    client.set_property = MagicMock()

    result = update_pkv_properties(
        client,
        object_id="obj-pkv-1",
        erstattungsbetrag_eur=Decimal("45.80"),
        pkv_property_id="pkv-prop-001",
        dry_run=True,
    )

    client.set_property.assert_not_called()
    assert result.object_id == "obj-pkv-1"
    assert result.property_id == "pkv-prop-001"
    assert result.property_name == "Pkv (€)"
    assert result.value == {"number": 45.80}
    assert result.dry_run is True


def test_update_pkv_properties_live() -> None:
    """Live mode should call set_property with the correct number value."""
    client = MagicMock()

    result = update_pkv_properties(
        client,
        object_id="obj-pkv-2",
        erstattungsbetrag_eur=Decimal("120.50"),
        pkv_property_id="pkv-prop-002",
        dry_run=False,
    )

    client.set_property.assert_called_once_with(
        "obj-pkv-2",
        "pkv-prop-002",
        {"number": 120.50},
    )
    assert result.dry_run is False
    assert result.value == {"number": 120.50}


def test_mark_invoice_done_dry_run() -> None:
    """Dry-run should NOT call set_property for Done checkbox."""
    client = MagicMock()
    client.set_property = MagicMock()

    result = mark_invoice_done(
        client,
        object_id="obj-done-1",
        dry_run=True,
    )

    client.set_property.assert_not_called()
    assert result.object_id == "obj-done-1"
    assert result.property_name == "Done"
    assert result.value == {"checkbox": True}
    assert result.dry_run is True


def test_mark_invoice_done_live() -> None:
    """Live mode should call set_property with checkbox True."""
    client = MagicMock()

    result = mark_invoice_done(
        client,
        object_id="obj-done-2",
        dry_run=False,
    )

    client.set_property.assert_called_once_with(
        "obj-done-2",
        "done",
        {"checkbox": True},
    )
    assert result.dry_run is False
    assert result.value == {"checkbox": True}


def test_mark_invoice_done_custom_property_id() -> None:
    """Should use custom done_property_id when provided."""
    client = MagicMock()

    result = mark_invoice_done(
        client,
        object_id="obj-done-3",
        done_property_id="custom-done-key",
        dry_run=True,
    )

    assert result.property_id == "custom-done-key"
