"""
Freight Invoice Audit Pipeline
Executes multi-stage validation rules against invoices, shipment records,
rate cards, and delivery documentation. Generates line-level explanations
and explicit AuditException records.
"""
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from freight_audit.engine.rating import RatingEngine, determine_weight_tier
from freight_audit.models.entities import (
    FreightInvoice,
    InvoiceLine,
    Shipment,
    RateCard,
    Accessorial,
    AuditException,
    InvoiceStatusEvent,
)
from freight_audit.models.enums import (
    InvoiceStatus,
    AuditStatus,
    ChargeType,
    LineAuditDecision,
    ExceptionType,
    ExceptionSeverity,
    ExceptionStatus,
)

class FreightAuditor:
    def __init__(
        self,
        rating_engine: RatingEngine,
        shipments: Optional[Dict[str, Shipment]] = None,
        shipment_accessorials: Optional[Dict[str, List[Accessorial]]] = None,
        rate_cards_by_id: Optional[Dict[str, RateCard]] = None,
    ):
        self.rating_engine = rating_engine
        self.shipments = shipments or {}
        self.shipment_accessorials = shipment_accessorials or {}
        self.rate_cards_by_id = rate_cards_by_id or {}
        # Duplicate detection index: (carrier_id, shipment_id) -> invoice_id
        self.billed_shipments: Dict[Tuple[str, str], str] = {}
        # Invoice number index: (carrier_id, invoice_number) -> invoice_id
        self.billed_invoices: Dict[Tuple[str, str], str] = {}
        self.exception_counter = 0

    def next_exception_id(self) -> str:
        self.exception_counter += 1
        return f"FEX-2026-{self.exception_counter:06d}"

    def audit_invoice(
        self, invoice: FreightInvoice, lines: List[InvoiceLine]
    ) -> Tuple[FreightInvoice, List[InvoiceLine], List[AuditException], List[InvoiceStatusEvent]]:
        """
        Run end-to-end multi-stage audit rules for a freight invoice and its line items.
        """
        exceptions: List[AuditException] = []
        events: List[InvoiceStatusEvent] = []
        initial_status = invoice.status

        # -------------------------------------------------------------
        # Stage 1: Shipment Existence & Parent Integrity Check
        # -------------------------------------------------------------
        if not invoice.shipment_id or invoice.shipment_id not in self.shipments:
            ex = AuditException(
                exception_id=self.next_exception_id(),
                invoice_id=invoice.invoice_id,
                line_id=None,
                exception_type=ExceptionType.UNKNOWN_SHIPMENT,
                severity=ExceptionSeverity.CRITICAL,
                expected_value="Valid active shipment ID from TMS/ERP",
                billed_value=str(invoice.shipment_id),
                discrepancy_amount=invoice.billed_total_amount,
                status=ExceptionStatus.OPEN,
                assigned_to="Logistics Analyst",
                resolution_notes="Invoice references unknown or nonexistent shipment ID; potential phantom billing.",
            )
            exceptions.append(ex)

            invoice.status = InvoiceStatus.AUDITED_EXCEPTION
            invoice.audit_status = AuditStatus.UNMATCHED_SHIPMENT
            invoice.audit_variance = invoice.billed_total_amount

            for line in lines:
                line.expected_amount = 0.0
                line.variance_amount = line.billed_amount
                line.audit_decision = LineAuditDecision.INVALID_LINE

            events.append(
                InvoiceStatusEvent(
                    event_id=f"EVT-{invoice.invoice_id}-01",
                    invoice_id=invoice.invoice_id,
                    from_status=initial_status,
                    to_status=InvoiceStatus.AUDITED_EXCEPTION,
                    changed_by="Automated Freight Audit Engine",
                    reason="Flagged UNKNOWN_SHIPMENT exception: shipment ID not found in system.",
                )
            )
            return invoice, lines, exceptions, events

        shipment = self.shipments[invoice.shipment_id]
        accessorials = self.shipment_accessorials.get(shipment.shipment_id, [])

        # -------------------------------------------------------------
        # Stage 2: Duplicate Billing Check
        # -------------------------------------------------------------
        shipment_key = (invoice.carrier_id, shipment.shipment_id)
        invoice_num_key = (invoice.carrier_id, invoice.invoice_number)

        if shipment_key in self.billed_shipments:
            prev_inv = self.billed_shipments[shipment_key]
            ex = AuditException(
                exception_id=self.next_exception_id(),
                invoice_id=invoice.invoice_id,
                line_id=None,
                exception_type=ExceptionType.DUPLICATE_INVOICE,
                severity=ExceptionSeverity.CRITICAL,
                expected_value=f"Single invoice for shipment (first: {prev_inv})",
                billed_value=f"Duplicate invoice: {invoice.invoice_id}",
                discrepancy_amount=invoice.billed_total_amount,
                status=ExceptionStatus.OPEN,
                assigned_to="Operations Manager",
                resolution_notes=f"Shipment {shipment.shipment_id} was already billed under invoice {prev_inv}.",
            )
            exceptions.append(ex)
            invoice.status = InvoiceStatus.AUDITED_EXCEPTION
            invoice.audit_status = AuditStatus.DUPLICATE_INVOICE
            invoice.audit_variance = invoice.billed_total_amount

            for line in lines:
                line.expected_amount = 0.0
                line.variance_amount = line.billed_amount
                line.audit_decision = LineAuditDecision.DUPLICATE_LINE

            events.append(
                InvoiceStatusEvent(
                    event_id=f"EVT-{invoice.invoice_id}-01",
                    invoice_id=invoice.invoice_id,
                    from_status=initial_status,
                    to_status=InvoiceStatus.AUDITED_EXCEPTION,
                    changed_by="Automated Freight Audit Engine",
                    reason=f"Flagged DUPLICATE_INVOICE exception: shipment already billed on {prev_inv}.",
                )
            )
            return invoice, lines, exceptions, events

        # Register keys for future duplicate detection
        self.billed_shipments[shipment_key] = invoice.invoice_id
        self.billed_invoices[invoice_num_key] = invoice.invoice_id

        # -------------------------------------------------------------
        # Stage 3: Rate Card Effective Contract Check
        # -------------------------------------------------------------
        rate_card = self.rating_engine.find_active_rate_card(
            invoice.carrier_id, shipment.lane_id, shipment.service_level, shipment.ship_date
        )

        if not rate_card or rate_card.effective_end_date < shipment.ship_date:
            expired_date = rate_card.effective_end_date.isoformat() if rate_card else "None"
            ex = AuditException(
                exception_id=self.next_exception_id(),
                invoice_id=invoice.invoice_id,
                line_id=None,
                exception_type=ExceptionType.RATE_CARD_EXPIRED,
                severity=ExceptionSeverity.HIGH,
                expected_value=f"Active contract on ship date {shipment.ship_date.isoformat()}",
                billed_value=f"Expired contract (end date: {expired_date})",
                discrepancy_amount=round(invoice.billed_total_amount - shipment.expected_total_charge, 2),
                status=ExceptionStatus.OPEN,
                assigned_to="Logistics Analyst",
                resolution_notes="Rate card expired before shipment tender date; rates cannot be validated against current contract.",
            )
            exceptions.append(ex)

        # -------------------------------------------------------------
        # Stage 4: Expected Charges Calculation
        # -------------------------------------------------------------
        if rate_card:
            rating_result = self.rating_engine.calculate_expected_charges(
                rate_card=rate_card,
                actual_weight_lbs=shipment.total_actual_weight_lbs,
                dim_weight_lbs=shipment.total_dim_weight_lbs,
                authorized_accessorials=accessorials,
            )
        else:
            # Fallback to values pre-calculated on shipment
            rating_result = None

        expected_base = rating_result.base_charge if rating_result else shipment.expected_base_charge
        expected_fsc = rating_result.fuel_surcharge_amount if rating_result else shipment.expected_fuel_surcharge

        # Authorized accessorial map: code -> standard_fee
        auth_acc_map = {acc.code.value: acc.standard_fee for acc in accessorials if acc.authorized}

        # -------------------------------------------------------------
        # Stage 5: Line-Level Charge Auditing
        # -------------------------------------------------------------
        fsc_line_count = 0
        billed_accessorial_counts: Dict[str, int] = {}

        for line in lines:
            if line.charge_type == ChargeType.BASE_FREIGHT:
                line.expected_amount = expected_base
                line.variance_amount = round(line.billed_amount - line.expected_amount, 2)

                if abs(line.variance_amount) > 1.00:
                    # Determine whether this was a weight tier misapplication
                    expected_tier, _ = determine_weight_tier(shipment.billable_weight_lbs)
                    # Check if variance matches misapplied tier
                    ex_type = ExceptionType.BASE_RATE_MISMATCH
                    if rating_result and rating_result.is_dim_weight_applied:
                        # Often carriers bill on scale weight instead of higher dim weight
                        scale_tier, _ = determine_weight_tier(shipment.total_actual_weight_lbs)
                        if scale_tier != expected_tier or line.billed_units < (shipment.billable_weight_lbs / 100.0) - 0.5:
                            ex_type = ExceptionType.WEIGHT_TIER_MISAPPLIED

                    ex = AuditException(
                        exception_id=self.next_exception_id(),
                        invoice_id=invoice.invoice_id,
                        line_id=line.line_id,
                        exception_type=ex_type,
                        severity=ExceptionSeverity.MEDIUM if abs(line.variance_amount) < 100.0 else ExceptionSeverity.HIGH,
                        expected_value=f"${expected_base:.2f} (Tier {expected_tier.value})",
                        billed_value=f"${line.billed_amount:.2f}",
                        discrepancy_amount=line.variance_amount,
                        status=ExceptionStatus.OPEN,
                        assigned_to="Logistics Analyst",
                        resolution_notes=f"Base freight charge variance on line {line.line_number}.",
                    )
                    exceptions.append(ex)
                    line.audit_decision = LineAuditDecision.OVERCHARGE if line.variance_amount > 0 else LineAuditDecision.UNDERCHARGE
                else:
                    line.audit_decision = LineAuditDecision.MATCHED

            elif line.charge_type == ChargeType.FUEL_SURCHARGE:
                fsc_line_count += 1
                if fsc_line_count > 1:
                    # Duplicate surcharge line!
                    line.expected_amount = 0.0
                    line.variance_amount = line.billed_amount
                    line.audit_decision = LineAuditDecision.DUPLICATE_LINE
                    ex = AuditException(
                        exception_id=self.next_exception_id(),
                        invoice_id=invoice.invoice_id,
                        line_id=line.line_id,
                        exception_type=ExceptionType.SURCHARGE_DUPLICATED,
                        severity=ExceptionSeverity.HIGH,
                        expected_value="Single Fuel Surcharge line",
                        billed_value=f"Duplicate fuel surcharge line #{line.line_number} (${line.billed_amount:.2f})",
                        discrepancy_amount=line.billed_amount,
                        status=ExceptionStatus.OPEN,
                        assigned_to="Logistics Analyst",
                        resolution_notes="Duplicate fuel surcharge line detected on the same invoice.",
                    )
                    exceptions.append(ex)
                else:
                    line.expected_amount = expected_fsc
                    line.variance_amount = round(line.billed_amount - line.expected_amount, 2)
                    if abs(line.variance_amount) > 1.00:
                        ex = AuditException(
                            exception_id=self.next_exception_id(),
                            invoice_id=invoice.invoice_id,
                            line_id=line.line_id,
                            exception_type=ExceptionType.FUEL_SURCHARGE_MISMATCH,
                            severity=ExceptionSeverity.MEDIUM,
                            expected_value=f"${expected_fsc:.2f}",
                            billed_value=f"${line.billed_amount:.2f}",
                            discrepancy_amount=line.variance_amount,
                            status=ExceptionStatus.OPEN,
                            assigned_to="Logistics Analyst",
                            resolution_notes="Fuel surcharge calculated does not match contracted index percentage.",
                        )
                        exceptions.append(ex)
                        line.audit_decision = LineAuditDecision.OVERCHARGE if line.variance_amount > 0 else LineAuditDecision.UNDERCHARGE
                    else:
                        line.audit_decision = LineAuditDecision.MATCHED

            elif line.charge_type == ChargeType.ACCESSORIAL:
                # Extract code or match by description
                matched_code = None
                for code_str in auth_acc_map.keys():
                    if code_str.lower() in line.description.lower():
                        matched_code = code_str
                        break

                acc_key = matched_code or line.description
                billed_accessorial_counts[acc_key] = billed_accessorial_counts.get(acc_key, 0) + 1

                if billed_accessorial_counts[acc_key] > 1:
                    # Duplicate accessorial!
                    line.expected_amount = 0.0
                    line.variance_amount = line.billed_amount
                    line.audit_decision = LineAuditDecision.DUPLICATE_LINE
                    ex = AuditException(
                        exception_id=self.next_exception_id(),
                        invoice_id=invoice.invoice_id,
                        line_id=line.line_id,
                        exception_type=ExceptionType.SURCHARGE_DUPLICATED,
                        severity=ExceptionSeverity.HIGH,
                        expected_value=f"Single accessorial line for {acc_key}",
                        billed_value=f"Duplicate accessorial line #{line.line_number}",
                        discrepancy_amount=line.billed_amount,
                        status=ExceptionStatus.OPEN,
                        assigned_to="Logistics Analyst",
                        resolution_notes=f"Duplicate accessorial fee billed for {acc_key}.",
                    )
                    exceptions.append(ex)
                elif matched_code and matched_code in auth_acc_map:
                    # Valid authorized accessorial
                    line.expected_amount = auth_acc_map[matched_code]
                    line.variance_amount = round(line.billed_amount - line.expected_amount, 2)
                    if abs(line.variance_amount) > 1.00:
                        ex = AuditException(
                            exception_id=self.next_exception_id(),
                            invoice_id=invoice.invoice_id,
                            line_id=line.line_id,
                            exception_type=ExceptionType.BASE_RATE_MISMATCH,
                            severity=ExceptionSeverity.LOW,
                            expected_value=f"${line.expected_amount:.2f}",
                            billed_value=f"${line.billed_amount:.2f}",
                            discrepancy_amount=line.variance_amount,
                            status=ExceptionStatus.OPEN,
                            assigned_to="Logistics Analyst",
                            resolution_notes=f"Accessorial fee variance on {matched_code}.",
                        )
                        exceptions.append(ex)
                        line.audit_decision = LineAuditDecision.OVERCHARGE if line.variance_amount > 0 else LineAuditDecision.UNDERCHARGE
                    else:
                        line.audit_decision = LineAuditDecision.MATCHED
                else:
                    # Unauthorized accessorial!
                    line.expected_amount = 0.0
                    line.variance_amount = line.billed_amount
                    line.audit_decision = LineAuditDecision.INVALID_LINE
                    ex = AuditException(
                        exception_id=self.next_exception_id(),
                        invoice_id=invoice.invoice_id,
                        line_id=line.line_id,
                        exception_type=ExceptionType.INVALID_ACCESSORIAL,
                        severity=ExceptionSeverity.MEDIUM,
                        expected_value="$0.00 (Not authorized on BOL/Shipment)",
                        billed_value=f"${line.billed_amount:.2f} ({line.description})",
                        discrepancy_amount=line.billed_amount,
                        status=ExceptionStatus.OPEN,
                        assigned_to="Logistics Analyst",
                        resolution_notes="Accessorial was not requested or authorized by shipper on the Bill of Lading.",
                    )
                    exceptions.append(ex)
            else:
                # Other misc fees
                line.expected_amount = 0.0
                line.variance_amount = line.billed_amount
                line.audit_decision = LineAuditDecision.MATCHED if line.billed_amount == 0 else LineAuditDecision.OVERCHARGE

        # -------------------------------------------------------------
        # Stage 6: Invoice-Level Rollup & Lifecycle Transition
        # -------------------------------------------------------------
        total_expected = sum(line.expected_amount for line in lines)
        total_billed = sum(line.billed_amount for line in lines)
        invoice.billed_total_amount = round(total_billed, 2)
        invoice.audit_variance = round(total_billed - total_expected, 2)

        if exceptions:
            invoice.status = InvoiceStatus.AUDITED_EXCEPTION
            invoice.audit_status = AuditStatus.DISCREPANCY_DETECTED
            events.append(
                InvoiceStatusEvent(
                    event_id=f"EVT-{invoice.invoice_id}-01",
                    invoice_id=invoice.invoice_id,
                    from_status=initial_status,
                    to_status=InvoiceStatus.AUDITED_EXCEPTION,
                    changed_by="Automated Freight Audit Engine",
                    reason=f"Audit completed with {len(exceptions)} exception(s); total variance: ${invoice.audit_variance:+.2f}.",
                )
            )
        else:
            invoice.status = InvoiceStatus.AUDITED_APPROVED
            invoice.audit_status = AuditStatus.CLEARED
            events.append(
                InvoiceStatusEvent(
                    event_id=f"EVT-{invoice.invoice_id}-01",
                    invoice_id=invoice.invoice_id,
                    from_status=initial_status,
                    to_status=InvoiceStatus.AUDITED_APPROVED,
                    changed_by="Automated Freight Audit Engine",
                    reason="Invoice fully matched contracted rates and authorized accessorials. Cleared for payment.",
                )
            )

        return invoice, lines, exceptions, events
