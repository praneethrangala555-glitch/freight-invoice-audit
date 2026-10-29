"""
Freight Invoice Audit - Dataset Generation CLI
Generates synthetic data at starter or full volume with fixed seed.
"""
import argparse
import json
from pathlib import Path
import sys
import time

# Ensure project root is in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from freight_audit.generator.seed_generator import FreightDataGenerator
from freight_audit.generator.exporters import DatasetExporter
from freight_audit.evaluation.validator import RelationalValidator
from freight_audit.evaluation.metrics import AuditMetricsEvaluator

def main():
    parser = argparse.ArgumentParser(description="Deterministic Freight Data Generator")
    parser.add_argument(
        "--scale",
        choices=["starter", "full"],
        default="starter",
        help="Scale preset: starter (500 shipments, 400 invoices) or full (100 carriers, 20,000 shipments, 15,000 invoices)",
    )
    parser.add_argument("--seed", type=int, default=20261022, help="Fixed random seed (default: 20261022)")
    parser.add_argument("--output-dir", type=str, default=None, help="Custom export directory")
    parser.add_argument("--carriers", type=int, default=None, help="Override number of carriers")
    parser.add_argument("--shipments", type=int, default=None, help="Override number of shipments")
    parser.add_argument("--invoices", type=int, default=None, help="Override number of freight invoices")
    parser.add_argument("--lanes", type=int, default=None, help="Override number of lanes")
    parser.add_argument(
        "--populate-mysql",
        action="store_true",
        help="Also write to the configured live MySQL database (otherwise export only the SQL dump).",
    )

    args = parser.parse_args()

    # Scale configuration
    if args.scale == "full":
        num_carriers = args.carriers or 100
        num_shipments = args.shipments or 20000
        num_invoices = args.invoices or 15000
        num_lanes = args.lanes or 500
        default_dir = ROOT_DIR / "data" / "full"
    else:  # starter
        num_carriers = args.carriers or 25
        num_shipments = args.shipments or 500
        num_invoices = args.invoices or 400
        num_lanes = args.lanes or 100
        default_dir = ROOT_DIR / "data" / "starter"

    out_dir = Path(args.output_dir) if args.output_dir else default_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("FREIGHT INVOICE AUDIT DATASET GENERATOR")
    print(f"Scale: {args.scale.upper()} | Seed: {args.seed}")
    print(f"Targets: {num_carriers} Carriers | {num_lanes} Lanes | {num_shipments:,} Shipments | {num_invoices:,} Invoices")
    print(f"Export Directory: {out_dir}")
    print("=" * 70)

    start_time = time.time()
    generator = FreightDataGenerator(seed=args.seed)
    bundle = generator.generate(
        num_carriers=num_carriers,
        num_shipments=num_shipments,
        num_invoices=num_invoices,
        num_lanes=num_lanes,
    )
    gen_time = time.time() - start_time
    print(f"\n[1/3] Generation Completed in {gen_time:.2f} seconds.")

    # Validation
    val_start = time.time()
    validator = RelationalValidator(bundle)
    val_result = validator.validate_all()
    val_time = time.time() - val_start
    print(f"[2/3] Validation Completed in {val_time:.2f}s: {val_result.checks_passed}/{val_result.checks_run} checks passed.")

    if not val_result.passed:
        print("\nValidation Warnings/Errors:")
        for err in val_result.errors:
            print(f"  - {err}")
        return 1
    else:
        print("  All enabled integrity, lifecycle, ground-truth, and arithmetic checks passed.")

    # Export
    exp_start = time.time()
    exporter = DatasetExporter(out_dir)
    manifest = exporter.export_all(bundle, populate_mysql=args.populate_mysql)
    exp_time = time.time() - exp_start
    print(f"[3/3] Export to CSV, JSON, and SQLite completed in {exp_time:.2f}s ({manifest['total_rows']:,} rows).")

    # Evaluation
    eval_report = AuditMetricsEvaluator.evaluate(bundle)
    print("\n" + "=" * 70)
    print("EVALUATION & BENCHMARK SUMMARY")
    print("=" * 70)
    print(f"Invoices Audited:            {eval_report.total_invoices_audited:,}")
    print(f"Clean Baseline Invoices:     {eval_report.clean_baseline_count:,}")
    print(f"Injected Anomaly Invoices:   {eval_report.anomalous_invoices_count:,}")
    print(f"Audit Precision:             {eval_report.precision * 100:.2f}%")
    print(f"Audit Recall:                {eval_report.recall * 100:.2f}%")
    print(f"Audit F1 Score:              {eval_report.f1_score:.4f}")
    print(f"Classification Accuracy:     {eval_report.accuracy * 100:.2f}%")
    print(f"Total Billed Spend:          ${eval_report.total_spend_billed_usd:,.2f}")
    print(f"Total Expected Spend:        ${eval_report.total_spend_expected_usd:,.2f}")
    print(f"Overcharge Discrepancies:    ${eval_report.total_overcharge_detected_usd:,.2f}")
    print(f"Credit Notes Issued:         ${eval_report.credit_notes_issued_usd:,.2f}")
    print(f"Recovery Rate:               {eval_report.recovery_rate_pct:.2f}%")
    print("=" * 70)

    # Save validation & evaluation summary
    summary_path = out_dir / "validation_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "scale": args.scale,
                "seed": args.seed,
                "generation_time_sec": round(gen_time, 2),
                "validation_passed": val_result.passed,
                "checks_passed": val_result.checks_passed,
                "checks_total": val_result.checks_run,
                "performance_metrics": {
                    "precision": eval_report.precision,
                    "recall": eval_report.recall,
                    "f1_score": eval_report.f1_score,
                    "accuracy": eval_report.accuracy,
                    "total_spend_billed": eval_report.total_spend_billed_usd,
                    "total_spend_expected": eval_report.total_spend_expected_usd,
                    "total_overcharge_detected": eval_report.total_overcharge_detected_usd,
                    "credit_notes_issued": eval_report.credit_notes_issued_usd,
                    "credit_notes_reconciled": eval_report.credit_notes_reconciled_usd,
                    "credit_notes_overcredited": eval_report.credit_notes_overcredited_usd,
                    "credit_notes_reconciled_count": eval_report.credit_notes_reconciled_count,
                    "credit_notes_overcredited_count": eval_report.credit_notes_overcredited_count,
                    "recovery_rate_pct": eval_report.recovery_rate_pct,
                },
                "anomalies_breakdown": eval_report.anomalies_by_category,
                "credit_notes_breakdown": eval_report.credit_notes_by_category,
                "validation_errors": val_result.errors,
            },
            f,
            indent=2,
        )
    return 0

if __name__ == "__main__":
    sys.exit(main())
