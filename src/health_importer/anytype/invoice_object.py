from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from health_importer.anytype.client import AnytypeClient, AnytypeObjectRef
from health_importer.anytype.doctor_matching import DoctorMatch
from health_importer.config import AnytypeConfig
from health_importer.state_db import StateDb
from health_importer.workflow.validation import ValidatedInvoice


class AnytypeInvoiceCreateError(RuntimeError):
    """Raised when an invoice object cannot be created in Anytype."""


@dataclass(frozen=True)
class InvoiceObjectResult:
    object_ref: AnytypeObjectRef
    reused_existing: bool
    properties: dict[str, dict[str, object]]


def create_invoice_object_once(
    client: AnytypeClient,
    state_db: StateDb,
    *,
    file_id: int,
    config: AnytypeConfig,
    invoice: ValidatedInvoice,
    anytype_file_id: str,
    doctor_match: DoctorMatch | None = None,
    object_name: str | None = None,
) -> InvoiceObjectResult:
    record = state_db.get_file(file_id)
    properties = prepare_invoice_properties(
        invoice,
        config=config,
        anytype_file_id=anytype_file_id,
        doctor_match=doctor_match,
    )
    name = object_name if object_name is not None else invoice.topic
    if record.anytype_object_id:
        return InvoiceObjectResult(
            object_ref=AnytypeObjectRef(
                id=record.anytype_object_id,
                name=name,
                type_key=config.custom_type_key,
            ),
            reused_existing=True,
            properties=properties,
        )

    object_ref = client.create_object(config.custom_type_key, properties, name=name)
    client.add_object_to_collection(config.collection_id, object_ref.id)
    state_db.set_status(file_id, "ANYTYPE_CREATED", anytype_object_id=object_ref.id)
    return InvoiceObjectResult(
        object_ref=object_ref,
        reused_existing=False,
        properties=properties,
    )


def prepare_invoice_properties(
    invoice: ValidatedInvoice,
    *,
    config: AnytypeConfig,
    anytype_file_id: str,
    doctor_match: DoctorMatch | None = None,
) -> dict[str, dict[str, object]]:
    patient_tag = config.patient_tags.get(invoice.patient_first_name)
    if patient_tag is None:
        raise AnytypeInvoiceCreateError(
            f"Unknown Anytype patient tag: {invoice.patient_first_name}"
        )

    properties: dict[str, dict[str, object]] = {
        config.date_property_id: {"date": invoice.date.isoformat()},
        config.patient_tag_property_id: {"multi_select": [patient_tag]},
        config.amount_property_id: {"number": _decimal_to_number(invoice.total_amount_eur)},
        config.attachment_property_id: {"files": [anytype_file_id]},
        config.done_property_id: {"checkbox": False},
    }
    if doctor_match and doctor_match.should_set_relation and doctor_match.doctor:
        properties[config.doctor_property_id] = {"objects": [doctor_match.doctor.id]}
    return properties


def _decimal_to_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)
