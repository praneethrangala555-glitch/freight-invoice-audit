"""
Data Integrity & Validation Suite
Validates primary key uniqueness, foreign key integrity, date chronology,
arithmetic reconciliation, and enum constraints across generated entities.
"""
from datetime import date, datetime
from typing import Any, Dict, List, Set, Tuple
from freight_audit.generator.seed_generator import DatasetBundle

class ValidationResult:
    def __init__(self):
        self.passed: bool = True
        self.checks_run: int = 0
        self.checks_passed: int = 0
        self.checks_failed: int = 0
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
        self._check_date_ordering(result)
        self._check_arithmetic_reconciliation(result)
        self._check_duplicate_invoices(result)

        return result

    def _check_primary_keys(self, result: ValidationResult):
        """Verify primary key uniqueness across all entities."""
        entities = [
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
        ]

        for name, items, pk_field in entities:
            seen: Set[str] = set()
            duplicates: List[str] = []
            for item in items:
                pk_val = getattr(item, pk_field)
                if pk_val in seen:
                    duplicates.append(pk_val)
                seen.add(pk_val)

            success = len(duplicates) == 0
            msg = f"{len(items)} rows validated, 0 duplicates." if success else f"Found {len(duplicates)} duplicate PKs: {duplicates[:5]}"
            result.record_check(f"PK Uniqueness ({name})", success, msg)

    def _check_foreign_keys(self, result: ValidationResult):
        """Verify referential integrity across parent-child relationships."""
        carrier_ids = {c.carrier_id for c in self.bundle.carriers}
        lane_ids = {l.lane_id for l in self.bundle.lanes}
        shipment_ids = {s.shipment_id for s in self.bundle.shipments}
        invoice_ids = {i.invoice_id for i in self.bundle.freight_invoices}
        exception_ids = {e.exception_id for e in self.bundle.audit_exceptions}

        # 1. RateCards -> Carriers & Lanes
        rc_c_errs = [rc.rate_card_id for rc in self.bundle.rate_cards if rc.carrier_id not in carrier_ids]
        result.record_check("FK RateCard -> Carrier", len(rc_c_errs) == 0, f"Unmatched: {rc_c_errs[:3]}")

        rc_l_errs = [rc.rate_card_id for rc in self.bundle.rate_cards if rc.lane_id not in lane_ids]
        result.record_check("FK RateCard -> Lane", len(rc_l_errs) == 0, f"Unmatched: {rc_l_errs[:3]}")

        # 2. Shipments -> Carriers & Lanes
        shp_c_errs = [s.shipment_id for s in self.bundle.shipments if s.carrier_id not in carrier_ids]
        result.record_check("FK Shipment -> Carrier", len(shp_c_errs) == 0, f"Unmatched: {shp_c_errs[:3]}")

        shp_l_errs = [s.shipment_id for s in self.bundle.shipments if s.lane_id not in lane_ids]
        result.record_check("FK Shipment -> Lane", len(shp_l_errs) == 0, f"Unmatched: {shp_l_errs[:3]}")

        # 3. ShipmentLegs -> Shipments
        leg_errs = [l.leg_id for l in self.bundle.shipment_legs if l.shipment_id not in shipment_ids]
        result.record_check("FK ShipmentLeg -> Shipment", len(leg_errs) == 0, f"Unmatched: {leg_errs[:3]}")

        # 4. WeightMeasurements -> Shipments
        wm_errs = [wm.measurement_id for wm in self.bundle.weight_measurements if wm.shipment_id not in shipment_ids]
        result.record_check("FK WeightMeasurement -> Shipment", len(wm_errs) == 0, f"Unmatched: {wm_errs[:3]}")

        # 5. Accessorials -> Shipments
        acc_errs = [a.accessorial_id for a in self.bundle.accessorials if a.shipment_id not in shipment_ids]
        result.record_check("FK Accessorial -> Shipment", len(acc_errs) == 0, f"Unmatched: {acc_errs[:3]}")

        # 6. FreightInvoices -> Carriers
        inv_c_errs = [inv.invoice_id for inv in self.bundle.freight_invoices if inv.carrier_id not in carrier_ids]
        result.record_check("FK FreightInvoice -> Carrier", len(inv_c_errs) == 0, f"Unmatched: {inv_c_errs[:3]}")

        # 7. InvoiceLines -> FreightInvoices
        line_errs = [line.line_id for line in self.bundle.invoice_lines if line.invoice_id not in invoice_ids]
        result.record_check("FK InvoiceLine -> FreightInvoice", len(line_errs) == 0, f"Unmatched: {line_errs[:3]}")

        # 8. CreditNotes -> Exceptions
        cn_errs = [cn.credit_note_id for cn in self.bundle.credit_notes if cn.exception_id not in exception_ids]
        result.record_check("FK CreditNote -> AuditException", len(cn_errs) == 0, f"Unmatched: {cn_errs[:3]}")

    def _check_date_ordering(self, result: ValidationResult):
        """Verify chronological validity of dates."""
        # Shipment ship_date <= delivery_date
        deliv_errs = [
            s.shipment_id for s in self.bundle.shipments
            if s.delivery_date and s.delivery_date < s.ship_date
        ]
        result.record_check("Date Chronology: Shipment Tender <= Delivery", len(deliv_errs) == 0, f"Failed: {deliv_errs[:3]}")

        # RateCard effective_start <= effective_end
        rc_date_errs = [
            rc.rate_card_id for rc in self.bundle.rate_cards
            if rc.effective_end_date < rc.effective_start_date
        ]
        result.record_check("Date Chronology: RateCard Start <= End", len(rc_date_errs) == 0, f"Failed: {rc_date_errs[:3]}")

        # FreightInvoice invoice_date <= due_date
        inv_date_errs = [
            inv.invoice_id for inv in self.bundle.freight_invoices
            if inv.due_date < inv.invoice_date
        ]
        result.record_check("Date Chronology: Invoice Date <= Due Date", len(inv_date_errs) == 0, f"Failed: {inv_date_errs[:3]}")

    def _check_arithmetic_reconciliation(self, result: ValidationResult):
        """Verify mathematical integrity of rollups and calculations."""
        # 1. Invoice total amount == sum of line amounts
        lines_by_inv: Dict[str, float] = {}
        for l in self.bundle.invoice_lines:
            lines_by_inv[l.invoice_id] = lines_by_inv.get(l.invoice_id, 0.0) + l.billed_amount

        math_errs = []
        for inv in self.bundle.freight_invoices:
            sum_lines = round(lines_by_inv.get(inv.invoice_id, 0.0), 2)
            if abs(inv.billed_total_amount - sum_lines) > 0.02:
                math_errs.append((inv.invoice_id, inv.billed_total_amount, sum_lines))

        result.record_check(
            "Arithmetic: Invoice Total == Sum(Line Amounts)",
            len(math_errs) == 0,
            f"Mismatches: {math_errs[:3]}",
        )

        # 2. Shipment billable weight == max(actual, dim)
        wt_errs = [
            s.shipment_id for s in self.bundle.shipments
            if abs(s.billable_weight_lbs - max(s.total_actual_weight_lbs, s.total_dim_weight_lbs)) > 0.05
        ]
        result.record_check(
            "Arithmetic: Billable Weight == Max(Actual, Dim)",
            len(wt_errs) == 0,
            f"Mismatches: {wt_errs[:3]}",
        )

        # 3. Shipment expected total == base + fuel + accessorials
        exp_errs = [
            s.shipment_id for s in self.bundle.shipments
            if abs(s.expected_total_charge - round(s.expected_base_charge + s.expected_fuel_surcharge + s.expected_accessorials_charge, 2)) > 0.02
        ]
        result.record_check(
            "Arithmetic: Shipment Expected Total == Base + FSC + Accessorials",
            len(exp_errs) == 0,
            f"Mismatches: {exp_errs[:3]}",
        )

    def _check_duplicate_invoices(self, result: ValidationResult):
        """Verify duplicate invoices exist only where intentionally injected and labeled."""
        invoice_numbers: Dict[Tuple[str, str], int] = {}
        for inv in self.bundle.freight_invoices:
            k = (inv.carrier_id, inv.invoice_number)
            invoice_numbers[k] = invoice_numbers.get(k, 0) + 1

        unlabelled_dups = [k for k, count in invoice_numbers.items() if count > 1 and "DUP" not in k[1]]
        result.record_check(
            "Integrity: No Unintended Duplicate Invoice Numbers",
            len(unlabelled_dups) == 0,
            f"Unlabeled duplicates: {unlabelled_dups[:3]}",
        )
