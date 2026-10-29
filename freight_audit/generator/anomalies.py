"""
Anomaly Injection Specification & Ground Truth Tracking
Defines labeled negative scenarios injected into synthetic freight transactions.
All injected anomalies are recorded in an isolated GroundTruth registry.
"""
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, List, Optional

class AnomalyCategory(str, Enum):
    VALID_BASELINE = "VALID_BASELINE"
    UNKNOWN_SHIPMENT = "UNKNOWN_SHIPMENT"
    RATE_CARD_EXPIRED = "RATE_CARD_EXPIRED"
    WEIGHT_TIER_MISAPPLIED = "WEIGHT_TIER_MISAPPLIED"
    SURCHARGE_DUPLICATED = "SURCHARGE_DUPLICATED"
    INVALID_ACCESSORIAL = "INVALID_ACCESSORIAL"
    DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
    CREDIT_NOTE_EXCEEDS_EXCEPTION = "CREDIT_NOTE_EXCEEDS_EXCEPTION"
    BASE_RATE_MISMATCH = "BASE_RATE_MISMATCH"

@dataclass
class GroundTruthRecord:
    target_entity: str          # 'FreightInvoice' or 'CreditNote'
    target_id: str              # e.g. FINV-2026-000042
    anomaly_category: str       # from AnomalyCategory
    expected_decision: str      # 'AUDITED_EXCEPTION', 'AUDITED_APPROVED', 'OVERCREDITED'
    expected_variance: float    # Expected financial variance in USD
    line_number: Optional[int]  # Specific line index if applicable
    explanation: str

class GroundTruthTracker:
    def __init__(self):
        self.records: List[GroundTruthRecord] = []

    def record_anomaly(
        self,
        target_entity: str,
        target_id: str,
        category: AnomalyCategory,
        expected_decision: str,
        expected_variance: float,
        line_number: Optional[int] = None,
        explanation: str = "",
    ):
        rec = GroundTruthRecord(
            target_entity=target_entity,
            target_id=target_id,
            anomaly_category=category.value,
            expected_decision=expected_decision,
            expected_variance=round(expected_variance, 2),
            line_number=line_number,
            explanation=explanation,
        )
        self.records.append(rec)

    def to_dicts(self) -> List[dict]:
        return [asdict(r) for r in self.records]
