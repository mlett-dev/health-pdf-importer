"""Generate synthetic Kassen-Rückmeldung PDFs for testing."""

from pathlib import Path

from fpdf import FPDF


def _make_pdf(title: str, lines: list[str]) -> FPDF:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=10)
    pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    for line in lines:
        pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    return pdf


def generate_kasse_positiv_max(output_dir: Path) -> None:
    lines = [
        "Bescheid über Ihre Rechnungseinsendung",
        "",
        "Sehr geehrte Versicherte,",
        "",
        "wir haben Ihre Rechnung vom 10.04.2026 geprüft.",
        "Patient: Max",
        "Aktenzeichen: TEST-AZ-0001",
        "Leistungserbringer: Dr. med. Testarzt A, Privatärztin",
        "",
        "Erstattungsbetrag: 85,00 EUR",
        "Bescheidsdatum: 13.05.2026",
        "",
        "Mit freundlichen Grüßen",
        "Ihre Krankenkasse",
    ]
    pdf = _make_pdf("Krankenkassen-Bescheid", lines)
    pdf.output(output_dir / "kasse_positiv_max.pdf")


def generate_kasse_positiv_anna_ohne_aktenzeichen(output_dir: Path) -> None:
    lines = [
        "Rechnungsbearbeitung",
        "",
        "Sehr geehrte Versicherte,",
        "",
        "wir haben Ihre Unterlagen vom 22.03.2026 erhalten.",
        "Patient: Anna",
        "Arzt: Dr. Testarzt B",
        "",
        "Erstattungsbetrag: 120,00 EUR",
        "Bescheidsdatum: 05.05.2026",
        "",
        "Mit freundlichen Grüßen",
        "Ihre Krankenkasse",
    ]
    pdf = _make_pdf("Bescheid", lines)
    pdf.output(output_dir / "kasse_positiv_anna_ohne_aktenzeichen.pdf")


def generate_kasse_unsicher_mehrdeutig(output_dir: Path) -> None:
    lines = [
        "Bescheid",
        "",
        "Patient: Max",
        "",
        "Rechnungsbetrag: 200,00 EUR",
        "Eigenanteil: 30,00 EUR",
        "Erstattungsbetrag: 170,00 EUR",
        "Zuzahlung: 5,00 EUR",
        "",
        "Bescheidsdatum: 01.05.2026",
        "",
        "Mit freundlichen Grüßen",
    ]
    pdf = _make_pdf("Bescheid", lines)
    pdf.output(output_dir / "kasse_unsicher_mehrdeutig.pdf")


if __name__ == "__main__":
    output_dir = Path(__file__).parent / "pdfs" / "kassen"
    output_dir.mkdir(parents=True, exist_ok=True)
    generate_kasse_positiv_max(output_dir)
    generate_kasse_positiv_anna_ohne_aktenzeichen(output_dir)
    generate_kasse_unsicher_mehrdeutig(output_dir)
    print(f"Generated 3 Kassen PDFs in {output_dir}")
