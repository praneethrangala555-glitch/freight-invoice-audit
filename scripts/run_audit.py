"""
Freight Invoice Audit Pipeline - CLI Auditor
Audits a directory of exported freight invoices against master rate cards and shipments,
outputs line-level exception reports, and prints evaluation metrics.
"""
import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from freight_audit.generator.seed_generator import FreightDataGenerator
from freight_audit.engine.rating import RatingEngine
from freight_audit.engine.auditor import FreightAuditor
from freight_audit.evaluation.metrics import AuditMetricsEvaluator
from freight_audit.models.entities import ShipmentLeg

def main():
    parser = argparse.ArgumentParser(description="Run Freight Invoice Audit Engine")
    parser.add_argument("--scale", choices=["starter", "full"], default="starter")
    parser.add_argument("--seed", type=int, default=20261022)
    args = parser.parse_args()

    print("=" * 70)
    print("FREIGHT INVOICE AUDIT PIPELINE EXECUTION")
    print(f"Scale: {args.scale} | Seed: {args.seed}")
    print("=" * 70)

    gen = FreightDataGenerator(seed=args.seed)
    if args.scale == "full":
        bundle = gen.generate(num_carriers=100, num_shipments=20000, num_invoices=15000, num_lanes=500)
    else:
        bundle = gen.generate(num_carriers=25, num_shipments=500, num_invoices=400, num_lanes=100)

    rating_engine = RatingEngine(bundle.rate_cards)
    shipment_map = {s.shipment_id: s for s in bundle.shipments}
    legs_by_shipment: dict[str, list[ShipmentLeg]] = {}
    for leg in bundle.shipment_legs:
        legs_by_shipment.setdefault(leg.shipment_id, []).append(leg)
    acc_map = {}
    for acc in bundle.accessorials:
        acc_map.setdefault(acc.shipment_id, []).append(acc)
    rc_map = {rc.rate_card_id: rc for rc in bundle.rate_cards}

    auditor = FreightAuditor(
        rating_engine=rating_engine,
        shipments=shipment_map,
        shipment_legs=legs_by_shipment,
        shipment_accessorials=acc_map,
        rate_cards_by_id=rc_map,
    )

    print(f"\nAuditing {len(bundle.freight_invoices):,} freight invoices...")
    total_exceptions = 0
    total_overcharge = 0.0

    for inv in bundle.freight_invoices:
        lines = [l for l in bundle.invoice_lines if l.invoice_id == inv.invoice_id]
        audited_inv, _, exceptions, _ = auditor.audit_invoice(inv, lines)
        total_exceptions += len(exceptions)
        total_overcharge += max(0.0, audited_inv.audit_variance)

    print(f"Audit Complete!")
    print(f"  Total Invoices Audited:      {len(bundle.freight_invoices):,}")
    print(f"  Exceptions Raised:           {total_exceptions:,}")
    print(f"  Overcharges Flagged:         ${total_overcharge:,.2f}")

    metrics = AuditMetricsEvaluator.evaluate(bundle)
    print(f"  Precision:                   {metrics.precision * 100:.2f}%")
    print(f"  Recall:                      {metrics.recall * 100:.2f}%")
    print(f"  F1-Score:                    {metrics.f1_score:.4f}")
    print("=" * 70)

if __name__ == "__main__":
    main()
