from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class DocumentType(StrEnum):
    HONORARNOTE = "honorarnote"
    UEBERWEISUNG = "ueberweisung"
    BEFUND = "befund"
    PKV_ANTWORT = "pkv_antwort"
    KRANKENKASSE_ANTWORT = "krankenkasse_antwort"
    SONSTIGES = "sonstiges"


class ExtractedField(BaseModel):
    value: str | int | float | None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str | None = None
    page: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def evidence_or_missing_value(self) -> "ExtractedField":
        if self.value is not None and not self.evidence:
            raise ValueError("evidence is required when value is set")
        return self


class DocumentTypeField(BaseModel):
    value: DocumentType | None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str | None = None
    page: int | None = Field(default=None, ge=1)

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_document_type(cls, value: object) -> object:
        if value is None or isinstance(value, DocumentType):
            return value
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if not normalized:
                return None
            for member in DocumentType:
                if member.value.casefold() == normalized:
                    return member
        return value


class InvoiceExtraction(BaseModel):
    document_type: DocumentTypeField
    patient_first_name: ExtractedField
    doctor_name: ExtractedField
    appointment_date: ExtractedField
    invoice_date: ExtractedField
    topic: ExtractedField
    total_amount_eur: ExtractedField
    invoice_number: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    iban: ExtractedField = Field(default_factory=lambda: ExtractedField(value=None, confidence=0.0))
    diagnosis: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    line_items: list[ExtractedField] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)

    def workflow_required_missing_fields(self) -> list[str]:
        missing = []
        if self.patient_first_name.value is None:
            missing.append("patient_first_name")
        if self.appointment_date.value is None and self.invoice_date.value is None:
            missing.append("appointment_date_or_invoice_date")
        if self.topic.value is None:
            missing.append("topic")
        if self.total_amount_eur.value is None:
            missing.append("total_amount_eur")
        return missing

    def is_ready_for_code_validation(self) -> bool:
        return not self.workflow_required_missing_fields()


class VisionPageExtraction(BaseModel):
    page_number: int = Field(ge=1)
    document_type: DocumentTypeField
    patient_first_name: ExtractedField
    doctor_name: ExtractedField
    appointment_date: ExtractedField
    invoice_date: ExtractedField
    topic: ExtractedField
    total_amount_eur: ExtractedField
    invoice_number: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    iban: ExtractedField = Field(default_factory=lambda: ExtractedField(value=None, confidence=0.0))
    diagnosis: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    line_items: list[ExtractedField] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class KassenRuckmeldungExtraction(BaseModel):
    document_type: DocumentTypeField
    patient_first_name: ExtractedField
    doctor_name: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    bescheids_datum: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    aufwendungsbetrag_eur: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    erstattungsbetrag_eur: ExtractedField
    rechnungsnummer: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    aktenzeichen: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    betreffender_termin: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    warnings: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)

    def workflow_required_missing_fields(self) -> list[str]:
        missing = []
        if self.patient_first_name.value is None:
            missing.append("patient_first_name")
        if self.erstattungsbetrag_eur.value is None:
            missing.append("erstattungsbetrag_eur")
        return missing

    def is_ready_for_code_validation(self) -> bool:
        return not self.workflow_required_missing_fields()


class PkvAntwortExtraction(BaseModel):
    document_type: DocumentTypeField
    patient_first_name: ExtractedField
    doctor_name: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    erstattungsbetrag_eur: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    bescheids_datum: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    aufwendungsbetrag_eur: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    rechnungsnummer: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    betreffender_termin: ExtractedField = Field(
        default_factory=lambda: ExtractedField(value=None, confidence=0.0)
    )
    warnings: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)

    def workflow_required_missing_fields(self) -> list[str]:
        missing = []
        if self.patient_first_name.value is None:
            missing.append("patient_first_name")
        if self.erstattungsbetrag_eur.value is None:
            missing.append("erstattungsbetrag_eur")
        return missing

    def is_ready_for_code_validation(self) -> bool:
        return not self.workflow_required_missing_fields()


class VerificationStatus(StrEnum):
    VALID = "valid"
    NEEDS_REVIEW = "needs_review"
    INVALID = "invalid"


class ExtractionVerification(BaseModel):
    status: VerificationStatus
    issues: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class VisionValueVerification(BaseModel):
    amount_found: bool
    date_found: bool
    amount_evidence: str | None = None
    date_evidence: str | None = None
    warnings: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
