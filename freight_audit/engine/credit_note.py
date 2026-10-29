"""
Credit Note & Dispute Reconciliation Engine
Manages dispute approval workflows, credit note issuance, and
arithmetic balance reconciliation against approved audit exceptions.
"""
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple
from freight_audit.models.entities import (
    AuditException,
    CreditNote,
    AuditResolutionEvent,
)
from freight_audit.models.enums import (
    ExceptionStatus,
    CreditNoteStatus,
    ReconciliationStatus,
    ExceptionType,
    ExceptionSeverity,
)

class DisputeReconciliationEngine:
    def __init__(
        self,
        credit_notes: Optional[List[CreditNote]] = None,
        resolution_events: Optional[List[AuditResolutionEvent]] = None,
        exceptions: Optional[List[AuditException]] = None,
    ):
        self.credit_note_counter = max(
            (int(item.credit_note_id.rsplit("-", 1)[1]) for item in credit_notes or []),
            default=0,
        )
        self.resolution_event_counter = max(
            (int(item.event_id.rsplit("-", 1)[1]) for item in resolution_events or []),
            default=0,
        )
        self.exception_counter = max(
            (int(item.exception_id.rsplit("-", 1)[1]) for item in exceptions or []),
            default=0,
        )

    def next_credit_note_id(self) -> str:
        self.credit_note_counter += 1
        return f"CN-2026-{self.credit_note_counter:06d}"

    def next_resolution_event_id(self) -> str:
        self.resolution_event_counter += 1
        return f"REV-2026-{self.resolution_event_counter:06d}"

    def next_exception_id(self) -> str:
        self.exception_counter += 1
        return f"FEX-2026-{self.exception_counter:06d}"

    def resolve_exception_dispute(
        self,
        exception: AuditException,
        decision: ExceptionStatus,
        decided_by: str,
        decision_reason: str,
        approved_amount: Optional[float] = None,
    ) -> Tuple[AuditException, AuditResolutionEvent]:
        """
        Transition exception state and generate immutable resolution event history.
        """
        if exception.status != ExceptionStatus.OPEN:
            raise ValueError(
                f"Cannot resolve exception {exception.exception_id}: "
                f"current status is {exception.status.value}, not OPEN."
            )
        if decision not in {
            ExceptionStatus.APPROVED_DISPUTE,
            ExceptionStatus.REJECTED_DISPUTE,
        }:
            raise ValueError("A dispute decision must approve or reject the exception.")
        if approved_amount is not None and not 0 <= approved_amount <= exception.discrepancy_amount:
            raise ValueError(
                "Approved amount must be between zero and the exception discrepancy."
            )

        initial_status = exception.status
        amount = approved_amount if approved_amount is not None else exception.discrepancy_amount
        exception.status = decision
        exception.resolved_at = datetime.now(timezone.utc)
        exception.resolution_notes = f"[{decided_by}] {decision_reason} (Settled Amount: ${amount:.2f})"

        event = AuditResolutionEvent(
            event_id=self.next_resolution_event_id(),
            exception_id=exception.exception_id,
            from_status=initial_status,
            to_status=decision,
            decided_by=decided_by,
            decision_reason=decision_reason,
            approved_amount=amount,
            timestamp=datetime.now(timezone.utc),
        )
        return exception, event

    def generate_credit_note_for_exception(
        self,
        exception: AuditException,
        carrier_id: str,
        credit_amount: Optional[float] = None,
        issue_date: Optional[date] = None,
        force_overcredit_ratio: float = 1.0,
        approved_amount: Optional[float] = None,
    ) -> CreditNote:
        """
        Issue a CreditNote to settle an approved exception dispute.
        Optionally injects overcredit anomaly when force_overcredit_ratio != 1.0.
        """
        base_amt = approved_amount if approved_amount is not None else exception.discrepancy_amount
        target_credit = round(base_amt * force_overcredit_ratio, 2) if credit_amount is None else credit_amount
        today = issue_date or date.today()

        # Check reconciliation balance
        diff = round(target_credit - base_amt, 2)
        if abs(diff) < 0.01:
            recon_status = ReconciliationStatus.RECONCILED
        elif diff > 0.0:
            recon_status = ReconciliationStatus.OVERCREDITED
        else:
            recon_status = ReconciliationStatus.UNDERCREDITED

        cn = CreditNote(
            credit_note_id=self.next_credit_note_id(),
            carrier_id=carrier_id,
            invoice_id=exception.invoice_id,
            exception_id=exception.exception_id,
            credit_note_number=f"CN-{carrier_id[-4:]}-{today.strftime('%Y%m%d')}-{self.credit_note_counter:04d}",
            credit_amount=target_credit,
            original_exception_amount=base_amt,
            status=CreditNoteStatus.APPLIED,
            issue_date=today,
            reconciliation_status=recon_status,
            created_at=datetime.now(timezone.utc),
        )
        return cn

    def reconcile_credit_note(
        self, credit_note: CreditNote, exception: AuditException
    ) -> Tuple[bool, str, Optional[AuditException]]:
        """
        Reconcile a credit note against its originating exception.
        Detects 'credit note exceeds exception amount' edge case.
        """
        approved_amount = credit_note.original_exception_amount
        diff = round(credit_note.credit_amount - approved_amount, 2)

        if diff > 0.05:  # Overcredited!
            excess_ex = AuditException(
                exception_id=self.next_exception_id(),
                invoice_id=credit_note.invoice_id,
                line_id=None,
                exception_type=ExceptionType.CREDIT_NOTE_EXCEEDS_EXCEPTION,
                severity=ExceptionSeverity.HIGH,
                expected_value=f"${approved_amount:.2f}",
                billed_value=f"${credit_note.credit_amount:.2f}",
                discrepancy_amount=diff,
                status=ExceptionStatus.OPEN,
                assigned_to="Operations Manager",
                resolution_notes=f"Credit note {credit_note.credit_note_id} exceeds approved dispute by ${diff:.2f}.",
            )
            return False, f"Credit note exceeds approved exception by ${diff:.2f}", excess_ex

        elif diff < -0.05:
            return False, f"Credit note undercredits approved exception by ${abs(diff):.2f}", None

        else:
            return True, "Credit note perfectly reconciled to approved exception.", None
