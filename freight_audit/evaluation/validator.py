"""Relational, lifecycle, and financial validation for generated audit data."""

from collections import Counter, defaultdict
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Set

from freight_audit.engine.rating import RatingEngine, calculate_dim_weight
from freight_audit.generator.anomalies import AnomalyCategory
from freight_audit.generator.seed_generator import DatasetBundle
from freight_audit.models.enums import (
    ExceptionType,
    ExceptionStatus,
    InvoiceStatus,
    RateCardStatus,
    ShipmentStatus,
)


class ValidationResult:
    def __init__(self):
        self.passed = True
        self.checks_run = 0
        self.checks_passed = 0
        self.checks_failed = 0
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.details: Dict[str, Any] = {}

    def record_check(self, name: str, success: bool, message: str = ""):
        self.checks_run += 1
        if success:
            self.checks_passed += 1
        else:
            self.checks_failed += 1
            self.passed = False
            self.errors.append(f"[{name}] {message}")


class RelationalValidator:
    def __init__(self, bundle: DatasetBundle):
        self.bundle = bundle

    def validate_all(self) -> ValidationResult:
        result = ValidationResult()
        self._check_primary_keys(result)
        self._check_foreign_keys(result)
        self._check_cardinality(result)
        self._check_enum_values(result)
        self._check_enums_and_lifecycles(result)
        self._check_date_ordering(result)
        self._check_arithmetic_reconciliation(result)
        self._check_anomaly_ground_truth(result)
        return result

    def _all_entities(self):
        return [
            ("carriers", self.bundle.carriers, "carrier_id"),
            ("lanes", self.bundle.lanes, "lane_id"),
            ("rate_cards", self.bundle.rate_cards, "rate_card_id"),
            ("shipments", self.bundle.shipments, "shipment_id"),
            ("shipment_legs", self.bundle.shipment_legs, "leg_id"),
            ("weight_measurements", self.bundle.weight_measurements, "measurement_id"),
            ("accessorials", self.bundle.accessorials, "accessorial_id"),
            ("freight_invoices", self.bundle.freight_invoices, "invoice_id"),
            ("invoice_lines", self.bundle.invoice_lines, "line_id"),
            ("audit_exceptions", self.bundle.audit_exceptions, "exception_id"),
            ("credit_notes", self.bundle.credit_notes, "credit_note_id"),
            ("invoice_status_events", self.bundle.invoice_status_events, "event_id"),
            ("audit_resolution_events", self.bundle.audit_resolution_events, "event_id"),
        ]

    def _check_primary_keys(self, result: ValidationResult):
        for name, items, pk_field in self._all_entities():
            values = [getattr(item, pk_field) for item in items]
            duplicates = [value for value, count in Counter(values).items() if count > 1]
            result.record_check(
                f"PK uniqueness ({name})",
                not duplicates,
                f"Duplicate IDs: {duplicates[:5]}",
            )

    def _check_foreign_keys(self, result: ValidationResult):
        carriers = {item.carrier_id for item in self.bundle.carriers}
        lanes = {item.lane_id for item in self.bundle.lanes}
        rate_cards = {item.rate_card_id: item for item in self.bundle.rate_cards}
        shipments = {item.shipment_id: item for item in self.bundle.shipments}
        invoices = {item.invoice_id: item for item in self.bundle.freight_invoices}
        lines = {item.line_id for item in self.bundle.invoice_lines}
        accessorials = {item.accessorial_id: item for item in self.bundle.accessorials}
        exceptions = {item.exception_id: item for item in self.bundle.audit_exceptions}
        truth_by_target = {
            (record.target_entity, record.target_id): record
            for record in self.bundle.ground_truth.records
        }

        relations = [
            ("RateCard -> Carrier", [x.rate_card_id for x in self.bundle.rate_cards if x.carrier_id not in carriers]),
            ("RateCard -> Lane", [x.rate_card_id for x in self.bundle.rate_cards if x.lane_id not in lanes]),
            ("Shipment -> Carrier", [x.shipment_id for x in self.bundle.shipments if x.carrier_id not in carriers]),
            ("Shipment -> Lane", [x.shipment_id for x in self.bundle.shipments if x.lane_id not in lanes]),
            ("Shipment -> RateCard", [
                x.shipment_id for x in self.bundle.shipments
                if x.rate_card_id is None or x.rate_card_id not in rate_cards
            ]),
            ("ShipmentLeg -> Shipment", [x.leg_id for x in self.bundle.shipment_legs if x.shipment_id not in shipments]),
            ("WeightMeasurement -> Shipment", [
                x.measurement_id for x in self.bundle.weight_measurements if x.shipment_id not in shipments
            ]),
            ("Accessorial -> Shipment", [
                x.accessorial_id for x in self.bundle.accessorials if x.shipment_id not in shipments
            ]),
            ("FreightInvoice -> Carrier", [
                x.invoice_id for x in self.bundle.freight_invoices if x.carrier_id not in carriers
            ]),
            ("FreightInvoice -> Shipment", [
                x.invoice_id for x in self.bundle.freight_invoices
                if x.shipment_id is not None and x.shipment_id not in shipments
            ]),
            ("FreightInvoice -> RateCard", [
                x.invoice_id for x in self.bundle.freight_invoices
                if x.rate_card_id is not None and x.rate_card_id not in rate_cards
            ]),
            ("InvoiceLine -> FreightInvoice", [
                x.line_id for x in self.bundle.invoice_lines if x.invoice_id not in invoices
            ]),
            ("InvoiceLine -> Accessorial", [
                x.line_id for x in self.bundle.invoice_lines
                if x.accessorial_id is not None and x.accessorial_id not in accessorials
            ]),
            ("AuditException -> FreightInvoice", [
                x.exception_id for x in self.bundle.audit_exceptions if x.invoice_id not in invoices
            ]),
            ("AuditException -> InvoiceLine", [
                x.exception_id for x in self.bundle.audit_exceptions
                if x.line_id is not None and x.line_id not in lines
            ]),
            ("CreditNote -> Carrier/Invoice/Exception", [
                x.credit_note_id for x in self.bundle.credit_notes
                if x.carrier_id not in carriers
                or x.invoice_id not in invoices
                or x.exception_id not in exceptions
            ]),
            ("InvoiceStatusEvent -> FreightInvoice", [
                x.event_id for x in self.bundle.invoice_status_events if x.invoice_id not in invoices
            ]),
            ("AuditResolutionEvent -> AuditException", [
                x.event_id for x in self.bundle.audit_resolution_events if x.exception_id not in exceptions
            ]),
        ]
        for name, errors in relations:
            result.record_check(f"FK {name}", not errors, f"Unmatched rows: {errors[:5]}")

        invalid_accessorial_joins = [
            line.line_id for line in self.bundle.invoice_lines
            if line.accessorial_id is not None
            and (
                line.accessorial_id not in accessorials
                or line.invoice_id not in invoices
                or line.accessorial_id in accessorials
                and line.invoice_id in invoices
                and invoices[line.invoice_id].shipment_id != accessorials[line.accessorial_id].shipment_id
            )
        ]
        result.record_check(
            "InvoiceLine accessorial belongs to billed shipment",
            not invalid_accessorial_joins,
            f"Mismatched joins: {invalid_accessorial_joins[:5]}",
        )

        unknown_shipment_errors = []
        for invoice in self.bundle.freight_invoices:
            gt = truth_by_target.get(("FreightInvoice", invoice.invoice_id))
            if gt and gt.anomaly_category == AnomalyCategory.UNKNOWN_SHIPMENT.value:
                if invoice.shipment_id is not None or not invoice.shipment_reference:
                    unknown_shipment_errors.append(invoice.invoice_id)
                elif invoice.shipment_reference in shipments:
                    unknown_shipment_errors.append(invoice.invoice_id)
            elif invoice.shipment_id is None and invoice.shipment_reference:
                unknown_shipment_errors.append(invoice.invoice_id)
            elif invoice.shipment_id and invoice.shipment_reference not in (None, invoice.shipment_id):
                unknown_shipment_errors.append(invoice.invoice_id)
        result.record_check(
            "Intentional unknown shipment references are ground-truth labelled",
            not unknown_shipment_errors,
            f"Unexpected/malformed references: {unknown_shipment_errors[:5]}",
        )

        mismatch_errors = []
        for shipment in self.bundle.shipments:
            card = rate_cards.get(shipment.rate_card_id or "")
            if card and (
                card.carrier_id != shipment.carrier_id
                or card.lane_id != shipment.lane_id
                or card.service_level != shipment.service_level
            ):
                mismatch_errors.append(shipment.shipment_id)
        result.record_check(
            "Shipment uses matching carrier/lane/service rate card",
            not mismatch_errors,
            f"Mismatched rate cards: {mismatch_errors[:5]}",
        )

        credit_mismatch = [
            credit.credit_note_id for credit in self.bundle.credit_notes
            if credit.exception_id not in exceptions
            or credit.invoice_id != exceptions[credit.exception_id].invoice_id
            or exceptions[credit.exception_id].status != ExceptionStatus.APPROVED_DISPUTE
        ]
        result.record_check(
            "CreditNote -> originating invoice",
            not credit_mismatch,
            f"Invoice/exception mismatch: {credit_mismatch[:5]}",
        )

    def _check_cardinality(self, result: ValidationResult):
        line_numbers = Counter((x.invoice_id, x.line_number) for x in self.bundle.invoice_lines)
        duplicate_lines = [key for key, count in line_numbers.items() if count > 1]
        result.record_check(
            "InvoiceLine line numbers unique per invoice",
            not duplicate_lines,
            f"Duplicates: {duplicate_lines[:5]}",
        )

        leg_sequences = Counter((x.shipment_id, x.leg_sequence) for x in self.bundle.shipment_legs)
        duplicate_legs = [key for key, count in leg_sequences.items() if count > 1]
        result.record_check(
            "ShipmentLeg sequences unique per shipment",
            not duplicate_legs,
            f"Duplicates: {duplicate_legs[:5]}",
        )

        piece_numbers = Counter((x.shipment_id, x.piece_number) for x in self.bundle.weight_measurements)
        duplicate_pieces = [key for key, count in piece_numbers.items() if count > 1]
        result.record_check(
            "WeightMeasurement piece numbers unique per shipment",
            not duplicate_pieces,
            f"Duplicates: {duplicate_pieces[:5]}",
        )
        carrier_scacs = Counter(item.scac for item in self.bundle.carriers)
        duplicate_scacs = [value for value, count in carrier_scacs.items() if count > 1]
        bol_numbers = Counter(item.bol_number for item in self.bundle.shipments)
        duplicate_bols = [value for value, count in bol_numbers.items() if count > 1]
        credit_numbers = Counter(item.credit_note_number for item in self.bundle.credit_notes)
        duplicate_credit_numbers = [value for value, count in credit_numbers.items() if count > 1]
        result.record_check(
            "Carrier SCAC uniqueness",
            not duplicate_scacs,
            f"Duplicates: {duplicate_scacs[:5]}",
        )
        result.record_check(
            "Shipment BOL uniqueness",
            not duplicate_bols,
            f"Duplicates: {duplicate_bols[:5]}",
        )
        result.record_check(
            "Credit note number uniqueness",
            not duplicate_credit_numbers,
            f"Duplicates: {duplicate_credit_numbers[:5]}",
        )

    def _check_enums_and_lifecycles(self, result: ValidationResult):
        valid_baseline = {record.target_id for record in self.bundle.ground_truth.records
                          if record.target_entity == "FreightInvoice"
                          and record.anomaly_category == AnomalyCategory.VALID_BASELINE.value}
        invoice_events: Dict[str, list] = defaultdict(list)
        for event in self.bundle.invoice_status_events:
            invoice_events[event.invoice_id].append(event)
        missing_invoice_events = [
            invoice.invoice_id for invoice in self.bundle.freight_invoices
            if not invoice_events[invoice.invoice_id]
        ]
        event_state_mismatches = [
            invoice.invoice_id for invoice in self.bundle.freight_invoices
            if invoice_events[invoice.invoice_id]
            and invoice_events[invoice.invoice_id][-1].to_status != invoice.status
        ]
        invalid_invoice_transitions = [
            event.event_id for event in self.bundle.invoice_status_events
            if not self._invoice_transition_allowed(event.from_status, event.to_status)
        ]
        result.record_check(
            "Invoice lifecycle events and final state",
            not (missing_invoice_events or event_state_mismatches or invalid_invoice_transitions),
            f"Missing={missing_invoice_events[:3]}, state mismatch={event_state_mismatches[:3]}, "
            f"invalid transitions={invalid_invoice_transitions[:3]}",
        )

        resolution_events = {event.exception_id: event for event in self.bundle.audit_resolution_events}
        missing_resolution = [
            item.exception_id for item in self.bundle.audit_exceptions
            if item.status != ExceptionStatus.OPEN and item.exception_id not in resolution_events
        ]
        mismatched_resolution = [
            item.exception_id for item in self.bundle.audit_exceptions
            if item.exception_id in resolution_events
            and resolution_events[item.exception_id].to_status != item.status
        ]
        result.record_check(
            "Exception lifecycle events match state",
            not (missing_resolution or mismatched_resolution),
            f"Missing={missing_resolution[:3]}, state mismatch={mismatched_resolution[:3]}",
        )

        invalid_baseline = [
            invoice.invoice_id for invoice in self.bundle.freight_invoices
            if invoice.invoice_id in valid_baseline
            and (invoice.status != InvoiceStatus.AUDITED_APPROVED or abs(invoice.audit_variance) > 0.02)
        ]
        result.record_check(
            "Ground-truth baseline decisions",
            not invalid_baseline,
            f"Invalid clean-baseline decisions: {invalid_baseline[:5]}",
        )

    def _check_enum_values(self, result: ValidationResult):
        fields = [
            (self.bundle.carriers, ("mode", "status")),
            (self.bundle.rate_cards, ("service_level", "status")),
            (self.bundle.shipments, ("service_level", "status")),
            (self.bundle.shipment_legs, ("leg_status",)),
            (self.bundle.weight_measurements, ("measurement_type",)),
            (self.bundle.accessorials, ("code",)),
            (self.bundle.freight_invoices, ("status", "audit_status")),
            (self.bundle.invoice_lines, ("charge_type", "audit_decision")),
            (self.bundle.audit_exceptions, ("exception_type", "severity", "status")),
            (self.bundle.credit_notes, ("status", "reconciliation_status")),
            (self.bundle.invoice_status_events, ("from_status", "to_status")),
            (self.bundle.audit_resolution_events, ("from_status", "to_status")),
        ]
        invalid = []
        for entities, names in fields:
            for entity in entities:
                for name in names:
                    value = getattr(entity, name)
                    if not isinstance(value, Enum) or value.value not in {
                        item.value for item in type(value)
                    }:
                        invalid.append(f"{type(entity).__name__}.{name}")
        result.record_check(
            "Allowed enum values",
            not invalid,
            f"Invalid enum fields: {invalid[:5]}",
        )

    @staticmethod
    def _invoice_transition_allowed(source: InvoiceStatus, target: InvoiceStatus) -> bool:
        transitions = {
            InvoiceStatus.PENDING_AUDIT: {
                InvoiceStatus.AUDITED_APPROVED, InvoiceStatus.AUDITED_EXCEPTION
            },
            InvoiceStatus.AUDITED_EXCEPTION: {
                InvoiceStatus.DISPUTED, InvoiceStatus.AUDITED_APPROVED,
                InvoiceStatus.REJECTED, InvoiceStatus.PAID,
            },
            InvoiceStatus.DISPUTED: {InvoiceStatus.PAID, InvoiceStatus.REJECTED},
            InvoiceStatus.AUDITED_APPROVED: {InvoiceStatus.PAID},
        }
        return target in transitions.get(source, set())

    def _check_date_ordering(self, result: ValidationResult):
        shipment_by_id = {item.shipment_id: item for item in self.bundle.shipments}
        bad_shipments = [
            item.shipment_id for item in self.bundle.shipments
            if item.delivery_date and item.delivery_date < item.ship_date
            or item.status == ShipmentStatus.DELIVERED and item.delivery_date is None
        ]
        bad_legs = [
            item.leg_id for item in self.bundle.shipment_legs
            if item.delivery_time and item.delivery_time < item.pickup_time
        ]
        bad_rates = [
            item.rate_card_id for item in self.bundle.rate_cards
            if item.effective_end_date < item.effective_start_date
        ]
        bad_invoices = [
            item.invoice_id for item in self.bundle.freight_invoices
            if item.due_date < item.invoice_date
            or item.shipment_id in shipment_by_id
            and shipment_by_id[item.shipment_id].delivery_date
            and item.invoice_date < shipment_by_id[item.shipment_id].delivery_date
        ]
        bad_credits = [
            item.credit_note_id for item in self.bundle.credit_notes
            if item.exception_id in {e.exception_id for e in self.bundle.audit_exceptions}
            and item.issue_date < next(
                e.created_at.date() for e in self.bundle.audit_exceptions
                if e.exception_id == item.exception_id
            )
        ]
        for name, errors in [
            ("Shipment and delivery chronology", bad_shipments),
            ("ShipmentLeg chronology", bad_legs),
            ("RateCard effective dates/status", bad_rates),
            ("Invoice/delivery/due-date chronology", bad_invoices),
            ("CreditNote issuance chronology", bad_credits),
        ]:
            result.record_check(name, not errors, f"Invalid rows: {errors[:5]}")

    def _check_arithmetic_reconciliation(self, result: ValidationResult):
        lines_by_invoice: Dict[str, list] = defaultdict(list)
        for line in self.bundle.invoice_lines:
            lines_by_invoice[line.invoice_id].append(line)

        total_errors = []
        component_errors = []
        variance_errors = []
        for invoice in self.bundle.freight_invoices:
            lines = lines_by_invoice[invoice.invoice_id]
            billed_sum = round(sum(item.billed_amount for item in lines), 2)
            if abs(invoice.billed_total_amount - billed_sum) > 0.02:
                total_errors.append(invoice.invoice_id)
            for charge_type, field in [
                ("BASE_FREIGHT", invoice.billed_base_charge),
                ("FUEL_SURCHARGE", invoice.billed_fuel_surcharge),
                ("ACCESSORIAL", invoice.billed_accessorials_charge),
            ]:
                amount = round(sum(x.billed_amount for x in lines if x.charge_type.value == charge_type), 2)
                if abs(amount - field) > 0.02:
                    component_errors.append(invoice.invoice_id)
                    break
            line_variance = round(sum(x.billed_amount - x.expected_amount for x in lines), 2)
            if abs(invoice.audit_variance - line_variance) > 0.02:
                variance_errors.append(invoice.invoice_id)

        result.record_check(
            "Invoice total equals line sum",
            not total_errors,
            f"Mismatches: {total_errors[:5]}",
        )
        result.record_check(
            "Invoice charge components equal line rollups",
            not component_errors,
            f"Mismatches: {component_errors[:5]}",
        )
        result.record_check(
            "Invoice variance equals line variances",
            not variance_errors,
            f"Mismatches: {variance_errors[:5]}",
        )

        measurement_by_shipment: Dict[str, list] = defaultdict(list)
        for item in self.bundle.weight_measurements:
            measurement_by_shipment[item.shipment_id].append(item)
        accessorial_by_shipment: Dict[str, list] = defaultdict(list)
        for item in self.bundle.accessorials:
            accessorial_by_shipment[item.shipment_id].append(item)
        rate_cards = {item.rate_card_id: item for item in self.bundle.rate_cards}
        weight_errors = []
        expected_errors = []
        for shipment in self.bundle.shipments:
            measurements = measurement_by_shipment[shipment.shipment_id]
            actual = round(sum(x.scale_weight_lbs for x in measurements), 2)
            dim = round(sum(x.dim_weight_lbs for x in measurements), 2)
            if (
                len(measurements) != shipment.total_pieces
                or abs(actual - shipment.total_actual_weight_lbs) > 0.05
                or abs(dim - shipment.total_dim_weight_lbs) > 0.05
                or abs(shipment.billable_weight_lbs - max(actual, dim)) > 0.05
            ):
                weight_errors.append(shipment.shipment_id)
            card = rate_cards.get(shipment.rate_card_id or "")
            if card:
                dimension_errors = [
                    item.measurement_id for item in measurements
                    if abs(
                        item.dim_weight_lbs
                        - calculate_dim_weight(item.length_in, item.width_in, item.height_in, card.dim_factor)
                    ) > 0.02
                ]
                if dimension_errors:
                    weight_errors.extend(dimension_errors[:3])
                breakdown = RatingEngine([card]).calculate_expected_charges(
                    card,
                    shipment.total_actual_weight_lbs,
                    shipment.total_dim_weight_lbs,
                    accessorial_by_shipment[shipment.shipment_id],
                )
                if (
                    abs(shipment.expected_base_charge - breakdown.base_charge) > 0.02
                    or abs(shipment.expected_fuel_surcharge - breakdown.fuel_surcharge_amount) > 0.02
                    or abs(shipment.expected_accessorials_charge - breakdown.accessorials_amount) > 0.02
                    or abs(shipment.expected_total_charge - breakdown.total_expected_charge) > 0.02
                ):
                    expected_errors.append(shipment.shipment_id)
        result.record_check(
            "Shipment measurements and billable weight reconcile",
            not weight_errors,
            f"Mismatches: {weight_errors[:5]}",
        )
        result.record_check(
            "Shipment expected charges reproduce from contract",
            not expected_errors,
            f"Mismatches: {expected_errors[:5]}",
        )

        exceptions = {item.exception_id: item for item in self.bundle.audit_exceptions}
        approved_amounts = {
            event.exception_id: event.approved_amount
            for event in self.bundle.audit_resolution_events
            if event.to_status == ExceptionStatus.APPROVED_DISPUTE
        }
        credit_errors = []
        for credit in self.bundle.credit_notes:
            exception = exceptions.get(credit.exception_id)
            if exception is None:
                continue
            approved_amount = approved_amounts.get(
                credit.exception_id, exception.discrepancy_amount
            )
            difference = round(credit.credit_amount - approved_amount, 2)
            expected_status = (
                "RECONCILED" if abs(difference) < 0.01
                else "OVERCREDITED" if difference > 0
                else "UNDERCREDITED"
            )
            if (
                abs(credit.original_exception_amount - approved_amount) > 0.02
                or credit.reconciliation_status.value != expected_status
            ):
                credit_errors.append(credit.credit_note_id)
        result.record_check(
            "Credit notes reconcile to approved exception amounts",
            not credit_errors,
            f"Mismatches: {credit_errors[:5]}",
        )

    def _check_anomaly_ground_truth(self, result: ValidationResult):
        truth_by_target = {
            (record.target_entity, record.target_id): record
            for record in self.bundle.ground_truth.records
        }
        invoices = {item.invoice_id: item for item in self.bundle.freight_invoices}
        lines = {item.line_id: item for item in self.bundle.invoice_lines}
        base_line_by_invoice = {
            item.invoice_id: item for item in self.bundle.invoice_lines
            if item.charge_type.value == "BASE_FREIGHT"
        }
        rate_cards = {item.rate_card_id: item for item in self.bundle.rate_cards}
        shipments = {item.shipment_id: item for item in self.bundle.shipments}
        exceptions = {item.exception_id: item for item in self.bundle.audit_exceptions}
        credit_notes = {item.credit_note_id: item for item in self.bundle.credit_notes}

        missing_labels = [
            invoice.invoice_id for invoice in self.bundle.freight_invoices
            if ("FreightInvoice", invoice.invoice_id) not in truth_by_target
        ]
        orphan_labels = [
            key for key in truth_by_target
            if key[0] == "FreightInvoice" and key[1] not in invoices
            or key[0] == "CreditNote" and key[1] not in credit_notes
        ]
        result.record_check(
            "Ground-truth labels cover invoices and resolve to source rows",
            not missing_labels and not orphan_labels,
            f"Missing={missing_labels[:5]}, orphan={orphan_labels[:5]}",
        )

        anomaly_errors = []
        duplicate_pairs = Counter(
            (item.carrier_id, item.shipment_id) for item in self.bundle.freight_invoices
            if item.shipment_id is not None
        )
        for invoice in self.bundle.freight_invoices:
            gt = truth_by_target.get(("FreightInvoice", invoice.invoice_id))
            if not gt:
                continue
            if gt.expected_decision == "AUDITED_EXCEPTION":
                if invoice.status != InvoiceStatus.AUDITED_EXCEPTION:
                    anomaly_errors.append(invoice.invoice_id)
                if abs(invoice.audit_variance - gt.expected_variance) > 0.02:
                    anomaly_errors.append(invoice.invoice_id)
            elif gt.expected_decision == "AUDITED_APPROVED" and (
                invoice.status != InvoiceStatus.AUDITED_APPROVED or abs(invoice.audit_variance) > 0.02
            ):
                anomaly_errors.append(invoice.invoice_id)

            if gt.anomaly_category == AnomalyCategory.RATE_CARD_EXPIRED.value:
                card = rate_cards.get(invoice.rate_card_id or "")
                shipment = shipments.get(invoice.shipment_id or "")
                if (
                    not card
                    or not shipment
                    or card.status != RateCardStatus.EXPIRED
                    or card.effective_end_date >= shipment.ship_date
                ):
                    anomaly_errors.append(invoice.invoice_id)
            elif gt.anomaly_category == AnomalyCategory.WEIGHT_TIER_MISAPPLIED.value:
                shipment = shipments.get(invoice.shipment_id or "")
                card = rate_cards.get(shipment.rate_card_id or "") if shipment else None
                target_line = base_line_by_invoice.get(invoice.invoice_id)
                if (
                    not shipment
                    or not target_line
                    or shipment.billable_weight_lbs < 2000
                    or shipment.billable_weight_lbs >= 5000
                    or not card
                    or abs(
                        target_line.billed_rate
                        - card.rate_tier_1_cwt
                    ) > 0.02
                ):
                    anomaly_errors.append(invoice.invoice_id)
            elif gt.anomaly_category == AnomalyCategory.DUPLICATE_INVOICE.value:
                if duplicate_pairs[(invoice.carrier_id, invoice.shipment_id)] < 2:
                    anomaly_errors.append(invoice.invoice_id)

            expected_exception_type = {
                AnomalyCategory.UNKNOWN_SHIPMENT.value: ExceptionType.UNKNOWN_SHIPMENT,
                AnomalyCategory.RATE_CARD_EXPIRED.value: ExceptionType.RATE_CARD_EXPIRED,
                AnomalyCategory.WEIGHT_TIER_MISAPPLIED.value: ExceptionType.WEIGHT_TIER_MISAPPLIED,
                AnomalyCategory.SURCHARGE_DUPLICATED.value: ExceptionType.SURCHARGE_DUPLICATED,
                AnomalyCategory.INVALID_ACCESSORIAL.value: ExceptionType.INVALID_ACCESSORIAL,
                AnomalyCategory.DUPLICATE_INVOICE.value: ExceptionType.DUPLICATE_INVOICE,
            }.get(gt.anomaly_category)
            if expected_exception_type and not any(
                item.invoice_id == invoice.invoice_id and item.exception_type == expected_exception_type
                for item in self.bundle.audit_exceptions
            ):
                anomaly_errors.append(invoice.invoice_id)

        credit_errors = []
        for credit in self.bundle.credit_notes:
            gt = truth_by_target.get(("CreditNote", credit.credit_note_id))
            if not gt:
                credit_errors.append(credit.credit_note_id)
                continue
            difference = round(credit.credit_amount - credit.original_exception_amount, 2)
            if gt.expected_decision == "OVERCREDITED" and credit.reconciliation_status.value != "OVERCREDITED":
                credit_errors.append(credit.credit_note_id)
            if gt.expected_decision == "RECONCILED" and credit.reconciliation_status.value != "RECONCILED":
                credit_errors.append(credit.credit_note_id)
            if abs(credit.credit_amount - credit.original_exception_amount - gt.expected_variance) > 0.02:
                credit_errors.append(credit.credit_note_id)
            has_overcredit_exception = any(
                item.invoice_id == credit.invoice_id
                and item.exception_type == ExceptionType.CREDIT_NOTE_EXCEEDS_EXCEPTION
                and abs(item.discrepancy_amount - max(0.0, difference)) < 0.02
                for item in self.bundle.audit_exceptions
            )
            if gt.expected_decision == "OVERCREDITED" and not has_overcredit_exception:
                credit_errors.append(credit.credit_note_id)

        result.record_check(
            "Injected anomaly cases match documented ground truth",
            not anomaly_errors,
            f"Incorrect invoice outcomes: {anomaly_errors[:5]}",
        )
        result.record_check(
            "Credit ground truth matches reconciliation outcomes",
            not credit_errors,
            f"Incorrect credit outcomes: {credit_errors[:5]}",
        )
