from health_importer.pdf.quality import evaluate_text_quality, join_page_text


def test_good_invoice_text_routes_to_llm_text_extraction() -> None:
    text = (
        "Honorarnote Rechnung Patient Max Ordination\n"
        "Termin 10.05.2026\n"
        "Betrag EUR 120,00\n"
        + "Leistung Kontrolle " * 50
    )

    quality = evaluate_text_quality(text, min_text_chars=100)

    assert quality.score >= 0.65
    assert quality.route == "llm_text_extraction"
    assert "rechnung" in quality.matched_terms
    assert quality.date_count == 1
    assert quality.amount_count >= 1


def test_empty_or_short_text_routes_to_ocr() -> None:
    quality = evaluate_text_quality("", min_text_chars=100)

    assert quality.route == "ocr"
    assert quality.score < 0.65
    assert "below_min_text_chars" in quality.reasons
    assert "missing_amount" in quality.reasons


def test_integer_eur_amount_is_detected() -> None:
    quality = evaluate_text_quality("Rechnung Betrag EUR 120 am 10.05.2026", min_text_chars=10)

    assert quality.amount_count == 1


def test_join_page_text_preserves_page_order() -> None:
    text = join_page_text({"pages": [{"text": "Seite 1"}, {"text": "Seite 2"}]})

    assert text == "Seite 1\n\nSeite 2"
