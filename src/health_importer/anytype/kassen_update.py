"""Anytype update operations for Kassenrückmeldungen."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from health_importer.anytype.client import AnytypeClient, AnytypeSchemaError


@dataclass(frozen=True)
class KassenPropertyUpdate:
    object_id: str
    property_id: str
    property_name: str
    value: dict[str, Any]
    dry_run: bool


@dataclass(frozen=True)
class KassenAttachmentUpdate:
    object_id: str
    property_id: str
    file_ids: list[str]
    dry_run: bool


def update_kassen_properties(
    client: AnytypeClient,
    *,
    object_id: str,
    erstattungsbetrag_eur: Decimal,
    gkk_property_id: str,
    dry_run: bool = True,
) -> KassenPropertyUpdate:
    """Set the GKK (€) property on an existing Anytype invoice object.

    Returns a KassenPropertyUpdate describing what was (or would be) done.
    """
    value = {"number": float(erstattungsbetrag_eur)}
    if not dry_run:
        client.set_property(object_id, gkk_property_id, value)
    return KassenPropertyUpdate(
        object_id=object_id,
        property_id=gkk_property_id,
        property_name="GKK (€)",
        value=value,
        dry_run=dry_run,
    )


def attach_kassen_pdf(
    client: AnytypeClient,
    *,
    object_id: str,
    kassen_file_id: str,
    attachment_property_id: str,
    existing_file_ids: list[str] | None = None,
    dry_run: bool = True,
) -> KassenAttachmentUpdate:
    """Attach a Kassen-PDF to an existing invoice object's files property.

    Preserves existing file IDs and appends the new Kassen file ID.
    """
    existing = list(existing_file_ids or [])
    if kassen_file_id in existing:
        file_ids = existing
    else:
        file_ids = existing + [kassen_file_id]

    value = {"files": file_ids}
    if not dry_run:
        try:
            client.set_property(object_id, attachment_property_id, value)
        except AnytypeSchemaError as exc:
            # One or more existing file IDs may be dead (deleted in Anytype).
            # Parse the invalid ID from the error message and retry with a
            # cleaned list that preserves the still-valid existing files.
            dead_id_match = re.search(
                r"invalid file reference for [^:]+:\s*(\S+)",
                str(exc),
            )
            if not dead_id_match:
                raise
            dead_id = dead_id_match.group(1).strip()
            cleaned = [fid for fid in file_ids if fid != dead_id]
            if not cleaned:
                cleaned = [kassen_file_id]

            fallback = {"files": cleaned}
            client.set_property(object_id, attachment_property_id, fallback)
            return KassenAttachmentUpdate(
                object_id=object_id,
                property_id=attachment_property_id,
                file_ids=cleaned,
                dry_run=dry_run,
            )
    return KassenAttachmentUpdate(
        object_id=object_id,
        property_id=attachment_property_id,
        file_ids=file_ids,
        dry_run=dry_run,
    )


def update_pkv_properties(
    client: AnytypeClient,
    *,
    object_id: str,
    erstattungsbetrag_eur: Decimal,
    pkv_property_id: str,
    dry_run: bool = True,
) -> KassenPropertyUpdate:
    """Set the Pkv (€) property on an existing Anytype invoice object.

    Returns a KassenPropertyUpdate describing what was (or would be) done.
    """
    value = {"number": float(erstattungsbetrag_eur)}
    if not dry_run:
        client.set_property(object_id, pkv_property_id, value)
    return KassenPropertyUpdate(
        object_id=object_id,
        property_id=pkv_property_id,
        property_name="Pkv (€)",
        value=value,
        dry_run=dry_run,
    )


def mark_invoice_done(
    client: AnytypeClient,
    *,
    object_id: str,
    done_property_id: str = "done",
    dry_run: bool = True,
) -> KassenPropertyUpdate:
    """Set the Done checkbox on an existing Anytype invoice object."""
    value = {"checkbox": True}
    if not dry_run:
        client.set_property(object_id, done_property_id, value)
    return KassenPropertyUpdate(
        object_id=object_id,
        property_id=done_property_id,
        property_name="Done",
        value=value,
        dry_run=dry_run,
    )


def update_pkv_eingereicht(
    client: AnytypeClient,
    *,
    object_id: str,
    pkv_property_id: str,
    eingereicht_datum: date | None = None,
    dry_run: bool = True,
) -> KassenPropertyUpdate:
    """Set the 'Pkv eingereicht' date property on an existing Anytype invoice object.

    If no date is provided, today() is used.  This should only be called when
    the workflow is actually creating a Pkv draft (email enabled).
    """
    datum = eingereicht_datum or date.today()
    value = {"date": datum.isoformat()}
    if not dry_run:
        client.set_property(object_id, pkv_property_id, value)
    return KassenPropertyUpdate(
        object_id=object_id,
        property_id=pkv_property_id,
        property_name="Pkv eingereicht",
        value=value,
        dry_run=dry_run,
    )
