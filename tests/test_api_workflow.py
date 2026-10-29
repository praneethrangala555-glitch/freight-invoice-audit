from datetime import date
import sqlite3

import pytest
from fastapi import HTTPException

from freight_audit.api import app as api
from freight_audit.models.enums import AuditStatus, ExceptionType


def test_api_audit_persists_records_and_reconciles_approved_credit(tmp_path):
    state_path = tmp_path / "api-state.sqlite3"
    api.init_system(state_path=state_path)
    bundle = api.bundle
    assert bundle is not None

    existing_exception_ids = {item.exception_id for item in bundle.audit_exceptions}
    existing_credit_ids = {item.credit_note_id for item in bundle.credit_notes}
    existing_resolution_ids = {
        item.event_id for item in bundle.audit_resolution_events
    }
    expected_exception_id = f"FEX-2026-{max(int(item.rsplit('-', 1)[1]) for item in existing_exception_ids) + 1:06d}"
    expected_credit_id = f"CN-2026-{max(int(item.rsplit('-', 1)[1]) for item in existing_credit_ids) + 1:06d}"
    expected_resolution_id = (
        f"REV-2026-{max(int(item.rsplit('-', 1)[1]) for item in existing_resolution_ids) + 1:06d}"
    )
    carrier_id = bundle.carriers[0].carrier_id
    unknown_shipment_id = "SHP-2026-999999"
    invoice_id = "FINV-2026-990001"
    request = api.InvoiceAuditRequest(
        invoice_id=invoice_id,
        carrier_id=carrier_id,
        shipment_id=unknown_shipment_id,
        invoice_number="API-UNKNOWN-SHIPMENT-001",
        invoice_date=date(2026, 3, 20),
        due_date=date(2026, 4, 20),
        lines=[
            {
                "line_id": f"FLINE-{invoice_id}-01",
                "invoice_id": invoice_id,
                "line_number": 1,
                "charge_type": "BASE_FREIGHT",
                "description": "Base freight",
                "billed_amount": 25.0,
            }
        ],
    )

    result = api.audit_incoming_invoice(request)
    persisted_invoice = next(
        item for item in bundle.freight_invoices if item.invoice_id == invoice_id
    )
    assert persisted_invoice.shipment_id is None
    assert persisted_invoice.shipment_reference == unknown_shipment_id
    assert result["exceptions"][0]["exception_id"] == expected_exception_id
    assert result["exceptions"][0]["exception_id"] not in existing_exception_ids
    assert any(item.invoice_id == invoice_id for item in bundle.invoice_lines)
    assert any(item.invoice_id == invoice_id for item in bundle.invoice_status_events)
    with pytest.raises(HTTPException) as duplicate_invoice_error:
        api.audit_incoming_invoice(request)
    assert duplicate_invoice_error.value.status_code == 409

    resolution = api.resolve_exception(
        expected_exception_id,
        api.DisputeResolutionRequest(
            decision="APPROVED_DISPUTE",
            decision_reason="Approve the verified portion of the claim.",
            approved_amount=20.0,
        ),
    )
    assert resolution["resolution_event"]["event_id"] == expected_resolution_id
    with pytest.raises(HTTPException) as duplicate_resolution_error:
        api.resolve_exception(
            expected_exception_id,
            api.DisputeResolutionRequest(
                decision="REJECTED_DISPUTE",
                decision_reason="A second decision must not overwrite history.",
            ),
        )
    assert duplicate_resolution_error.value.status_code == 409
    assert len(bundle.audit_resolution_events) == len(existing_resolution_ids) + 1

    credit = api.issue_credit_note(
        expected_exception_id,
        api.CreditNoteRequest(carrier_id=carrier_id, credit_amount=20.0),
    )
    assert credit["credit_note"]["credit_note_id"] == expected_credit_id
    assert credit["credit_note"]["original_exception_amount"] == 20.0
    assert credit["reconciliation_success"] is True
    assert any(
        item.credit_note_id == expected_credit_id for item in bundle.credit_notes
    )

    with pytest.raises(HTTPException) as duplicate_credit_error:
        api.issue_credit_note(
            expected_exception_id,
            api.CreditNoteRequest(carrier_id=carrier_id, credit_amount=20.0),
        )
    assert duplicate_credit_error.value.status_code == 409

    api.init_system(state_path=state_path)
    restored_bundle = api.bundle
    assert restored_bundle is not None
    restored_invoice = next(
        item for item in restored_bundle.freight_invoices
        if item.invoice_id == invoice_id
    )
    restored_exception = next(
        item for item in restored_bundle.audit_exceptions
        if item.exception_id == expected_exception_id
    )
    assert restored_invoice.shipment_reference == unknown_shipment_id
    assert restored_exception.status.value == "APPROVED_DISPUTE"
    assert any(
        item.credit_note_id == expected_credit_id
        for item in restored_bundle.credit_notes
    )
    assert any(
        item.exception_id == expected_exception_id
        for item in restored_bundle.audit_resolution_events
    )


def test_api_duplicate_detection_indexes_loaded_invoices(tmp_path):
    api.init_system(state_path=tmp_path / "api-state.sqlite3")
    bundle = api.bundle
    assert bundle is not None
    original_invoice = next(
        item
        for item in bundle.freight_invoices
        if item.shipment_id
        and item.audit_status != AuditStatus.DUPLICATE_INVOICE
    )
    invoice_id = "FINV-2026-990002"
    result = api.audit_incoming_invoice(
        api.InvoiceAuditRequest(
            invoice_id=invoice_id,
            carrier_id=original_invoice.carrier_id,
            shipment_id=original_invoice.shipment_id,
            invoice_number="API-DUPLICATE-001",
            invoice_date=date(2026, 3, 20),
            due_date=date(2026, 4, 20),
            lines=[
                {
                    "line_id": f"FLINE-{invoice_id}-01",
                    "invoice_id": invoice_id,
                    "line_number": 1,
                    "charge_type": "BASE_FREIGHT",
                    "description": "Duplicate base freight",
                    "billed_amount": 25.0,
                }
            ],
        )
    )

    assert result["exceptions"][0]["exception_type"] == ExceptionType.DUPLICATE_INVOICE


def test_api_rolls_back_audit_indexes_when_journal_write_fails(tmp_path, monkeypatch):
    api.init_system(state_path=tmp_path / "api-state.sqlite3")
    bundle = api.bundle
    assert bundle is not None
    invoice_id = "FINV-2026-990003"
    request = api.InvoiceAuditRequest(
        invoice_id=invoice_id,
        carrier_id=bundle.carriers[0].carrier_id,
        shipment_id="SHP-2026-999999",
        invoice_number="API-PERSISTENCE-FAILURE",
        invoice_date=date(2026, 3, 20),
        due_date=date(2026, 4, 20),
        lines=[
            {
                "line_id": f"FLINE-{invoice_id}-01",
                "invoice_id": invoice_id,
                "line_number": 1,
                "charge_type": "BASE_FREIGHT",
                "description": "Base freight",
                "billed_amount": 25.0,
            }
        ],
    )
    exception_counter = api.auditor.exception_counter

    def fail_persist(_records):
        raise sqlite3.OperationalError("disk unavailable")

    monkeypatch.setattr(api.state_store, "persist", fail_persist)
    with pytest.raises(HTTPException) as error:
        api.audit_incoming_invoice(request)

    assert error.value.status_code == 503
    assert api.auditor.exception_counter == exception_counter
    assert all(item.invoice_id != invoice_id for item in bundle.freight_invoices)
    assert api.auditor.billed_invoices.get(
        (request.carrier_id, request.invoice_number)
    ) is None
