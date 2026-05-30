import pytest
from pydantic import ValidationError

from health_importer.ai.schemas import DocumentType, DocumentTypeField


def _build(value):
    return DocumentTypeField(value=value, confidence=0.9, evidence="Honorarnote")


def test_document_type_accepts_capitalized_string() -> None:
    assert _build("Honorarnote").value is DocumentType.HONORARNOTE


def test_document_type_accepts_uppercase_and_whitespace() -> None:
    assert _build("  HONORARNOTE  ").value is DocumentType.HONORARNOTE
    assert _build("Befund").value is DocumentType.BEFUND


def test_document_type_keeps_none_and_empty_as_none() -> None:
    assert DocumentTypeField(value=None, confidence=0.0).value is None
    assert _build("").value is None


def test_document_type_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        _build("not_a_real_type")
