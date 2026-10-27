"""
Freight Invoice Audit Engine - Core Domain Entities
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

from freight_audit.models.enums import (
    CarrierMode,
    CarrierStatus,
    ServiceLevel,
    RateCardStatus,
    ShipmentStatus,
    LegStatus,
    MeasurementType,
    AccessorialCode,
    InvoiceStatus,
    AuditStatus,
    ChargeType,
    LineAuditDecision,
    ExceptionType,
    ExceptionSeverity,
    ExceptionStatus,
    CreditNoteStatus,
    ReconciliationStatus,
)

# 1. Carrier
class Carrier(BaseModel):
    carrier_id: str = Field(..., pattern=r"^CAR-\d{6}$")
    name: str
    scac: str = Field(..., pattern=r"^[A-Z]{2,4}$")
    mode: CarrierMode
    contact_email: str
    payment_terms_days: int = Field(default=30, ge=15, le=90)
    status: CarrierStatus = CarrierStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)

# 2. Lane
class Lane(BaseModel):
    lane_id: str = Field(..., pattern=r"^LANE-\d{6}$")
    origin_city: str
    origin_state: str = Field(..., min_length=2, max_length=2)
    origin_zip_prefix: str = Field(..., pattern=r"^\d{3}$")
    destination_city: str
    destination_state: str = Field(..., min_length=2, max_length=2)
    destination_zip_prefix: str = Field(..., pattern=r"^\d{3}$")
    distance_miles: float = Field(..., gt=0.0)
    standard_transit_days: int = Field(..., ge=1)

# 3. RateCard
class RateCard(BaseModel):
    rate_card_id: str = Field(..., pattern=r"^RATE-CAR-\d{6}-2026-\d{2,4}$")
    carrier_id: str = Field(..., pattern=r"^CAR-\d{6}$")
    lane_id: str = Field(..., pattern=r"^LANE-\d{6}$")
    service_level: ServiceLevel
    effective_start_date: date
    effective_end_date: date
    base_min_charge: float = Field(..., ge=0.0)
    rate_tier_1_cwt: float = Field(..., gt=0.0)  # < 500 lbs
    rate_tier_2_cwt: float = Field(..., gt=0.0)  # 500 - 1999 lbs
    rate_tier_3_cwt: float = Field(..., gt=0.0)  # 2000 - 4999 lbs
    rate_tier_4_cwt: float = Field(..., gt=0.0)  # 5000 - 9999 lbs
    rate_tier_5_cwt: float = Field(..., gt=0.0)  # >= 10000 lbs
    dim_factor: int = Field(default=139, gt=0)
    fuel_surcharge_pct: float = Field(..., ge=0.0, le=1.0)
    status: RateCardStatus = RateCardStatus.ACTIVE

# 4. Shipment
class Shipment(BaseModel):
    shipment_id: str = Field(..., pattern=r"^SHP-2026-\d{6}$")
    carrier_id: str = Field(..., pattern=r"^CAR-\d{6}$")
    lane_id: str = Field(..., pattern=r"^LANE-\d{6}$")
    service_level: ServiceLevel
    status: ShipmentStatus = ShipmentStatus.DELIVERED
    ship_date: date
    delivery_date: Optional[date] = None
    bol_number: str
    total_pieces: int = Field(..., ge=1)
    total_actual_weight_lbs: float = Field(..., ge=1.0)
    total_dim_weight_lbs: float = Field(..., ge=1.0)
    billable_weight_lbs: float = Field(..., ge=1.0)
    expected_base_charge: float = Field(default=0.0, ge=0.0)
    expected_fuel_surcharge: float = Field(default=0.0, ge=0.0)
    expected_accessorials_charge: float = Field(default=0.0, ge=0.0)
    expected_total_charge: float = Field(default=0.0, ge=0.0)
    created_at: datetime = Field(default_factory=utc_now)

# 5. ShipmentLeg
class ShipmentLeg(BaseModel):
    leg_id: str = Field(..., pattern=r"^LEG-SHP-2026-\d{6}-\d{2}$")
    shipment_id: str = Field(..., pattern=r"^SHP-2026-\d{6}$")
    leg_sequence: int = Field(..., ge=1)
    origin_location: str
    destination_location: str
    pickup_time: datetime
    delivery_time: Optional[datetime] = None
    leg_status: LegStatus = LegStatus.COMPLETED
    distance_miles: float = Field(..., gt=0.0)

# 6. WeightMeasurement
class WeightMeasurement(BaseModel):
    measurement_id: str = Field(..., pattern=r"^WM-2026-\d{6}$")
    shipment_id: str = Field(..., pattern=r"^SHP-2026-\d{6}$")
    piece_number: int = Field(..., ge=1)
    length_in: float = Field(..., ge=1.0, le=120.0)
    width_in: float = Field(..., ge=1.0, le=102.0)
    height_in: float = Field(..., ge=1.0, le=110.0)
    scale_weight_lbs: float = Field(..., ge=1.0)
    dim_weight_lbs: float = Field(..., ge=0.1)
    measurement_type: MeasurementType = MeasurementType.ORIGIN_SCALE
    measured_at: datetime = Field(default_factory=utc_now)
    scale_id: str

# 7. Accessorial
class Accessorial(BaseModel):
    accessorial_id: str = Field(..., pattern=r"^ACC-2026-\d{6}$")
    shipment_id: str = Field(..., pattern=r"^SHP-2026-\d{6}$")
    code: AccessorialCode
    description: str
    standard_fee: float = Field(..., ge=0.0)
    authorized: bool = True
    proof_document_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)

# 8. FreightInvoice
class FreightInvoice(BaseModel):
    invoice_id: str = Field(..., pattern=r"^FINV-2026-\d{6}$")
    carrier_id: str = Field(..., pattern=r"^CAR-\d{6}$")
    shipment_id: Optional[str] = None  # May be invalid/null in negative scenarios
    invoice_number: str
    invoice_date: date
    due_date: date
    currency: str = "USD"
    billed_base_charge: float = Field(default=0.0, ge=0.0)
    billed_fuel_surcharge: float = Field(default=0.0, ge=0.0)
    billed_accessorials_charge: float = Field(default=0.0, ge=0.0)
    billed_total_amount: float = Field(default=0.0, ge=0.0)
    status: InvoiceStatus = InvoiceStatus.PENDING_AUDIT
    audit_status: AuditStatus = AuditStatus.CLEARED
    audit_variance: float = 0.0
    created_at: datetime = Field(default_factory=utc_now)

# 9. InvoiceLine
class InvoiceLine(BaseModel):
    line_id: str = Field(..., pattern=r"^FLINE-FINV-2026-\d{6}-\d{2}$")
    invoice_id: str = Field(..., pattern=r"^FINV-2026-\d{6}$")
    line_number: int = Field(..., ge=1)
    charge_type: ChargeType
    description: str
    billed_rate: float = Field(default=0.0, ge=0.0)
    billed_units: float = Field(default=1.0, ge=0.0)
    billed_amount: float = Field(..., ge=0.0)
    expected_amount: float = Field(default=0.0, ge=0.0)
    variance_amount: float = 0.0
    audit_decision: LineAuditDecision = LineAuditDecision.MATCHED

# 10. AuditException
class AuditException(BaseModel):
    exception_id: str = Field(..., pattern=r"^FEX-2026-\d{6}$")
    invoice_id: str = Field(..., pattern=r"^FINV-2026-\d{6}$")
    line_id: Optional[str] = None
    exception_type: ExceptionType
    severity: ExceptionSeverity
    expected_value: str
    billed_value: str
    discrepancy_amount: float
    status: ExceptionStatus = ExceptionStatus.OPEN
    assigned_to: str = "Logistics Analyst"
    resolution_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    resolved_at: Optional[datetime] = None

# 11. CreditNote
class CreditNote(BaseModel):
    credit_note_id: str = Field(..., pattern=r"^CN-2026-\d{6}$")
    carrier_id: str = Field(..., pattern=r"^CAR-\d{6}$")
    invoice_id: str = Field(..., pattern=r"^FINV-2026-\d{6}$")
    exception_id: str = Field(..., pattern=r"^FEX-2026-\d{6}$")
    credit_note_number: str
    credit_amount: float = Field(..., gt=0.0)
    original_exception_amount: float = Field(..., gt=0.0)
    status: CreditNoteStatus = CreditNoteStatus.PENDING_CARRIER
    issue_date: date
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.RECONCILED
    created_at: datetime = Field(default_factory=utc_now)

# State Transition & Audit Event Records (Traceability & Immutable History)
class InvoiceStatusEvent(BaseModel):
    event_id: str
    invoice_id: str
    from_status: InvoiceStatus
    to_status: InvoiceStatus
    changed_by: str
    reason: str
    timestamp: datetime = Field(default_factory=utc_now)

class AuditResolutionEvent(BaseModel):
    event_id: str
    exception_id: str
    from_status: ExceptionStatus
    to_status: ExceptionStatus
    decided_by: str
    decision_reason: str
    approved_amount: float
    timestamp: datetime = Field(default_factory=utc_now)
