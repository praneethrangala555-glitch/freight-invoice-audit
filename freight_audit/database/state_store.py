"""Durable journal for API and dashboard workflow changes."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, TYPE_CHECKING

from pydantic import BaseModel

from freight_audit.models.entities import (
    AuditException,
    AuditResolutionEvent,
    CreditNote,
    FreightInvoice,
    InvoiceLine,
    InvoiceStatusEvent,
)

if TYPE_CHECKING:
    from freight_audit.generator.seed_generator import DatasetBundle


_RECORD_TYPES: dict[str, tuple[type[BaseModel], str, str, bool]] = {
    "FreightInvoice": (FreightInvoice, "freight_invoices", "invoice_id", False),
    "InvoiceLine": (InvoiceLine, "invoice_lines", "line_id", False),
    "AuditException": (AuditException, "audit_exceptions", "exception_id", False),
    "CreditNote": (CreditNote, "credit_notes", "credit_note_id", False),
    "InvoiceStatusEvent": (
        InvoiceStatusEvent,
        "invoice_status_events",
        "event_id",
        True,
    ),
    "AuditResolutionEvent": (
        AuditResolutionEvent,
        "audit_resolution_events",
        "event_id",
        True,
    ),
}


class RuntimeStateStore:
    """Stores runtime records separately from the generated baseline dataset."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_records (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_type TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE (record_type, record_id)
                )
                """
            )

    def persist(self, records: Iterable[BaseModel]) -> None:
        rows = []
        for record in records:
            record_type = type(record).__name__
            if record_type not in _RECORD_TYPES:
                raise TypeError(f"Unsupported persisted record type: {record_type}")
            _, _, id_field, append_only = _RECORD_TYPES[record_type]
            record_id = getattr(record, id_field)
            rows.append(
                (record_type, record_id, record.model_dump_json(), append_only)
            )

        with sqlite3.connect(self.path, timeout=30) as connection:
            for record_type, record_id, payload, append_only in rows:
                if append_only:
                    connection.execute(
                        """
                        INSERT INTO runtime_records (record_type, record_id, payload)
                        VALUES (?, ?, ?)
                        """,
                        (record_type, record_id, payload),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO runtime_records (record_type, record_id, payload)
                        VALUES (?, ?, ?)
                        ON CONFLICT (record_type, record_id)
                        DO UPDATE SET payload = excluded.payload
                        """,
                        (record_type, record_id, payload),
                    )

    def restore(self, bundle: DatasetBundle) -> None:
        """Overlay saved runtime records on a freshly generated bundle."""
        with sqlite3.connect(self.path) as connection:
            saved_rows = connection.execute(
                """
                SELECT record_type, payload
                FROM runtime_records
                ORDER BY sequence
                """
            ).fetchall()

        for record_type, payload in saved_rows:
            model, attribute, id_field, _ = _RECORD_TYPES[record_type]
            record = model.model_validate_json(payload)
            records = getattr(bundle, attribute)
            matching_index = next(
                (
                    index
                    for index, existing in enumerate(records)
                    if getattr(existing, id_field) == getattr(record, id_field)
                ),
                None,
            )
            if matching_index is None:
                records.append(record)
            else:
                records[matching_index] = record
