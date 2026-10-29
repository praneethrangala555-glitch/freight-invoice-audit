"""
Unit Tests for Data Generator Integrity & Validation
"""
from freight_audit.generator.seed_generator import FreightDataGenerator
from freight_audit.evaluation.validator import RelationalValidator
from freight_audit.evaluation.metrics import AuditMetricsEvaluator
from freight_audit.generator.anomalies import AnomalyCategory
from freight_audit.engine.rating import determine_weight_tier
from freight_audit.models.enums import RateCardStatus, ReconciliationStatus

def test_starter_generation_validation():
    generator = FreightDataGenerator(seed=20261022)
    bundle = generator.generate(
        num_carriers=15,
        num_shipments=300,
        num_invoices=250,
        num_lanes=50,
    )

    validator = RelationalValidator(bundle)
    result = validator.validate_all()

    assert result.passed is True
    assert result.checks_failed == 0
    assert result.checks_passed == result.checks_run

def test_ground_truth_separation():
    generator = FreightDataGenerator(seed=20261022)
    bundle = generator.generate(
        num_carriers=10,
        num_shipments=100,
        num_invoices=80,
        num_lanes=30,
    )

    # Check that ground truth contains records
    assert len(bundle.ground_truth.records) > 0

    # Ensure none of the invoice entities carry ground truth internal labels
    for inv in bundle.freight_invoices:
        inv_dict = inv.model_dump()
        assert "ground_truth" not in inv_dict
        assert "anomaly_category" not in inv_dict


def test_required_anomalies_are_truthful_and_reconciled():
    bundle = FreightDataGenerator(seed=20261022).generate(
        num_carriers=15,
        num_shipments=300,
        num_invoices=250,
        num_lanes=50,
    )
    invoice_by_id = {item.invoice_id: item for item in bundle.freight_invoices}
    shipment_by_id = {item.shipment_id: item for item in bundle.shipments}
    rate_by_id = {item.rate_card_id: item for item in bundle.rate_cards}
    gt_invoice = {
        item.target_id: item for item in bundle.ground_truth.records
        if item.target_entity == "FreightInvoice"
    }

    unknown = next(item for item in bundle.freight_invoices if item.shipment_reference)
    assert unknown.shipment_id is None
    assert unknown.shipment_reference.startswith("SHP-2026-")
    assert gt_invoice[unknown.invoice_id].anomaly_category == AnomalyCategory.UNKNOWN_SHIPMENT.value

    expired_invoice = next(
        invoice for invoice in bundle.freight_invoices
        if gt_invoice[invoice.invoice_id].anomaly_category == AnomalyCategory.RATE_CARD_EXPIRED.value
    )
    assert rate_by_id[expired_invoice.rate_card_id].status == RateCardStatus.EXPIRED

    tier_invoice = next(
        invoice for invoice in bundle.freight_invoices
        if gt_invoice[invoice.invoice_id].anomaly_category == AnomalyCategory.WEIGHT_TIER_MISAPPLIED.value
    )
    tier_shipment = shipment_by_id[tier_invoice.shipment_id]
    assert determine_weight_tier(tier_shipment.billable_weight_lbs)[0].value == "TIER_3"
    tier_line = next(
        line for line in bundle.invoice_lines
        if line.invoice_id == tier_invoice.invoice_id and line.charge_type.value == "BASE_FREIGHT"
    )
    assert tier_line.billed_rate == rate_by_id[tier_shipment.rate_card_id].rate_tier_1_cwt

    duplicate_invoice = next(
        invoice for invoice in bundle.freight_invoices
        if gt_invoice[invoice.invoice_id].anomaly_category == AnomalyCategory.DUPLICATE_INVOICE.value
    )
    assert any(
        earlier.invoice_id < duplicate_invoice.invoice_id
        and earlier.carrier_id == duplicate_invoice.carrier_id
        and earlier.shipment_id == duplicate_invoice.shipment_id
        for earlier in bundle.freight_invoices
    )

    credit_statuses = {item.reconciliation_status for item in bundle.credit_notes}
    assert ReconciliationStatus.RECONCILED in credit_statuses
    assert ReconciliationStatus.OVERCREDITED in credit_statuses
    assert all(
        item.credit_amount > item.original_exception_amount
        for item in bundle.credit_notes
        if item.reconciliation_status == ReconciliationStatus.OVERCREDITED
    )
    assert RelationalValidator(bundle).validate_all().passed

    metrics = AuditMetricsEvaluator.evaluate(bundle)
    assert metrics.precision == metrics.recall == metrics.accuracy == 1.0
    assert metrics.credit_notes_reconciled_count > 0
    assert metrics.credit_notes_overcredited_count > 0
