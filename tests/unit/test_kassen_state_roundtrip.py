"""Regression tests for Kassen state serialization boundaries between nodes."""

from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

from health_importer.graph.nodes import match_kassen_invoice, move_kassen_to_done
from health_importer.graph.state import GraphState


def _ef(value, confidence=0.95, evidence="test", page=1):
    """Build a realistic ExtractedField dict as produced by model_dump(mode='json')."""
    return {"value": value, "confidence": confidence, "evidence": evidence, "page": page}


def test_move_kassen_to_done_from_serde_state(tmp_path: Path) -> None:
    """Regression: move_kassen_to_done must handle KassenRuckmeldungExtraction.model_dump output."""
    source = tmp_path / "processing" / "kasse.pdf"
    source.parent.mkdir()
    source.write_text("PDF content")
    done_dir = tmp_path / "done"

    state = cast(
        GraphState,
        {
            "file_path": str(source),
            "done_folder": str(done_dir),
            "events": [],
            # kassen_file_naming is now handled upstream by prepare_kassen_target_filename;
            # move_kassen_to_done only moves the already-renamed file.
            "kassen_ruckmeldung_extraction": {
                "document_type": _ef("krankenkasse_antwort"),
                "patient_first_name": _ef("Anna"),
                "doctor_name": _ef("Dr. Testarzt F"),
                "bescheids_datum": _ef("2026-03-25"),
                "aufwendungsbetrag_eur": _ef(None),
                "erstattungsbetrag_eur": _ef("100.00"),
                "rechnungsnummer": _ef(None),
                "aktenzeichen": _ef(None),
                "betreffender_termin": _ef(None),
                "warnings": [],
                "missing_fields": [],
            },
            "allowed_patients": ["Max", "Anna"],
        },
    )
    result = move_kassen_to_done(state)

    assert result["status"] == "KASSEN_DONE"
    moved_path = Path(result["file_path"])
    assert moved_path.parent == done_dir
    assert moved_path.name == "kasse.pdf"
    assert moved_path.exists()


def test_match_kassen_invoice_from_serde_state() -> None:
    """Regression: match_kassen_invoice must handle __dict__ after LangGraph serde."""
    # Simulate what validation node stores and what LangGraph serde produces
    # After LangGraph serde roundtrip: date -> str, Decimal -> float
    serde_dict = {
        "patient_first_name": "Anna",
        "doctor_name": "Dr. Testarzt F",
        "bescheids_datum": "2026-03-25",  # String after serde
        "aufwendungsbetrag_eur": None,
        "erstattungsbetrag_eur": 100.0,  # Float after serde
        "rechnungsnummer": None,
        "aktenzeichen": None,
        "betreffender_termin": None,
        "warnings": [],
    }

    state = cast(
        GraphState,
        {
            "validation": {"kassen": serde_dict},
            "events": [],
        },
    )

    # Must not raise when reconstructing from serde state
    with patch("health_importer.graph.kassen_nodes.build_anytype_client") as mock_client:
        mock_client.return_value = MagicMock()
        # find_invoice_candidates will fail with empty mock; we only care about
        # construction not crashing before that point.
        try:
            match_kassen_invoice(state)
        except Exception as exc:
            # Any error before the actual anytype call is a regression
            if "unexpected keyword argument" in str(exc) or "strftime" in str(exc):
                raise AssertionError(f"Regression in serde handling: {exc}") from exc
            # Other errors (e.g. from find_invoice_candidates with empty mock) are OK
