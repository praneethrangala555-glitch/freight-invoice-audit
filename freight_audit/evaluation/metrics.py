"""
Evaluation Metrics & Financial Audit Performance Engine
Calculates precision, recall, F1, accuracy, and financial recovery ROI
benchmarked directly against the isolated ground truth.
"""
from dataclasses import dataclass
from typing import Dict, Any
from freight_audit.generator.seed_generator import DatasetBundle

@dataclass
class AuditPerformanceReport:
    total_invoices_audited: int
    clean_baseline_count: int
    anomalous_invoices_count: int
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float
    accuracy: float
    total_spend_billed_usd: float
    total_spend_expected_usd: float
    total_overcharge_detected_usd: float
    credit_notes_issued_usd: float
    credit_notes_reconciled_usd: float
    credit_notes_overcredited_usd: float
    credit_notes_reconciled_count: int
    credit_notes_overcredited_count: int
    recovery_rate_pct: float
    anomalies_by_category: Dict[str, Dict[str, Any]]
    credit_notes_by_category: Dict[str, Dict[str, Any]]

class AuditMetricsEvaluator:
    @staticmethod
    def evaluate(bundle: DatasetBundle) -> AuditPerformanceReport:
        gt_records = bundle.ground_truth.records
        gt_invoice_map = {r.target_id: r for r in gt_records if r.target_entity == "FreightInvoice"}
        gt_credit_map = {r.target_id: r for r in gt_records if r.target_entity == "CreditNote"}

        tp = 0
        tn = 0
        fp = 0
        fn = 0

        total_billed = sum(inv.billed_total_amount for inv in bundle.freight_invoices)
        total_expected = sum(line.expected_amount for line in bundle.invoice_lines)
        total_overcharge = sum(
            max(0.0, inv.audit_variance) for inv in bundle.freight_invoices
        )
        credit_notes_amt = sum(cn.credit_amount for cn in bundle.credit_notes)
        reconciled_credits = [
            credit for credit in bundle.credit_notes
            if credit.reconciliation_status.value == "RECONCILED"
        ]
        overcredited_credits = [
            credit for credit in bundle.credit_notes
            if credit.reconciliation_status.value == "OVERCREDITED"
        ]
        reconciled_credit_amount = sum(credit.credit_amount for credit in reconciled_credits)
        overcredited_excess = sum(
            max(0.0, credit.credit_amount - credit.original_exception_amount)
            for credit in overcredited_credits
        )

        category_stats: Dict[str, Dict[str, Any]] = {}
        credit_category_stats: Dict[str, Dict[str, Any]] = {}

        for inv in bundle.freight_invoices:
            gt = gt_invoice_map.get(inv.invoice_id)
            is_anomaly = gt is not None and gt.anomaly_category != "VALID_BASELINE"
            flagged = inv.status.value in ["AUDITED_EXCEPTION", "DISPUTED", "REJECTED"]

            cat = gt.anomaly_category if gt else "UNKNOWN"
            if cat not in category_stats:
                category_stats[cat] = {"count": 0, "total_variance_usd": 0.0, "detected": 0}
            category_stats[cat]["count"] += 1
            category_stats[cat]["total_variance_usd"] += max(0.0, inv.audit_variance)
            if flagged:
                category_stats[cat]["detected"] += 1

            if is_anomaly and flagged:
                tp += 1
            elif not is_anomaly and not flagged:
                tn += 1
            elif not is_anomaly and flagged:
                fp += 1
            elif is_anomaly and not flagged:
                fn += 1

        for credit in bundle.credit_notes:
            gt = gt_credit_map.get(credit.credit_note_id)
            category = gt.anomaly_category if gt else "UNKNOWN"
            stats = credit_category_stats.setdefault(
                category,
                {"count": 0, "expected_decision": gt.expected_decision if gt else "UNKNOWN", "correct": 0},
            )
            stats["count"] += 1
            actual_decision = credit.reconciliation_status.value
            if gt and gt.expected_decision == actual_decision:
                stats["correct"] += 1

        precision = round(tp / max(1, (tp + fp)), 4)
        recall = round(tp / max(1, (tp + fn)), 4)
        f1 = round(2 * (precision * recall) / max(0.0001, (precision + recall)), 4)
        accuracy = round((tp + tn) / max(1, (tp + tn + fp + fn)), 4)

        recovery_rate = round(
            (reconciled_credit_amount / max(1.0, total_overcharge)) * 100.0, 2
        )

        return AuditPerformanceReport(
            total_invoices_audited=len(bundle.freight_invoices),
            clean_baseline_count=tn + fp,
            anomalous_invoices_count=tp + fn,
            true_positives=tp,
            true_negatives=tn,
            false_positives=fp,
            false_negatives=fn,
            precision=precision,
            recall=recall,
            f1_score=f1,
            accuracy=accuracy,
            total_spend_billed_usd=round(total_billed, 2),
            total_spend_expected_usd=round(total_expected, 2),
            total_overcharge_detected_usd=round(total_overcharge, 2),
            credit_notes_issued_usd=round(credit_notes_amt, 2),
            credit_notes_reconciled_usd=round(reconciled_credit_amount, 2),
            credit_notes_overcredited_usd=round(overcredited_excess, 2),
            credit_notes_reconciled_count=len(reconciled_credits),
            credit_notes_overcredited_count=len(overcredited_credits),
            recovery_rate_pct=recovery_rate,
            anomalies_by_category=category_stats,
            credit_notes_by_category=credit_category_stats,
        )
