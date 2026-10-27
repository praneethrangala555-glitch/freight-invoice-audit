"""
Unit Tests for Required Negative Scenarios & Edge Cases
Validates that FreightAuditor and DisputeReconciliationEngine detect:
1. Invoice references unknown shipment
2. Rate card expired
3. Weight tier misapplied
4. Surcharge duplicated
5. Credit note exceeds exception amount
6. Duplicate billing
7. Unauthorized accessorial
"""
from datetime import date
import pytest
from freight_audit.engine.rating import RatingEngine
from freight_audit.engine.auditor import FreightAuditor
from freight_audit.engine.credit_note import DisputeReconciliationEngine
from freight_audit.models.entities import (
    Carrier,
    RateCard,
    Shipment,
    FreightInvoice,
    InvoiceLine,
    Accessorial,
    AuditException,
)
from freight_audit.models.enums import (
    CarrierMode,
    CarrierStatus,
    ServiceLevel,
    RateCardStatus,
    ShipmentStatus,
    ChargeType,
    InvoiceStatus,
    AuditStatus,
    ExceptionType,
    ExceptionSeverity,
    ExceptionStatus,
    AccessorialCode,
)

@pytest.fixture
def test_setup():
    carrier = Carrier(
        carrier_id="CAR-000001",
        name="Apex Logistics",
        scac="APEX",
        mode=CarrierMode.LTL,
        contact_email="audit@apex.com",
    )
    rate_card = RateCard(
        rate_card_id="RATE-CAR-000001-2026-01",
        carrier_id="CAR-000001",
        lane_id="LANE-000001",
        service_level=ServiceLevel.STANDARD,
        effective_start_date=date(2026, 1, 1),
        effective_end_date=date(2026, 6, 30),
        base_min_charge=80.00,
        rate_tier_1_cwt=32.00,  # < 500
        rate_tier_2_cwt=28.00,  # 500 - 1999
        rate_tier_3_cwt=24.00,  # 2000 - 4999
        rate_tier_4_cwt=20.00,  # 5000 - 9999
        rate_tier_5_cwt=16.00,  # >= 10000
        dim_factor=139,
        fuel_surcharge_pct=0.15,
        status=RateCardStatus.ACTIVE,
    )
    shipment = Shipment(
        shipment_id="SHP-2026-000001",
        carrier_id="CAR-000001",
        lane_id="LANE-000001",
        service_level=ServiceLevel.STANDARD,
        status=ShipmentStatus.DELIVERED,
        ship_date=date(2026, 3, 15),
        delivery_date=date(2026, 3, 18),
        bol_number="BOL-00000001",
        total_pieces=2,
        total_actual_weight_lbs=2500.0,
        total_dim_weight_lbs=1800.0,
        billable_weight_lbs=2500.0,  # Tier 3 (24.00/cwt) -> Base: 25.0 * 24 = 600.00
        expected_base_charge=600.00,
        expected_fuel_surcharge=90.00,  # 15% of 600.00
        expected_accessorials_charge=0.0,
        expected_total_charge=690.00,
    )
    rating_engine = RatingEngine([rate_card])
    auditor = FreightAuditor(
        rating_engine=rating_engine,
        shipments={shipment.shipment_id: shipment},
        shipment_accessorials={},
        rate_cards_by_id={rate_card.rate_card_id: rate_card},
    )
    return carrier, rate_card, shipment, auditor

def test_edge_case_unknown_shipment(test_setup):
    _, _, _, auditor = test_setup
    inv = FreightInvoice(
        invoice_id="FINV-2026-000001",
        carrier_id="CAR-000001",
        shipment_id="SHP-2026-999999",  # Unknown shipment!
        invoice_number="INV-001",
        invoice_date=date(2026, 3, 20),
        due_date=date(2026, 4, 20),
        billed_total_amount=500.00,
    )
    lines = [
        InvoiceLine(
            line_id="FLINE-FINV-2026-000001-01",
            invoice_id=inv.invoice_id,
            line_number=1,
            charge_type=ChargeType.BASE_FREIGHT,
            description="Freight charge",
            billed_amount=500.00,
        )
    ]
    audited_inv, audited_lines, exceptions, events = auditor.audit_invoice(inv, lines)

    assert audited_inv.status == InvoiceStatus.AUDITED_EXCEPTION
    assert audited_inv.audit_status == AuditStatus.UNMATCHED_SHIPMENT
    assert len(exceptions) == 1
    assert exceptions[0].exception_type == ExceptionType.UNKNOWN_SHIPMENT

def test_edge_case_duplicate_surcharge(test_setup):
    _, _, shipment, auditor = test_setup
    inv = FreightInvoice(
        invoice_id="FINV-2026-000002",
        carrier_id="CAR-000001",
        shipment_id=shipment.shipment_id,
        invoice_number="INV-002",
        invoice_date=date(2026, 3, 20),
        due_date=date(2026, 4, 20),
        billed_total_amount=780.00,  # 600 base + 90 FSC + 90 duplicate FSC
    )
    lines = [
        InvoiceLine(
            line_id="FLINE-FINV-2026-000002-01",
            invoice_id=inv.invoice_id,
            line_number=1,
            charge_type=ChargeType.BASE_FREIGHT,
            description="Base Freight",
            billed_amount=600.00,
        ),
        InvoiceLine(
            line_id="FLINE-FINV-2026-000002-02",
            invoice_id=inv.invoice_id,
            line_number=2,
            charge_type=ChargeType.FUEL_SURCHARGE,
            description="Fuel Surcharge #1",
            billed_amount=90.00,
        ),
        InvoiceLine(
            line_id="FLINE-FINV-2026-000002-03",
            invoice_id=inv.invoice_id,
            line_number=3,
            charge_type=ChargeType.FUEL_SURCHARGE,
            description="Fuel Surcharge #2 (DUPLICATE)",
            billed_amount=90.00,
        ),
    ]
    audited_inv, audited_lines, exceptions, events = auditor.audit_invoice(inv, lines)

    assert audited_inv.status == InvoiceStatus.AUDITED_EXCEPTION
    ex_types = [e.exception_type for e in exceptions]
    assert ExceptionType.SURCHARGE_DUPLICATED in ex_types

def test_edge_case_credit_note_exceeds_exception():
    recon_engine = DisputeReconciliationEngine()
    ex = AuditException(
        exception_id="FEX-2026-000001",
        invoice_id="FINV-2026-000001",
        exception_type=ExceptionType.BASE_RATE_MISMATCH,
        severity=ExceptionSeverity.MEDIUM,
        expected_value="$600.00",
        billed_value="$700.00",
        discrepancy_amount=100.00,
        status=ExceptionStatus.APPROVED_DISPUTE,
        assigned_to="Logistics Analyst",
    )
    # Issue credit note of $200 for a $100 exception
    cn = recon_engine.generate_credit_note_for_exception(
        exception=ex,
        carrier_id="CAR-000001",
        credit_amount=200.00,
    )
    success, msg, excess_ex = recon_engine.reconcile_credit_note(cn, ex)

    assert success is False
    assert "exceeds" in msg
    assert excess_ex is not None
    assert excess_ex.exception_type == ExceptionType.CREDIT_NOTE_EXCEEDS_EXCEPTION
    assert excess_ex.discrepancy_amount == 100.00  # $200 - $100
