from health_importer.ai.prompts import load_invoice_prompt, vision_prompt_for_page


def test_invoice_text_prompt_includes_default_pkv_insurer_names() -> None:
    prompt = load_invoice_prompt("extract_invoice_text.md")

    assert "Uniqua, Donau, Merkur" in prompt
    assert "{{pkv_insurer_names}}" not in prompt


def test_invoice_vision_prompt_includes_custom_pkv_insurer_names_and_page() -> None:
    prompt = vision_prompt_for_page(3, pkv_insurer_names=("Allianz", "Wiener Staedtische"))

    assert "Allianz, Wiener Staedtische" in prompt
    assert '"page_number": 3' in prompt
    assert "{{pkv_insurer_names}}" not in prompt
