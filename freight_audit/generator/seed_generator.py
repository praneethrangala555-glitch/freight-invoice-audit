"""
Deterministic Synthetic Freight Data Generator
Generates realistic freight transportation datasets according to exact
parent-first dependency rules, contractual rating logic, and deliberate
labeled anomaly edge cases with strict fixed-seed reproducibility.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import random
from typing import Dict, List, Optional, Tuple

from freight_audit.generator.anomalies import (
    AnomalyCategory,
    GroundTruthTracker,
)
from freight_audit.engine.rating import (
    RatingEngine,
    calculate_dim_weight,
    determine_weight_tier,
)
from freight_audit.models.entities import (
    Carrier,
    Lane,
    RateCard,
    Shipment,
    ShipmentLeg,
    WeightMeasurement,
    Accessorial,
    FreightInvoice,
    InvoiceLine,
    AuditException,
    CreditNote,
    InvoiceStatusEvent,
    AuditResolutionEvent,
)
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

# Reference US freight logistics hubs
HUBS = [
    ("Chicago", "IL", "606"),
    ("Dallas", "TX", "750"),
    ("Atlanta", "GA", "303"),
    ("Los Angeles", "CA", "900"),
    ("New York", "NY", "100"),
    ("Columbus", "OH", "430"),
    ("Indianapolis", "IN", "462"),
    ("Kansas City", "MO", "641"),
    ("Memphis", "TN", "381"),
    ("Harrisburg", "PA", "171"),
    ("Seattle", "WA", "981"),
    ("Charlotte", "NC", "282"),
    ("Denver", "CO", "802"),
    ("Phoenix", "AZ", "850"),
    ("Salt Lake City", "UT", "841"),
]

CARRIER_PREFIXES = [
    "Apex", "Swift", "Global", "Pinnacle", "Keystone", "Falcon", "Titan", "Vanguard",
    "Atlas", "Continental", "BlueLine", "CrossCountry", "Horizon", "FreightWay", "Echo",
    "Midwest", "Patriot", "Frontier", "Sterling", "Summit", "Liberty", "Redwood", "Metro"
]

@dataclass
class DatasetBundle:
    carriers: List[Carrier]
    lanes: List[Lane]
    rate_cards: List[RateCard]
    shipments: List[Shipment]
    shipment_legs: List[ShipmentLeg]
    weight_measurements: List[WeightMeasurement]
    accessorials: List[Accessorial]
    freight_invoices: List[FreightInvoice]
    invoice_lines: List[InvoiceLine]
    audit_exceptions: List[AuditException]
    credit_notes: List[CreditNote]
    invoice_status_events: List[InvoiceStatusEvent]
    audit_resolution_events: List[AuditResolutionEvent]
    ground_truth: GroundTruthTracker

class FreightDataGenerator:
    def __init__(self, seed: int = 20261022):
        self.seed = seed
        self.rng = random.Random(seed)
        self.gt = GroundTruthTracker()

    def generate(
        self,
        num_carriers: int = 100,
        num_shipments: int = 20000,
        num_invoices: int = 15000,
        num_lanes: int = 500,
    ) -> DatasetBundle:
        """
        Generate full synthetic relational dataset in strict dependency order.
        """
        # Reset RNG with seed for 100% reproducibility
        self.rng = random.Random(self.seed)
        self.gt = GroundTruthTracker()

        # Step 2.1: Generate Carriers Master
        carriers = self._generate_carriers(num_carriers)

        # Step 2.2: Generate Lanes Master
        lanes = self._generate_lanes(num_lanes)

        # Step 2.3: Generate Rate Cards
        rate_cards = self._generate_rate_cards(carriers, lanes)
        rating_engine = RatingEngine(rate_cards)

        # Step 2.4: Generate Shipments & Dependent Handling Units (Weight Measurements, Legs, Accessorials)
        shipments, legs, measurements, accessorials = self._generate_shipments_and_events(
            num_shipments, carriers, lanes, rate_cards, rating_engine
        )

        # Step 2.5: Generate Invoices, Lines, Exceptions, and Credit Notes (with labeled edge cases)
        invoices, lines, exceptions, credit_notes, inv_events, res_events = self._generate_invoices_and_audit(
            num_invoices, carriers, shipments, rate_cards, accessorials, rating_engine
        )

        return DatasetBundle(
            carriers=carriers,
            lanes=lanes,
            rate_cards=rate_cards,
            shipments=shipments,
            shipment_legs=legs,
            weight_measurements=measurements,
            accessorials=accessorials,
            freight_invoices=invoices,
            invoice_lines=lines,
            audit_exceptions=exceptions,
            credit_notes=credit_notes,
            invoice_status_events=inv_events,
            audit_resolution_events=res_events,
            ground_truth=self.gt,
        )

    def _generate_carriers(self, count: int) -> List[Carrier]:
        carriers: List[Carrier] = []
        modes = [CarrierMode.LTL, CarrierMode.LTL, CarrierMode.LTL, CarrierMode.FTL, CarrierMode.PARCEL]
        terms = [15, 30, 30, 45, 60]

        for i in range(1, count + 1):
            carrier_id = f"CAR-{i:06d}"
            prefix = self.rng.choice(CARRIER_PREFIXES)
            name = f"{prefix} Express #{i}"
            # Unique 4-letter SCAC
            c_char = chr(65 + ((i // 676) % 26))
            b_char = chr(65 + ((i // 26) % 26))
            a_char = chr(65 + (i % 26))
            scac = f"{prefix[:2].upper()}{b_char}{a_char}"[:4]

            mode = self.rng.choice(modes)
            payment_terms = self.rng.choice(terms)
            carriers.append(
                Carrier(
                    carrier_id=carrier_id,
                    name=name,
                    scac=scac,
                    mode=mode,
                    contact_email=f"billing@{scac.lower()}freight.com",
                    payment_terms_days=payment_terms,
                    status=CarrierStatus.ACTIVE,
                    created_at=datetime(2025, 1, 1, 8, 0, 0) + timedelta(days=i % 100),
                )
            )
        return carriers

    def _generate_lanes(self, count: int) -> List[Lane]:
        lanes: List[Lane] = []
        hub_pairs: List[Tuple[Tuple[str, str, str], Tuple[str, str, str]]] = []

        for i in range(len(HUBS)):
            for j in range(len(HUBS)):
                if i != j:
                    hub_pairs.append((HUBS[i], HUBS[j]))

        for i in range(1, count + 1):
            lane_id = f"LANE-{i:06d}"
            orig, dest = hub_pairs[(i - 1) % len(hub_pairs)]
            # Realistic distance proxy
            dist = round(self.rng.uniform(180.0, 2400.0), 1)
            transit_days = max(1, int(dist // 450) + 1)

            lanes.append(
                Lane(
                    lane_id=lane_id,
                    origin_city=orig[0],
                    origin_state=orig[1],
                    origin_zip_prefix=orig[2],
                    destination_city=dest[0],
                    destination_state=dest[1],
                    destination_zip_prefix=dest[2],
                    distance_miles=dist,
                    standard_transit_days=transit_days,
                )
            )
        return lanes

    def _generate_rate_cards(self, carriers: List[Carrier], lanes: List[Lane]) -> List[RateCard]:
        rate_cards: List[RateCard] = []
        services = [ServiceLevel.STANDARD, ServiceLevel.EXPEDITED]

        for carrier in carriers:
            # Each carrier covers a subset of lanes
            rc_index = 1
            num_carrier_lanes = max(5, min(len(lanes), 15))
            chosen_lanes = self.rng.sample(lanes, num_carrier_lanes)

            for lane in chosen_lanes:
                for srv in services:
                    rate_card_id = f"RATE-{carrier.carrier_id}-2026-{rc_index:02d}"
                    rc_index += 1

                    # Realistic LTL cwt rates tiered downwards by volume
                    base_factor = 28.0 + (lane.distance_miles / 120.0)
                    if srv == ServiceLevel.EXPEDITED:
                        base_factor *= 1.4

                    t1 = round(base_factor, 2)
                    t2 = round(base_factor * 0.88, 2)
                    t3 = round(base_factor * 0.74, 2)
                    t4 = round(base_factor * 0.62, 2)
                    t5 = round(base_factor * 0.50, 2)
                    fsc = round(self.rng.uniform(0.14, 0.24), 3)

                    rate_cards.append(
                        RateCard(
                            rate_card_id=rate_card_id,
                            carrier_id=carrier.carrier_id,
                            lane_id=lane.lane_id,
                            service_level=srv,
                            effective_start_date=date(2026, 1, 1),
                            effective_end_date=date(2026, 12, 31),
                            base_min_charge=round(65.0 + (lane.distance_miles * 0.05), 2),
                            rate_tier_1_cwt=t1,
                            rate_tier_2_cwt=t2,
                            rate_tier_3_cwt=t3,
                            rate_tier_4_cwt=t4,
                            rate_tier_5_cwt=t5,
                            dim_factor=139,
                            fuel_surcharge_pct=fsc,
                            status=RateCardStatus.ACTIVE,
                        )
                    )
        return rate_cards

    def _generate_shipments_and_events(
        self,
        count: int,
        carriers: List[Carrier],
        lanes: List[Lane],
        rate_cards: List[RateCard],
        rating_engine: RatingEngine,
    ) -> Tuple[List[Shipment], List[ShipmentLeg], List[WeightMeasurement], List[Accessorial]]:
        shipments: List[Shipment] = []
        legs: List[ShipmentLeg] = []
        measurements: List[WeightMeasurement] = []
        accessorials: List[Accessorial] = []

        # Available contracted combinations
        valid_contracts = [
            (rc.carrier_id, rc.lane_id, rc.service_level, rc) for rc in rate_cards
        ]

        meas_counter = 0
        acc_counter = 0

        start_date = date(2026, 2, 1)

        for i in range(1, count + 1):
            shipment_id = f"SHP-2026-{i:06d}"
            contract = valid_contracts[(i - 1) % len(valid_contracts)]
            carrier_id, lane_id, service_level, rate_card = contract

            ship_dt = start_date + timedelta(days=self.rng.randint(0, 180))
            deliv_days = self.rng.randint(1, 6)
            deliv_dt = ship_dt + timedelta(days=deliv_days)

            # Generate piece measurements
            pieces = self.rng.randint(1, 4)
            actual_wt = 0.0
            dim_wt = 0.0

            for p in range(1, pieces + 1):
                meas_counter += 1
                length = round(self.rng.uniform(36.0, 48.0), 1)
                width = round(self.rng.uniform(36.0, 48.0), 1)
                height = round(self.rng.uniform(30.0, 72.0), 1)
                scale_w = round(self.rng.uniform(150.0, 1200.0), 1)
                dim_w = calculate_dim_weight(length, width, height, rate_card.dim_factor)

                actual_wt += scale_w
                dim_wt += dim_w

                measurements.append(
                    WeightMeasurement(
                        measurement_id=f"WM-2026-{meas_counter:06d}",
                        shipment_id=shipment_id,
                        piece_number=p,
                        length_in=length,
                        width_in=width,
                        height_in=height,
                        scale_weight_lbs=scale_w,
                        dim_weight_lbs=dim_w,
                        measurement_type=MeasurementType.ORIGIN_SCALE,
                        measured_at=datetime.combine(ship_dt, datetime.min.time()),
                        scale_id=f"SCALE-{carrier_id[-4:]}-01",
                    )
                )

            actual_wt = round(actual_wt, 2)
            dim_wt = round(dim_wt, 2)
            billable_wt = max(actual_wt, dim_wt)

            # Optional accessorials (~30% of shipments)
            shipment_accs: List[Accessorial] = []
            if self.rng.random() < 0.35:
                acc_code = self.rng.choice([
                    AccessorialCode.LIFTGATE,
                    AccessorialCode.RESIDENTIAL,
                    AccessorialCode.INSIDE_DELIVERY,
                    AccessorialCode.APPOINTMENT,
                    AccessorialCode.HAZMAT,
                ])
                fee_map = {
                    AccessorialCode.LIFTGATE: 75.0,
                    AccessorialCode.RESIDENTIAL: 65.0,
                    AccessorialCode.INSIDE_DELIVERY: 95.0,
                    AccessorialCode.APPOINTMENT: 35.0,
                    AccessorialCode.HAZMAT: 150.0,
                }
                acc_counter += 1
                acc = Accessorial(
                    accessorial_id=f"ACC-2026-{acc_counter:06d}",
                    shipment_id=shipment_id,
                    code=acc_code,
                    description=f"Standard {acc_code.value.replace('_', ' ').title()} Service",
                    standard_fee=fee_map[acc_code],
                    authorized=True,
                    proof_document_id=f"DOC-POD-{shipment_id}",
                    created_at=datetime.combine(ship_dt, datetime.min.time()),
                )
                accessorials.append(acc)
                shipment_accs.append(acc)

            # Calculate expected charges using Rating Engine
            breakdown = rating_engine.calculate_expected_charges(
                rate_card=rate_card,
                actual_weight_lbs=actual_wt,
                dim_weight_lbs=dim_wt,
                authorized_accessorials=shipment_accs,
            )

            shipment = Shipment(
                shipment_id=shipment_id,
                carrier_id=carrier_id,
                lane_id=lane_id,
                service_level=service_level,
                status=ShipmentStatus.DELIVERED,
                ship_date=ship_dt,
                delivery_date=deliv_dt,
                bol_number=f"BOL-{i:08d}",
                total_pieces=pieces,
                total_actual_weight_lbs=actual_wt,
                total_dim_weight_lbs=dim_wt,
                billable_weight_lbs=billable_wt,
                expected_base_charge=breakdown.base_charge,
                expected_fuel_surcharge=breakdown.fuel_surcharge_amount,
                expected_accessorials_charge=breakdown.accessorials_amount,
                expected_total_charge=breakdown.total_expected_charge,
                created_at=datetime.combine(ship_dt, datetime.min.time()),
            )
            shipments.append(shipment)

            # Generate Leg
            legs.append(
                ShipmentLeg(
                    leg_id=f"LEG-{shipment_id}-01",
                    shipment_id=shipment_id,
                    leg_sequence=1,
                    origin_location=f"Hub-{lane_id[-4:]}-Origin",
                    destination_location=f"Hub-{lane_id[-4:]}-Dest",
                    pickup_time=datetime.combine(ship_dt, datetime.min.time()),
                    delivery_time=datetime.combine(deliv_dt, datetime.min.time()),
                    leg_status=LegStatus.COMPLETED,
                    distance_miles=round(self.rng.uniform(200.0, 1500.0), 1),
                )
            )

        return shipments, legs, measurements, accessorials

    def _generate_invoices_and_audit(
        self,
        count: int,
        carriers: List[Carrier],
        shipments: List[Shipment],
        rate_cards: List[RateCard],
        accessorials: List[Accessorial],
        rating_engine: RatingEngine,
    ) -> Tuple[
        List[FreightInvoice],
        List[InvoiceLine],
        List[AuditException],
        List[CreditNote],
        List[InvoiceStatusEvent],
        List[AuditResolutionEvent],
    ]:
        invoices: List[FreightInvoice] = []
        lines: List[InvoiceLine] = []
        exceptions: List[AuditException] = []
        credit_notes: List[CreditNote] = []
        inv_events: List[InvoiceStatusEvent] = []
        res_events: List[AuditResolutionEvent] = []

        # Index accessorials by shipment_id
        acc_by_shipment: Dict[str, List[Accessorial]] = {}
        for acc in accessorials:
            acc_by_shipment.setdefault(acc.shipment_id, []).append(acc)

        # Carrier lookup
        carrier_by_id = {c.carrier_id: c for c in carriers}

        # Counters
        line_counter = 0
        ex_counter = 0
        cn_counter = 0
        rev_counter = 0

        # Anomaly allocation targets (~85% clean baseline, ~15% labeled negative edge cases)
        # Required Edge Cases:
        # 1. Invoice references unknown shipment
        # 2. Rate card expired
        # 3. Weight tier misapplied
        # 4. Surcharge duplicated
        # 5. Credit note exceeds exception amount
        # Additional realistic edge cases:
        # 6. Duplicate invoice billing
        # 7. Invalid/unauthorized accessorial

        for i in range(1, count + 1):
            invoice_id = f"FINV-2026-{i:06d}"
            shipment = shipments[(i - 1) % len(shipments)]
            carrier = carrier_by_id[shipment.carrier_id]
            inv_date = shipment.ship_date + timedelta(days=self.rng.randint(3, 14))
            due_date = inv_date + timedelta(days=carrier.payment_terms_days)

            # Determine anomaly injection slot deterministically
            # Every 10th invoice gets a specific negative edge case
            anomaly_mod = i % 25
            is_anomaly = anomaly_mod in [3, 7, 11, 15, 19, 21, 23]

            # ---------------------------------------------------------
            # Case 1: Unknown Shipment ID
            # ---------------------------------------------------------
            if is_anomaly and anomaly_mod == 3:
                phantom_id = f"SHP-2026-999{i:03d}"
                inv = FreightInvoice(
                    invoice_id=invoice_id,
                    carrier_id=carrier.carrier_id,
                    shipment_id=phantom_id,
                    invoice_number=f"INV-{carrier.carrier_id[-4:]}-{i:06d}",
                    invoice_date=inv_date,
                    due_date=due_date,
                    currency="USD",
                    billed_base_charge=285.00,
                    billed_fuel_surcharge=42.75,
                    billed_accessorials_charge=0.0,
                    billed_total_amount=327.75,
                    status=InvoiceStatus.AUDITED_EXCEPTION,
                    audit_status=AuditStatus.UNMATCHED_SHIPMENT,
                    audit_variance=327.75,
                    created_at=datetime.combine(inv_date, datetime.min.time()),
                )
                invoices.append(inv)

                # Line items
                line_counter += 1
                l1 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-01",
                    invoice_id=invoice_id,
                    line_number=1,
                    charge_type=ChargeType.BASE_FREIGHT,
                    description="Base Freight Charge",
                    billed_rate=28.50,
                    billed_units=10.0,
                    billed_amount=285.00,
                    expected_amount=0.0,
                    variance_amount=285.00,
                    audit_decision=LineAuditDecision.INVALID_LINE,
                )
                line_counter += 1
                l2 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-02",
                    invoice_id=invoice_id,
                    line_number=2,
                    charge_type=ChargeType.FUEL_SURCHARGE,
                    description="Fuel Surcharge",
                    billed_rate=0.15,
                    billed_units=1.0,
                    billed_amount=42.75,
                    expected_amount=0.0,
                    variance_amount=42.75,
                    audit_decision=LineAuditDecision.INVALID_LINE,
                )
                lines.extend([l1, l2])

                ex_counter += 1
                fex_id = f"FEX-2026-{ex_counter:06d}"
                ex = AuditException(
                    exception_id=fex_id,
                    invoice_id=invoice_id,
                    line_id=None,
                    exception_type=ExceptionType.UNKNOWN_SHIPMENT,
                    severity=ExceptionSeverity.CRITICAL,
                    expected_value="Valid active shipment ID from TMS",
                    billed_value=phantom_id,
                    discrepancy_amount=327.75,
                    status=ExceptionStatus.OPEN,
                    assigned_to="Logistics Analyst",
                    resolution_notes="Invoice references unknown or nonexistent shipment ID.",
                    created_at=datetime.combine(inv_date, datetime.min.time()),
                )
                exceptions.append(ex)

                self.gt.record_anomaly(
                    target_entity="FreightInvoice",
                    target_id=invoice_id,
                    category=AnomalyCategory.UNKNOWN_SHIPMENT,
                    expected_decision="AUDITED_EXCEPTION",
                    expected_variance=327.75,
                    line_number=None,
                    explanation=f"Referenced shipment {phantom_id} does not exist in master records.",
                )

                inv_events.append(
                    InvoiceStatusEvent(
                        event_id=f"EVT-{invoice_id}-01",
                        invoice_id=invoice_id,
                        from_status=InvoiceStatus.PENDING_AUDIT,
                        to_status=InvoiceStatus.AUDITED_EXCEPTION,
                        changed_by="Automated Freight Audit Engine",
                        reason="Invoice rejected: unknown shipment ID.",
                        timestamp=datetime.combine(inv_date, datetime.min.time()),
                    )
                )
                continue

            # ---------------------------------------------------------
            # Case 2: Expired Rate Card
            # ---------------------------------------------------------
            elif is_anomaly and anomaly_mod == 7:
                expired_variance = 75.00
                billed_base = round(shipment.expected_base_charge + expired_variance, 2)
                inv_lines: List[InvoiceLine] = []

                l1 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-01",
                    invoice_id=invoice_id,
                    line_number=1,
                    charge_type=ChargeType.BASE_FREIGHT,
                    description="Base Freight Charge (Expired Schedule)",
                    billed_rate=round(billed_base / max(1.0, (shipment.billable_weight_lbs / 100.0)), 2),
                    billed_units=round(shipment.billable_weight_lbs / 100.0, 2),
                    billed_amount=billed_base,
                    expected_amount=shipment.expected_base_charge,
                    variance_amount=expired_variance,
                    audit_decision=LineAuditDecision.OVERCHARGE,
                )
                inv_lines.append(l1)

                l2 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-02",
                    invoice_id=invoice_id,
                    line_number=2,
                    charge_type=ChargeType.FUEL_SURCHARGE,
                    description="Fuel Surcharge",
                    billed_rate=0.18,
                    billed_units=1.0,
                    billed_amount=shipment.expected_fuel_surcharge,
                    expected_amount=shipment.expected_fuel_surcharge,
                    variance_amount=0.0,
                    audit_decision=LineAuditDecision.MATCHED,
                )
                inv_lines.append(l2)

                shipment_accs = acc_by_shipment.get(shipment.shipment_id, [])
                for acc_idx, acc in enumerate(shipment_accs, start=3):
                    inv_lines.append(
                        InvoiceLine(
                            line_id=f"FLINE-{invoice_id}-{acc_idx:02d}",
                            invoice_id=invoice_id,
                            line_number=acc_idx,
                            charge_type=ChargeType.ACCESSORIAL,
                            description=acc.description,
                            billed_rate=acc.standard_fee,
                            billed_units=1.0,
                            billed_amount=acc.standard_fee,
                            expected_amount=acc.standard_fee,
                            variance_amount=0.0,
                            audit_decision=LineAuditDecision.MATCHED,
                        )
                    )

                billed_total = round(sum(l.billed_amount for l in inv_lines), 2)
                billed_accs = round(sum(l.billed_amount for l in inv_lines if l.charge_type == ChargeType.ACCESSORIAL), 2)

                inv = FreightInvoice(
                    invoice_id=invoice_id,
                    carrier_id=carrier.carrier_id,
                    shipment_id=shipment.shipment_id,
                    invoice_number=f"INV-{carrier.carrier_id[-4:]}-{i:06d}",
                    invoice_date=inv_date,
                    due_date=due_date,
                    currency="USD",
                    billed_base_charge=billed_base,
                    billed_fuel_surcharge=shipment.expected_fuel_surcharge,
                    billed_accessorials_charge=billed_accs,
                    billed_total_amount=billed_total,
                    status=InvoiceStatus.AUDITED_EXCEPTION,
                    audit_status=AuditStatus.DISCREPANCY_DETECTED,
                    audit_variance=expired_variance,
                    created_at=datetime.combine(inv_date, datetime.min.time()),
                )
                invoices.append(inv)
                lines.extend(inv_lines)

                ex_counter += 1
                fex_id = f"FEX-2026-{ex_counter:06d}"
                ex = AuditException(
                    exception_id=fex_id,
                    invoice_id=invoice_id,
                    line_id=l1.line_id,
                    exception_type=ExceptionType.RATE_CARD_EXPIRED,
                    severity=ExceptionSeverity.HIGH,
                    expected_value="Active 2026 contract schedule",
                    billed_value="Rate card expired 2025-12-31",
                    discrepancy_amount=expired_variance,
                    status=ExceptionStatus.OPEN,
                    assigned_to="Logistics Analyst",
                    resolution_notes="Rate card expired before shipment tender date.",
                    created_at=datetime.combine(inv_date, datetime.min.time()),
                )
                exceptions.append(ex)

                self.gt.record_anomaly(
                    target_entity="FreightInvoice",
                    target_id=invoice_id,
                    category=AnomalyCategory.RATE_CARD_EXPIRED,
                    expected_decision="AUDITED_EXCEPTION",
                    expected_variance=expired_variance,
                    line_number=1,
                    explanation="Carrier billed under an expired contract rate card with unauthorized rate increase.",
                )
                continue

            # ---------------------------------------------------------
            # Case 3: Weight Tier Misapplied
            # ---------------------------------------------------------
            elif is_anomaly and anomaly_mod == 11:
                # Carrier charged at Tier 1 rate instead of contracted Tier 3 volume discount rate
                tier_variance = 65.40
                billed_base = round(shipment.expected_base_charge + tier_variance, 2)
                inv_lines = []

                l1 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-01",
                    invoice_id=invoice_id,
                    line_number=1,
                    charge_type=ChargeType.BASE_FREIGHT,
                    description="Base Freight (Tier 1 misapplied)",
                    billed_rate=34.50,
                    billed_units=round(shipment.billable_weight_lbs / 100.0, 2),
                    billed_amount=billed_base,
                    expected_amount=shipment.expected_base_charge,
                    variance_amount=tier_variance,
                    audit_decision=LineAuditDecision.OVERCHARGE,
                )
                inv_lines.append(l1)

                l2 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-02",
                    invoice_id=invoice_id,
                    line_number=2,
                    charge_type=ChargeType.FUEL_SURCHARGE,
                    description="Fuel Surcharge",
                    billed_rate=0.18,
                    billed_units=1.0,
                    billed_amount=shipment.expected_fuel_surcharge,
                    expected_amount=shipment.expected_fuel_surcharge,
                    variance_amount=0.0,
                    audit_decision=LineAuditDecision.MATCHED,
                )
                inv_lines.append(l2)

                shipment_accs = acc_by_shipment.get(shipment.shipment_id, [])
                for acc_idx, acc in enumerate(shipment_accs, start=3):
                    inv_lines.append(
                        InvoiceLine(
                            line_id=f"FLINE-{invoice_id}-{acc_idx:02d}",
                            invoice_id=invoice_id,
                            line_number=acc_idx,
                            charge_type=ChargeType.ACCESSORIAL,
                            description=acc.description,
                            billed_rate=acc.standard_fee,
                            billed_units=1.0,
                            billed_amount=acc.standard_fee,
                            expected_amount=acc.standard_fee,
                            variance_amount=0.0,
                            audit_decision=LineAuditDecision.MATCHED,
                        )
                    )

                billed_total = round(sum(l.billed_amount for l in inv_lines), 2)
                billed_accs = round(sum(l.billed_amount for l in inv_lines if l.charge_type == ChargeType.ACCESSORIAL), 2)

                inv = FreightInvoice(
                    invoice_id=invoice_id,
                    carrier_id=carrier.carrier_id,
                    shipment_id=shipment.shipment_id,
                    invoice_number=f"INV-{carrier.carrier_id[-4:]}-{i:06d}",
                    invoice_date=inv_date,
                    due_date=due_date,
                    currency="USD",
                    billed_base_charge=billed_base,
                    billed_fuel_surcharge=shipment.expected_fuel_surcharge,
                    billed_accessorials_charge=billed_accs,
                    billed_total_amount=billed_total,
                    status=InvoiceStatus.AUDITED_EXCEPTION,
                    audit_status=AuditStatus.DISCREPANCY_DETECTED,
                    audit_variance=tier_variance,
                    created_at=datetime.combine(inv_date, datetime.min.time()),
                )
                invoices.append(inv)
                lines.extend(inv_lines)

                ex_counter += 1
                fex_id = f"FEX-2026-{ex_counter:06d}"
                ex = AuditException(
                    exception_id=fex_id,
                    invoice_id=invoice_id,
                    line_id=l1.line_id,
                    exception_type=ExceptionType.WEIGHT_TIER_MISAPPLIED,
                    severity=ExceptionSeverity.MEDIUM,
                    expected_value="Tier 3 CWT Rate (Weight >= 2000 lbs)",
                    billed_value="Tier 1 CWT Rate (< 500 lbs)",
                    discrepancy_amount=tier_variance,
                    status=ExceptionStatus.OPEN,
                    assigned_to="Logistics Analyst",
                    resolution_notes="Weight tier misapplied: shipment qualifies for volume discount tier.",
                    created_at=datetime.combine(inv_date, datetime.min.time()),
                )
                exceptions.append(ex)

                self.gt.record_anomaly(
                    target_entity="FreightInvoice",
                    target_id=invoice_id,
                    category=AnomalyCategory.WEIGHT_TIER_MISAPPLIED,
                    expected_decision="AUDITED_EXCEPTION",
                    expected_variance=tier_variance,
                    line_number=1,
                    explanation="Carrier failed to apply contracted volume tier discount based on actual billable weight.",
                )
                continue

            # ---------------------------------------------------------
            # Case 4: Duplicate Surcharge Line
            # ---------------------------------------------------------
            elif is_anomaly and anomaly_mod == 15:
                dup_fsc_amount = shipment.expected_fuel_surcharge
                inv_lines = []

                l1 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-01",
                    invoice_id=invoice_id,
                    line_number=1,
                    charge_type=ChargeType.BASE_FREIGHT,
                    description="Base Freight Charge",
                    billed_rate=25.00,
                    billed_units=round(shipment.billable_weight_lbs / 100.0, 2),
                    billed_amount=shipment.expected_base_charge,
                    expected_amount=shipment.expected_base_charge,
                    variance_amount=0.0,
                    audit_decision=LineAuditDecision.MATCHED,
                )
                inv_lines.append(l1)

                l2 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-02",
                    invoice_id=invoice_id,
                    line_number=2,
                    charge_type=ChargeType.FUEL_SURCHARGE,
                    description="Fuel Surcharge - Standard DOE",
                    billed_rate=0.18,
                    billed_units=1.0,
                    billed_amount=shipment.expected_fuel_surcharge,
                    expected_amount=shipment.expected_fuel_surcharge,
                    variance_amount=0.0,
                    audit_decision=LineAuditDecision.MATCHED,
                )
                inv_lines.append(l2)

                l3 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-03",
                    invoice_id=invoice_id,
                    line_number=3,
                    charge_type=ChargeType.FUEL_SURCHARGE,
                    description="Fuel Surcharge - Additional Index (DUPLICATE)",
                    billed_rate=0.18,
                    billed_units=1.0,
                    billed_amount=dup_fsc_amount,
                    expected_amount=0.0,
                    variance_amount=dup_fsc_amount,
                    audit_decision=LineAuditDecision.DUPLICATE_LINE,
                )
                inv_lines.append(l3)

                shipment_accs = acc_by_shipment.get(shipment.shipment_id, [])
                for acc_idx, acc in enumerate(shipment_accs, start=4):
                    inv_lines.append(
                        InvoiceLine(
                            line_id=f"FLINE-{invoice_id}-{acc_idx:02d}",
                            invoice_id=invoice_id,
                            line_number=acc_idx,
                            charge_type=ChargeType.ACCESSORIAL,
                            description=acc.description,
                            billed_rate=acc.standard_fee,
                            billed_units=1.0,
                            billed_amount=acc.standard_fee,
                            expected_amount=acc.standard_fee,
                            variance_amount=0.0,
                            audit_decision=LineAuditDecision.MATCHED,
                        )
                    )

                billed_total = round(sum(l.billed_amount for l in inv_lines), 2)
                billed_accs = round(sum(l.billed_amount for l in inv_lines if l.charge_type == ChargeType.ACCESSORIAL), 2)

                inv = FreightInvoice(
                    invoice_id=invoice_id,
                    carrier_id=carrier.carrier_id,
                    shipment_id=shipment.shipment_id,
                    invoice_number=f"INV-{carrier.carrier_id[-4:]}-{i:06d}",
                    invoice_date=inv_date,
                    due_date=due_date,
                    currency="USD",
                    billed_base_charge=shipment.expected_base_charge,
                    billed_fuel_surcharge=round(shipment.expected_fuel_surcharge * 2, 2),
                    billed_accessorials_charge=billed_accs,
                    billed_total_amount=billed_total,
                    status=InvoiceStatus.AUDITED_EXCEPTION,
                    audit_status=AuditStatus.DISCREPANCY_DETECTED,
                    audit_variance=dup_fsc_amount,
                    created_at=datetime.combine(inv_date, datetime.min.time()),
                )
                invoices.append(inv)
                lines.extend(inv_lines)

                ex_counter += 1
                fex_id = f"FEX-2026-{ex_counter:06d}"
                ex = AuditException(
                    exception_id=fex_id,
                    invoice_id=invoice_id,
                    line_id=l3.line_id,
                    exception_type=ExceptionType.SURCHARGE_DUPLICATED,
                    severity=ExceptionSeverity.HIGH,
                    expected_value="Single Fuel Surcharge Line",
                    billed_value=f"Duplicate Line #3 (${dup_fsc_amount:.2f})",
                    discrepancy_amount=dup_fsc_amount,
                    status=ExceptionStatus.OPEN,
                    assigned_to="Logistics Analyst",
                    resolution_notes="Duplicate fuel surcharge line billed on single freight movement.",
                    created_at=datetime.combine(inv_date, datetime.min.time()),
                )
                exceptions.append(ex)

                self.gt.record_anomaly(
                    target_entity="FreightInvoice",
                    target_id=invoice_id,
                    category=AnomalyCategory.SURCHARGE_DUPLICATED,
                    expected_decision="AUDITED_EXCEPTION",
                    expected_variance=dup_fsc_amount,
                    line_number=3,
                    explanation="Duplicate fuel surcharge line billed on the same invoice.",
                )
                continue

            # ---------------------------------------------------------
            # Case 5: Credit Note Exceeds Exception Amount
            # ---------------------------------------------------------
            elif is_anomaly and anomaly_mod == 19:
                # An exception dispute of $80.00 was approved, but credit note issued was $160.00 (overcredited)
                disp_amount = 80.00
                billed_base = round(shipment.expected_base_charge + disp_amount, 2)
                inv_lines = []

                l1 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-01",
                    invoice_id=invoice_id,
                    line_number=1,
                    charge_type=ChargeType.BASE_FREIGHT,
                    description="Base Freight Charge (Rate Variance)",
                    billed_rate=29.00,
                    billed_units=round(shipment.billable_weight_lbs / 100.0, 2),
                    billed_amount=billed_base,
                    expected_amount=shipment.expected_base_charge,
                    variance_amount=disp_amount,
                    audit_decision=LineAuditDecision.OVERCHARGE,
                )
                inv_lines.append(l1)

                l2 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-02",
                    invoice_id=invoice_id,
                    line_number=2,
                    charge_type=ChargeType.FUEL_SURCHARGE,
                    description="Fuel Surcharge",
                    billed_rate=0.18,
                    billed_units=1.0,
                    billed_amount=shipment.expected_fuel_surcharge,
                    expected_amount=shipment.expected_fuel_surcharge,
                    variance_amount=0.0,
                    audit_decision=LineAuditDecision.MATCHED,
                )
                inv_lines.append(l2)

                shipment_accs = acc_by_shipment.get(shipment.shipment_id, [])
                for acc_idx, acc in enumerate(shipment_accs, start=3):
                    inv_lines.append(
                        InvoiceLine(
                            line_id=f"FLINE-{invoice_id}-{acc_idx:02d}",
                            invoice_id=invoice_id,
                            line_number=acc_idx,
                            charge_type=ChargeType.ACCESSORIAL,
                            description=acc.description,
                            billed_rate=acc.standard_fee,
                            billed_units=1.0,
                            billed_amount=acc.standard_fee,
                            expected_amount=acc.standard_fee,
                            variance_amount=0.0,
                            audit_decision=LineAuditDecision.MATCHED,
                        )
                    )

                billed_total = round(sum(l.billed_amount for l in inv_lines), 2)
                billed_accs = round(sum(l.billed_amount for l in inv_lines if l.charge_type == ChargeType.ACCESSORIAL), 2)

                inv = FreightInvoice(
                    invoice_id=invoice_id,
                    carrier_id=carrier.carrier_id,
                    shipment_id=shipment.shipment_id,
                    invoice_number=f"INV-{carrier.carrier_id[-4:]}-{i:06d}",
                    invoice_date=inv_date,
                    due_date=due_date,
                    currency="USD",
                    billed_base_charge=billed_base,
                    billed_fuel_surcharge=shipment.expected_fuel_surcharge,
                    billed_accessorials_charge=billed_accs,
                    billed_total_amount=billed_total,
                    status=InvoiceStatus.AUDITED_EXCEPTION,
                    audit_status=AuditStatus.DISCREPANCY_DETECTED,
                    audit_variance=disp_amount,
                    created_at=datetime.combine(inv_date, datetime.min.time()),
                )
                invoices.append(inv)
                lines.extend(inv_lines)

                ex_counter += 1
                fex_id = f"FEX-2026-{ex_counter:06d}"
                ex = AuditException(
                    exception_id=fex_id,
                    invoice_id=invoice_id,
                    line_id=l1.line_id,
                    exception_type=ExceptionType.BASE_RATE_MISMATCH,
                    severity=ExceptionSeverity.MEDIUM,
                    expected_value=f"${shipment.expected_base_charge:.2f}",
                    billed_value=f"${billed_base:.2f}",
                    discrepancy_amount=disp_amount,
                    status=ExceptionStatus.APPROVED_DISPUTE,
                    assigned_to="Operations Manager",
                    resolution_notes="Dispute approved by Operations Manager; awaiting credit note.",
                    created_at=datetime.combine(inv_date, datetime.min.time()),
                    resolved_at=datetime.combine(inv_date + timedelta(days=2), datetime.min.time()),
                )
                exceptions.append(ex)

                rev_counter += 1
                res_events.append(
                    AuditResolutionEvent(
                        event_id=f"REV-2026-{rev_counter:06d}",
                        exception_id=fex_id,
                        from_status=ExceptionStatus.OPEN,
                        to_status=ExceptionStatus.APPROVED_DISPUTE,
                        decided_by="Operations Manager",
                        decision_reason="Carrier acknowledged rate card discrepancy.",
                        approved_amount=disp_amount,
                        timestamp=datetime.combine(inv_date + timedelta(days=2), datetime.min.time()),
                    )
                )

                # Now generate CreditNote that EXCEEDS the exception amount!
                cn_counter += 1
                cn_id = f"CN-2026-{cn_counter:06d}"
                excess_credit = round(disp_amount * 2.0, 2)  # $160.00 instead of $80.00
                cn = CreditNote(
                    credit_note_id=cn_id,
                    carrier_id=carrier.carrier_id,
                    invoice_id=invoice_id,
                    exception_id=fex_id,
                    credit_note_number=f"CN-{carrier.carrier_id[-4:]}-2026-{cn_counter:04d}",
                    credit_amount=excess_credit,
                    original_exception_amount=disp_amount,
                    status=CreditNoteStatus.APPLIED,
                    issue_date=inv_date + timedelta(days=5),
                    reconciliation_status=ReconciliationStatus.OVERCREDITED,
                    created_at=datetime.combine(inv_date + timedelta(days=5), datetime.min.time()),
                )
                credit_notes.append(cn)

                self.gt.record_anomaly(
                    target_entity="CreditNote",
                    target_id=cn_id,
                    category=AnomalyCategory.CREDIT_NOTE_EXCEEDS_EXCEPTION,
                    expected_decision="OVERCREDITED",
                    expected_variance=round(excess_credit - disp_amount, 2),
                    line_number=None,
                    explanation=f"Credit note {cn_id} issued for ${excess_credit:.2f} exceeds approved exception of ${disp_amount:.2f}.",
                )
                continue

            # ---------------------------------------------------------
            # Case 6: Duplicate Invoice Billing (Same shipment billed twice)
            # ---------------------------------------------------------
            elif is_anomaly and anomaly_mod == 21:
                inv_lines = []

                l1 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-01",
                    invoice_id=invoice_id,
                    line_number=1,
                    charge_type=ChargeType.BASE_FREIGHT,
                    description="Duplicate Base Freight Billing",
                    billed_rate=25.00,
                    billed_units=round(shipment.billable_weight_lbs / 100.0, 2),
                    billed_amount=shipment.expected_base_charge,
                    expected_amount=0.0,
                    variance_amount=shipment.expected_base_charge,
                    audit_decision=LineAuditDecision.DUPLICATE_LINE,
                )
                inv_lines.append(l1)

                l2 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-02",
                    invoice_id=invoice_id,
                    line_number=2,
                    charge_type=ChargeType.FUEL_SURCHARGE,
                    description="Duplicate Fuel Surcharge Billing",
                    billed_rate=0.18,
                    billed_units=1.0,
                    billed_amount=shipment.expected_fuel_surcharge,
                    expected_amount=0.0,
                    variance_amount=shipment.expected_fuel_surcharge,
                    audit_decision=LineAuditDecision.DUPLICATE_LINE,
                )
                inv_lines.append(l2)

                shipment_accs = acc_by_shipment.get(shipment.shipment_id, [])
                for acc_idx, acc in enumerate(shipment_accs, start=3):
                    inv_lines.append(
                        InvoiceLine(
                            line_id=f"FLINE-{invoice_id}-{acc_idx:02d}",
                            invoice_id=invoice_id,
                            line_number=acc_idx,
                            charge_type=ChargeType.ACCESSORIAL,
                            description=f"Duplicate {acc.description}",
                            billed_rate=acc.standard_fee,
                            billed_units=1.0,
                            billed_amount=acc.standard_fee,
                            expected_amount=0.0,
                            variance_amount=acc.standard_fee,
                            audit_decision=LineAuditDecision.DUPLICATE_LINE,
                        )
                    )

                dup_variance = round(sum(l.billed_amount for l in inv_lines), 2)
                billed_accs = round(sum(l.billed_amount for l in inv_lines if l.charge_type == ChargeType.ACCESSORIAL), 2)

                inv = FreightInvoice(
                    invoice_id=invoice_id,
                    carrier_id=carrier.carrier_id,
                    shipment_id=shipment.shipment_id,
                    invoice_number=f"INV-{carrier.carrier_id[-4:]}-{i:06d}-DUP",
                    invoice_date=inv_date + timedelta(days=20),
                    due_date=due_date + timedelta(days=20),
                    currency="USD",
                    billed_base_charge=shipment.expected_base_charge,
                    billed_fuel_surcharge=shipment.expected_fuel_surcharge,
                    billed_accessorials_charge=billed_accs,
                    billed_total_amount=dup_variance,
                    status=InvoiceStatus.AUDITED_EXCEPTION,
                    audit_status=AuditStatus.DUPLICATE_INVOICE,
                    audit_variance=dup_variance,
                    created_at=datetime.combine(inv_date + timedelta(days=20), datetime.min.time()),
                )
                invoices.append(inv)
                lines.extend(inv_lines)

                ex_counter += 1
                fex_id = f"FEX-2026-{ex_counter:06d}"
                ex = AuditException(
                    exception_id=fex_id,
                    invoice_id=invoice_id,
                    line_id=None,
                    exception_type=ExceptionType.DUPLICATE_INVOICE,
                    severity=ExceptionSeverity.CRITICAL,
                    expected_value=f"Single invoice for shipment {shipment.shipment_id}",
                    billed_value=f"Duplicate invoice: {invoice_id}",
                    discrepancy_amount=dup_variance,
                    status=ExceptionStatus.OPEN,
                    assigned_to="Operations Manager",
                    resolution_notes="Shipment was previously billed on an earlier invoice; duplicate invoice rejected.",
                    created_at=datetime.combine(inv_date + timedelta(days=20), datetime.min.time()),
                )
                exceptions.append(ex)

                self.gt.record_anomaly(
                    target_entity="FreightInvoice",
                    target_id=invoice_id,
                    category=AnomalyCategory.DUPLICATE_INVOICE,
                    expected_decision="AUDITED_EXCEPTION",
                    expected_variance=dup_variance,
                    line_number=None,
                    explanation=f"Duplicate invoice submitted for already billed shipment {shipment.shipment_id}.",
                )
                continue

            # ---------------------------------------------------------
            # Case 7: Invalid / Unauthorized Accessorial
            # ---------------------------------------------------------
            elif is_anomaly and anomaly_mod == 23:
                unauth_fee = 85.00
                inv_lines = []

                l1 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-01",
                    invoice_id=invoice_id,
                    line_number=1,
                    charge_type=ChargeType.BASE_FREIGHT,
                    description="Base Freight Charge",
                    billed_rate=25.00,
                    billed_units=round(shipment.billable_weight_lbs / 100.0, 2),
                    billed_amount=shipment.expected_base_charge,
                    expected_amount=shipment.expected_base_charge,
                    variance_amount=0.0,
                    audit_decision=LineAuditDecision.MATCHED,
                )
                inv_lines.append(l1)

                l2 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-02",
                    invoice_id=invoice_id,
                    line_number=2,
                    charge_type=ChargeType.FUEL_SURCHARGE,
                    description="Fuel Surcharge",
                    billed_rate=0.18,
                    billed_units=1.0,
                    billed_amount=shipment.expected_fuel_surcharge,
                    expected_amount=shipment.expected_fuel_surcharge,
                    variance_amount=0.0,
                    audit_decision=LineAuditDecision.MATCHED,
                )
                inv_lines.append(l2)

                l3 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-03",
                    invoice_id=invoice_id,
                    line_number=3,
                    charge_type=ChargeType.ACCESSORIAL,
                    description="Liftgate Delivery (Unauthorized)",
                    billed_rate=85.00,
                    billed_units=1.0,
                    billed_amount=unauth_fee,
                    expected_amount=0.0,
                    variance_amount=unauth_fee,
                    audit_decision=LineAuditDecision.INVALID_LINE,
                )
                inv_lines.append(l3)

                shipment_accs = acc_by_shipment.get(shipment.shipment_id, [])
                for acc_idx, acc in enumerate(shipment_accs, start=4):
                    inv_lines.append(
                        InvoiceLine(
                            line_id=f"FLINE-{invoice_id}-{acc_idx:02d}",
                            invoice_id=invoice_id,
                            line_number=acc_idx,
                            charge_type=ChargeType.ACCESSORIAL,
                            description=acc.description,
                            billed_rate=acc.standard_fee,
                            billed_units=1.0,
                            billed_amount=acc.standard_fee,
                            expected_amount=acc.standard_fee,
                            variance_amount=0.0,
                            audit_decision=LineAuditDecision.MATCHED,
                        )
                    )

                billed_total = round(sum(l.billed_amount for l in inv_lines), 2)
                billed_accs = round(sum(l.billed_amount for l in inv_lines if l.charge_type == ChargeType.ACCESSORIAL), 2)

                inv = FreightInvoice(
                    invoice_id=invoice_id,
                    carrier_id=carrier.carrier_id,
                    shipment_id=shipment.shipment_id,
                    invoice_number=f"INV-{carrier.carrier_id[-4:]}-{i:06d}",
                    invoice_date=inv_date,
                    due_date=due_date,
                    currency="USD",
                    billed_base_charge=shipment.expected_base_charge,
                    billed_fuel_surcharge=shipment.expected_fuel_surcharge,
                    billed_accessorials_charge=billed_accs,
                    billed_total_amount=billed_total,
                    status=InvoiceStatus.AUDITED_EXCEPTION,
                    audit_status=AuditStatus.DISCREPANCY_DETECTED,
                    audit_variance=unauth_fee,
                    created_at=datetime.combine(inv_date, datetime.min.time()),
                )
                invoices.append(inv)
                lines.extend(inv_lines)

                ex_counter += 1
                fex_id = f"FEX-2026-{ex_counter:06d}"
                ex = AuditException(
                    exception_id=fex_id,
                    invoice_id=invoice_id,
                    line_id=l3.line_id,
                    exception_type=ExceptionType.INVALID_ACCESSORIAL,
                    severity=ExceptionSeverity.MEDIUM,
                    expected_value="$0.00 (No Liftgate authorized on BOL)",
                    billed_value="$85.00",
                    discrepancy_amount=unauth_fee,
                    status=ExceptionStatus.OPEN,
                    assigned_to="Logistics Analyst",
                    resolution_notes="Carrier billed for Liftgate service not requested or authorized on Bill of Lading.",
                    created_at=datetime.combine(inv_date, datetime.min.time()),
                )
                exceptions.append(ex)

                self.gt.record_anomaly(
                    target_entity="FreightInvoice",
                    target_id=invoice_id,
                    category=AnomalyCategory.INVALID_ACCESSORIAL,
                    expected_decision="AUDITED_EXCEPTION",
                    expected_variance=unauth_fee,
                    line_number=3,
                    explanation="Unauthorized accessorial fee billed without supporting BOL documentation.",
                )
                continue

            # ---------------------------------------------------------
            # Clean Baseline: Exactly Matches Contract & Delivery
            # ---------------------------------------------------------
            else:
                inv = FreightInvoice(
                    invoice_id=invoice_id,
                    carrier_id=carrier.carrier_id,
                    shipment_id=shipment.shipment_id,
                    invoice_number=f"INV-{carrier.carrier_id[-4:]}-{i:06d}",
                    invoice_date=inv_date,
                    due_date=due_date,
                    currency="USD",
                    billed_base_charge=shipment.expected_base_charge,
                    billed_fuel_surcharge=shipment.expected_fuel_surcharge,
                    billed_accessorials_charge=shipment.expected_accessorials_charge,
                    billed_total_amount=shipment.expected_total_charge,
                    status=InvoiceStatus.AUDITED_APPROVED,
                    audit_status=AuditStatus.CLEARED,
                    audit_variance=0.0,
                    created_at=datetime.combine(inv_date, datetime.min.time()),
                )
                invoices.append(inv)

                l1 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-01",
                    invoice_id=invoice_id,
                    line_number=1,
                    charge_type=ChargeType.BASE_FREIGHT,
                    description="Base Freight Charge",
                    billed_rate=25.00,
                    billed_units=round(shipment.billable_weight_lbs / 100.0, 2),
                    billed_amount=shipment.expected_base_charge,
                    expected_amount=shipment.expected_base_charge,
                    variance_amount=0.0,
                    audit_decision=LineAuditDecision.MATCHED,
                )
                lines.append(l1)

                l2 = InvoiceLine(
                    line_id=f"FLINE-{invoice_id}-02",
                    invoice_id=invoice_id,
                    line_number=2,
                    charge_type=ChargeType.FUEL_SURCHARGE,
                    description="Contractual Diesel Fuel Surcharge",
                    billed_rate=0.18,
                    billed_units=1.0,
                    billed_amount=shipment.expected_fuel_surcharge,
                    expected_amount=shipment.expected_fuel_surcharge,
                    variance_amount=0.0,
                    audit_decision=LineAuditDecision.MATCHED,
                )
                lines.append(l2)

                # Add authorized accessorial lines if present
                shipment_accs = acc_by_shipment.get(shipment.shipment_id, [])
                for acc_idx, acc in enumerate(shipment_accs, start=3):
                    l_acc = InvoiceLine(
                        line_id=f"FLINE-{invoice_id}-{acc_idx:02d}",
                        invoice_id=invoice_id,
                        line_number=acc_idx,
                        charge_type=ChargeType.ACCESSORIAL,
                        description=acc.description,
                        billed_rate=acc.standard_fee,
                        billed_units=1.0,
                        billed_amount=acc.standard_fee,
                        expected_amount=acc.standard_fee,
                        variance_amount=0.0,
                        audit_decision=LineAuditDecision.MATCHED,
                    )
                    lines.append(l_acc)

                inv_events.append(
                    InvoiceStatusEvent(
                        event_id=f"EVT-{invoice_id}-01",
                        invoice_id=invoice_id,
                        from_status=InvoiceStatus.PENDING_AUDIT,
                        to_status=InvoiceStatus.AUDITED_APPROVED,
                        changed_by="Automated Freight Audit Engine",
                        reason="Invoice matched contracted rates and authorized accessorials with $0.00 variance.",
                        timestamp=datetime.combine(inv_date, datetime.min.time()),
                    )
                )

                self.gt.record_anomaly(
                    target_entity="FreightInvoice",
                    target_id=invoice_id,
                    category=AnomalyCategory.VALID_BASELINE,
                    expected_decision="AUDITED_APPROVED",
                    expected_variance=0.0,
                    line_number=None,
                    explanation="Clean baseline invoice perfectly matching contracted rating and delivery records.",
                )

        return invoices, lines, exceptions, credit_notes, inv_events, res_events
