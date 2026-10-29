"""
Freight Invoice Audit Engine - Core Domain Entities
"""
from datetime import date, datetime, timezone
from decimal import Decimal
import math
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator

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

    @field_validator("contact_email")
    @classmethod
    def validate_contact_email(cls, value: str) -> str:
        import re

        if not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value):
            raise ValueError("Contact email must have a valid mailbox and domain.")
        return value

    @field_validator("payment_terms_days")
    @classmethod
    def validate_payment_terms(cls, value: int) -> int:
        if value not in {15, 30, 45, 60, 90}:
            raise ValueError("Payment terms must be one of 15, 30, 45, 60, or 90 days.")
        return value

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

    @field_validator("origin_state", "destination_state")
    @classmethod
    def validate_state_code(cls, value: str) -> str:
        states = {
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI",
            "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI",
            "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC",
            "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT",
            "VT", "VA", "WA", "WV", "WI", "WY", "DC",
        }
        if value not in states:
            raise ValueError("State must be a valid US postal abbreviation.")
        return value

    @model_validator(mode="after")
    def validate_transit_days(self):
        expected = max(1, math.ceil(self.distance_miles / 500.0))
        if self.standard_transit_days != expected:
            raise ValueError("Transit days must equal ceil(distance_miles / 500).")
        return self

# 3. RateCard
class RateCard(BaseModel):
    rate_card_id: str = Field(..., pattern=r"^RATE-CAR-\d{6}-2026-\d{2,4}$")
    carrier_id: str = Field(..., pattern=r"^CAR-\d{6}$")
    lane_id: str = Field(..., pattern=r"^LANE-\d{6}$")
    service_level: ServiceLevel
    effective_start_date: date
    effective_end_date: date
    base_min_charge: float = Field(..., ge=25.0)
    rate_tier_1_cwt: float = Field(..., gt=0.0)  # < 500 lbs
    rate_tier_2_cwt: float = Field(..., gt=0.0)  # 500 - 1999 lbs
    rate_tier_3_cwt: float = Field(..., gt=0.0)  # 2000 - 4999 lbs
    rate_tier_4_cwt: float = Field(..., gt=0.0)  # 5000 - 9999 lbs
    rate_tier_5_cwt: float = Field(..., gt=0.0)  # >= 10000 lbs
    dim_factor: int = Field(default=139)
    fuel_surcharge_pct: float = Field(..., ge=0.05, le=0.45)
    status: RateCardStatus = RateCardStatus.ACTIVE

    @model_validator(mode="after")
    def validate_rate_card(self):
        if self.effective_end_date < self.effective_start_date:
            raise ValueError("Rate card end date must not precede its start date.")
        if self.dim_factor not in {139, 166, 250}:
            raise ValueError("Dimensional factor must be 139, 166, or 250.")
        rates = [
            self.rate_tier_1_cwt, self.rate_tier_2_cwt, self.rate_tier_3_cwt,
            self.rate_tier_4_cwt, self.rate_tier_5_cwt,
        ]
        if any(earlier < later for earlier, later in zip(rates, rates[1:])):
            raise ValueError("CWT rates must be non-increasing across weight tiers.")
        return self

# 4. Shipment
class Shipment(BaseModel):
    shipment_id: str = Field(..., pattern=r"^SHP-2026-\d{6}$")
    carrier_id: str = Field(..., pattern=r"^CAR-\d{6}$")
    lane_id: str = Field(..., pattern=r"^LANE-\d{6}$")
    rate_card_id: Optional[str] = None
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

    @model_validator(mode="after")
    def validate_shipment_rollups(self):
        if self.delivery_date and self.delivery_date < self.ship_date:
            raise ValueError("Delivery date must not precede ship date.")
        if abs(self.billable_weight_lbs - max(
            self.total_actual_weight_lbs, self.total_dim_weight_lbs
        )) > 0.02:
            raise ValueError("Billable weight must equal max(actual weight, dimensional weight).")
        expected = round(
            self.expected_base_charge
            + self.expected_fuel_surcharge
            + self.expected_accessorials_charge,
            2,
        )
        if abs(self.expected_total_charge - expected) > 0.02:
            raise ValueError("Expected total must equal base, fuel, and accessorial charges.")
        if self.status == ShipmentStatus.DELIVERED and self.delivery_date is None:
            raise ValueError("Delivered shipments require a delivery date.")
        return self

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

    @model_validator(mode="after")
    def validate_leg_dates(self):
        if self.delivery_time and self.delivery_time < self.pickup_time:
            raise ValueError("Leg delivery time must not precede pickup time.")
        return self

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
    standard_fee: float = Field(..., ge=15.0, le=500.0)
    authorized: bool = True
    proof_document_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)

# 8. FreightInvoice
class FreightInvoice(BaseModel):
    invoice_id: str = Field(..., pattern=r"^FINV-2026-\d{6}$")
    carrier_id: str = Field(..., pattern=r"^CAR-\d{6}$")
    shipment_id: Optional[str] = None  # May be invalid/null in negative scenarios
    shipment_reference: Optional[str] = None
    rate_card_id: Optional[str] = None
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

    @model_validator(mode="after")
    def validate_invoice_dates(self):
        if self.due_date < self.invoice_date:
            raise ValueError("Invoice due date must not precede invoice date.")
        if self.currency != "USD":
            raise ValueError("Only USD invoices are supported.")
        return self

# 9. InvoiceLine
class InvoiceLine(BaseModel):
    line_id: str = Field(..., pattern=r"^FLINE-FINV-2026-\d{6}-\d{2}$")
    invoice_id: str = Field(..., pattern=r"^FINV-2026-\d{6}$")
    accessorial_id: Optional[str] = None
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
