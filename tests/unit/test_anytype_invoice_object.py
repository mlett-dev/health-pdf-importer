from datetime import date
from decimal import Decimal

import pytest

from health_importer.anytype.client import AnytypeObjectRef, DryRunAnytypeClient
from health_importer.anytype.doctor_matching import DoctorMatch, DoctorMatchStatus
from health_importer.anytype.invoice_object import (
    AnytypeInvoiceCreateError,
    create_invoice_object_once,
    prepare_invoice_properties,
)
from health_importer.config import AnytypeConfig, PatientEntry
from health_importer.state_db import StateDb
from health_importer.workflow.validation import ValidatedInvoice


def test_prepare_invoice_properties_maps_validated_invoice_to_anytype_payload() -> None:
    config = _config()
    properties = prepare_invoice_properties(
        _invoice(),
        config=config,
        anytype_file_id="file-1",
        doctor_match=DoctorMatch(
            status=DoctorMatchStatus.MATCHED,
            doctor=AnytypeObjectRef(id="doctor-1", name="Testarzt Eins", type_key="arzt"),
            score=100.0,
        ),
    )

    assert properties[config.date_property_id] == {"date": "2026-05-08"}
    assert properties[config.patient_tag_property_id] == {"multi_select": ["test-max-tag-id"]}
    assert properties[config.amount_property_id] == {"number": 120}
    assert properties[config.attachment_property_id] == {"files": ["file-1"]}
    assert properties[config.done_property_id] == {"checkbox": False}
    assert properties[config.doctor_property_id] == {"objects": ["doctor-1"]}


def test_prepare_invoice_properties_leaves_uncertain_doctor_empty() -> None:
    config = _config()
    properties = prepare_invoice_properties(
        _invoice(),
        config=config,
        anytype_file_id="file-1",
        doctor_match=DoctorMatch(
            status=DoctorMatchStatus.REVIEW,
            doctor=None,
            score=85.0,
            review_reason="doctor_match_below_confidence_threshold",
        ),
    )

    assert config.doctor_property_id not in properties


def test_prepare_invoice_properties_rejects_unknown_patient() -> None:
    with pytest.raises(AnytypeInvoiceCreateError):
        prepare_invoice_properties(
            _invoice(patient="Alex"), config=_config(), anytype_file_id="file-1"
        )


def test_create_invoice_object_once_creates_collection_object_and_stores_id(tmp_path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    db = StateDb(tmp_path / "state.sqlite")
    db.initialize()
    record, _ = db.register_file(pdf_path)
    client = DryRunAnytypeClient(_config())

    result = create_invoice_object_once(
        client,
        db,
        file_id=record.id,
        config=_config(),
        invoice=_invoice(),
        anytype_file_id="file-1",
    )

    assert result.reused_existing is False
    assert result.object_ref.id == "dry-run-object-1"
    assert db.get_file(record.id).anytype_object_id == "dry-run-object-1"
    assert db.get_file(record.id).status == "ANYTYPE_CREATED"
    assert [entry.operation for entry in client.operation_log] == [
        "create_object",
        "add_object_to_collection",
    ]


def test_create_invoice_object_once_reuses_existing_object_id(tmp_path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    db = StateDb(tmp_path / "state.sqlite")
    db.initialize()
    record, _ = db.register_file(pdf_path)
    db.set_status(record.id, "ANYTYPE_CREATED", anytype_object_id="object-existing")
    client = DryRunAnytypeClient(_config())

    result = create_invoice_object_once(
        client,
        db,
        file_id=record.id,
        config=_config(),
        invoice=_invoice(),
        anytype_file_id="file-1",
    )

    assert result.reused_existing is True
    assert result.object_ref.id == "object-existing"
    assert client.operation_log == []


def _invoice(*, patient: str = "Max") -> ValidatedInvoice:
    return ValidatedInvoice(
        patient_first_name=patient,
        date=date(2026, 5, 8),
        date_source="appointment_date",
        topic="Kontrolle",
        total_amount_eur=Decimal("120.00"),
        doctor_name="Testarzt Eins",
    )


def _config() -> AnytypeConfig:
    return AnytypeConfig(
        space_id="space-id",
        collection_name="Wahlarzt Rechnungen",
        collection_id="collection-id",
        custom_type_name="Wahlarztrechnung",
        custom_type_key="wahlarztrechnung",
        dry_run=True,
        patients=(
            PatientEntry(name="Max", tag="test-max-tag-id", aliases=("Maximilian",)),
            PatientEntry(name="Anna", tag="test-anna-tag-id"),
        ),
        patient_tag_property_id="test-patient-tag-id",
        amount_property_id="test-amount-id",
        date_property_id="test-date-id",
        doctor_property_id="test-doctor-id",
        gkk_property_id="test-gkk-id",
        pkv_property_id="test-pkv-id",
        pkv_eingereicht_property_id="test-pkv-eingereicht-id",
        attachment_property_id="test-attachment-id",
        done_property_id="test-done-id",
    )
