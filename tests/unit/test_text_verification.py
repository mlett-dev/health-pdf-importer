from datetime import date
from decimal import Decimal

from health_importer.workflow.text_verification import (
    extract_dates,
    extract_euro_amounts,
    verify_amount_and_date_in_text,
)


def test_extract_euro_amounts_supports_common_formats() -> None:
    text = "230,00 € und EUR 120,50 und 75.- und 1.230,00"

    assert extract_euro_amounts(text) == [
        Decimal("230.00"),
        Decimal("120.50"),
        Decimal("75"),
        Decimal("1230.00"),
    ]


def test_extract_dates_normalizes_common_formats() -> None:
    assert extract_dates("08.05.2026 und 2026-05-09") == [
        date(2026, 5, 8),
        date(2026, 5, 9),
    ]


def test_extract_euro_amounts_deduplicates_and_ignores_date_fragments() -> None:
    text = "Termin 08.05.2026 Betrag EUR 120,00, bezahlt 120,00 EUR"

    assert extract_euro_amounts(text) == [Decimal("120.00")]


def test_extract_dates_deduplicates_and_skips_invalid_dates() -> None:
    assert extract_dates("08.05.2026, 2026-05-08, 32.13.2026") == [date(2026, 5, 8)]


def test_verify_amount_and_date_in_text_accepts_matching_values() -> None:
    result = verify_amount_and_date_in_text(
        "Behandlung am 08.05.2026 Gesamtbetrag EUR 230,00",
        amount=Decimal("230.00"),
        target_date=date(2026, 5, 8),
    )

    assert result.amount_found is True
    assert result.date_found is True
    assert result.warnings == []
    assert result.needs_review is False


def test_verify_amount_and_date_in_text_warns_for_missing_and_ambiguous_values() -> None:
    result = verify_amount_and_date_in_text(
        "Betrag EUR 100,00 Teilbetrag EUR 20,00 Datum 01.01.2026",
        amount=Decimal("230.00"),
        target_date=date(2026, 5, 8),
    )

    assert result.amount_found is False
    assert result.date_found is False
    assert "amount_not_found_in_text" in result.warnings
    assert "multiple_amounts_found" in result.warnings
    assert "date_not_found_in_text" in result.warnings
