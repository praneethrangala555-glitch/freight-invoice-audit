"""
Unit Tests for End-to-End Freight Invoice Audit Pipeline
"""
from datetime import date
import pytest
from freight_audit.engine.rating import RatingEngine
from freight_audit.engine.auditor import FreightAuditor
from freight_audit.models.entities import (
    Carrier,
    RateCard,
    Shipment,
    FreightInvoice,
    InvoiceLine,
    Accessorial,
)
from freight_audit.models.enums import (
    CarrierMode,
    ServiceLevel,
    RateCardStatus,
    ShipmentStatus,
    ChargeType,
    InvoiceStatus,
    AuditStatus,
    LineAuditDecision,
    AccessorialCode,
)

@pytest.fixture
def audit_fixture():
    carrier = Carrier(
        carrier_id="CAR-000001",
        name="Global Freight",
        scac="GLFR",
        mode=CarrierMode.LTL,
        contact_email="audit@glfr.com",
    )
    rate_card = RateCard(
        rate_card_id="RATE-CAR-000001-2026-01",
        carrier_id="CAR-000001",
        lane_id="LANE-000001",
        service_level=ServiceLevel.STANDARD,
        effective_start_date=date(2026, 1, 1),
        effective_end_date=date(2026, 12, 31),
        base_min_charge=100.00,
        rate_tier_1_cwt=40.00,  # < 500 lbs
        rate_tier_2_cwt=35.00,  # 500 - 1999 lbs
        rate_tier_3_cwt=30.00,  # 2000 - 4999 lbs
        rate_tier_4_cwt=25.00,  # 5000 - 9999 lbs
        rate_tier_5_cwt=20.00,  # >= 10000 lbs
        dim_factor=139,
        fuel_surcharge_pct=0.18,
        status=RateCardStatus.ACTIVE,
    )
    acc = Accessorial(
        accessorial_id="ACC-2026-000001",
        shipment_id="SHP-2026-000001",
        code=AccessorialCode.LIFTGATE,
        description="Liftgate Delivery",
        standard_fee=75.00,
        authorized=True,
    )
    shipment = Shipment(
        shipment_id="SHP-2026-000001",
        carrier_id="CAR-000001",
        lane_id="LANE-000001",
        service_level=ServiceLevel.STANDARD,
        status=ShipmentStatus.DELIVERED,
        ship_date=date(2026, 4, 1),
        delivery_date=date(2026, 4, 3),
        bol_number="BOL-20260001",
        total_pieces=1,
        total_actual_weight_lbs=1000.0,
        total_dim_weight_lbs=800.0,
        billable_weight_lbs=1000.0,  # Tier 2 (35.00/cwt) -> 10.0 * 35 = $350.00
        expected_base_charge=350.00,
        expected_fuel_surcharge=63.00,  # 18% of 350.00
        expected_accessorials_charge=75.00,
        expected_total_charge=488.00,
    )
    rating_engine = RatingEngine([rate_card])
    auditor = FreightAuditor(
        rating_engine=rating_engine,
        shipments={shipment.shipment_id: shipment},
        shipment_accessorials={shipment.shipment_id: [acc]},
        rate_cards_by_id={rate_card.rate_card_id: rate_card},
    )
    return carrier, rate_card, shipment, acc, auditor

def test_clean_baseline_audit_approval(audit_fixture):
    _, _, shipment, acc, auditor = audit_fixture
    inv = FreightInvoice(
        invoice_id="FINV-2026-000001",
        carrier_id="CAR-000001",
        shipment_id=shipment.shipment_id,
        invoice_number="INV-1001",
        invoice_date=date(2026, 4, 10),
        due_date=date(2026, 5, 10),
        billed_total_amount=488.00,
    )
    lines = [
        InvoiceLine(
            line_id="FLINE-FINV-2026-000001-01",
            invoice_id=inv.invoice_id,
            line_number=1,
            charge_type=ChargeType.BASE_FREIGHT,
            description="Base Freight",
            billed_amount=350.00,
        ),
        InvoiceLine(
            line_id="FLINE-FINV-2026-000001-02",
            invoice_id=inv.invoice_id,
            line_number=2,
            charge_type=ChargeType.FUEL_SURCHARGE,
            description="Diesel Fuel Surcharge",
            billed_amount=63.00,
        ),
        InvoiceLine(
            line_id="FLINE-FINV-2026-000001-03",
            invoice_id=inv.invoice_id,
            line_number=3,
            charge_type=ChargeType.ACCESSORIAL,
            description="Liftgate Delivery",
            billed_amount=75.00,
        ),
    ]

    audited_inv, audited_lines, exceptions, events = auditor.audit_invoice(inv, lines)

    assert audited_inv.status == InvoiceStatus.AUDITED_APPROVED
    assert audited_inv.audit_status == AuditStatus.CLEARED
    assert audited_inv.audit_variance == 0.0
    assert len(exceptions) == 0
    for l in audited_lines:
        assert l.audit_decision == LineAuditDecision.MATCHED
        assert l.variance_amount == 0.0

def test_duplicate_invoice_detection(audit_fixture):
    _, _, shipment, _, auditor = audit_fixture
    # First bill
    inv1 = FreightInvoice(
        invoice_id="FINV-2026-000001",
        carrier_id="CAR-000001",
        shipment_id=shipment.shipment_id,
        invoice_number="INV-1001",
        invoice_date=date(2026, 4, 10),
        due_date=date(2026, 5, 10),
        billed_total_amount=488.00,
    )
    lines1 = [
        InvoiceLine(
            line_id="FLINE-FINV-2026-000001-01",
            invoice_id=inv1.invoice_id,
            line_number=1,
            charge_type=ChargeType.BASE_FREIGHT,
            description="Base Freight",
            billed_amount=488.00,
        )
    ]
    auditor.audit_invoice(inv1, lines1)

    # Second bill for exact same shipment!
    inv2 = FreightInvoice(
        invoice_id="FINV-2026-000002",
        carrier_id="CAR-000001",
        shipment_id=shipment.shipment_id,
        invoice_number="INV-1002",
        invoice_date=date(2026, 4, 25),
        due_date=date(2026, 5, 25),
        billed_total_amount=488.00,
    )
    lines2 = [
        InvoiceLine(
            line_id="FLINE-FINV-2026-000002-01",
            invoice_id=inv2.invoice_id,
            line_number=1,
            charge_type=ChargeType.BASE_FREIGHT,
            description="Base Freight",
            billed_amount=488.00,
        )
    ]
    audited_inv2, audited_lines2, exceptions2, events2 = auditor.audit_invoice(inv2, lines2)

    assert audited_inv2.status == InvoiceStatus.AUDITED_EXCEPTION
    assert audited_inv2.audit_status == AuditStatus.DUPLICATE_INVOICE
    assert len(exceptions2) == 1
    assert exceptions2[0].exception_type.value == "DUPLICATE_INVOICE"
