"""
Freight Invoice Audit - FastAPI REST Service
Exposes RESTful endpoints for invoice ingestion, real-time multi-stage auditing,
dispute resolution workflows, credit note reconciliation, and performance metrics.
"""
from datetime import date, datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from freight_audit.generator.seed_generator import FreightDataGenerator, DatasetBundle
from freight_audit.engine.rating import RatingEngine
from freight_audit.engine.auditor import FreightAuditor
from freight_audit.engine.credit_note import DisputeReconciliationEngine
from freight_audit.evaluation.metrics import AuditMetricsEvaluator, AuditPerformanceReport
from freight_audit.models.entities import (
    FreightInvoice,
    InvoiceLine,
    AuditException,
    CreditNote,
    AuditResolutionEvent,
)
from freight_audit.models.enums import (
    ExceptionStatus,
    ExceptionSeverity,
    ExceptionType,
    InvoiceStatus,
    AuditStatus,
    ChargeType,
)

app = FastAPI(
    title="Freight Invoice Audit & Rating Engine API",
    description="Automated Freight Invoice Validation, Contract Rating, Exception Detection & Dispute Settlement API",
    version="1.0.0",
)

# Global in-memory cache populated from generator or database
bundle: Optional[DatasetBundle] = None
rating_engine: Optional[RatingEngine] = None
auditor: Optional[FreightAuditor] = None
recon_engine = DisputeReconciliationEngine()

def init_system(scale: str = "starter", seed: int = 20261022):
    global bundle, rating_engine, auditor
    gen = FreightDataGenerator(seed=seed)
    if scale == "full":
        bundle = gen.generate(num_carriers=100, num_shipments=20000, num_invoices=15000, num_lanes=500)
    else:
        bundle = gen.generate(num_carriers=25, num_shipments=500, num_invoices=400, num_lanes=100)

    rating_engine = RatingEngine(bundle.rate_cards)
    shipment_map = {s.shipment_id: s for s in bundle.shipments}
    acc_map: Dict[str, list] = {}
    for acc in bundle.accessorials:
        acc_map.setdefault(acc.shipment_id, []).append(acc)
    rc_map = {rc.rate_card_id: rc for rc in bundle.rate_cards}

    auditor = FreightAuditor(
        rating_engine=rating_engine,
        shipments=shipment_map,
        shipment_accessorials=acc_map,
        rate_cards_by_id=rc_map,
    )

@app.on_event("startup")
def startup_event():
    init_system("starter", 20261022)

@app.get("/health", tags=["System"])
def healthcheck():
    return {
        "status": "online",
        "timestamp": datetime.utcnow().isoformat(),
        "carriers_loaded": len(bundle.carriers) if bundle else 0,
        "shipments_loaded": len(bundle.shipments) if bundle else 0,
        "invoices_audited": len(bundle.freight_invoices) if bundle else 0,
        "exceptions_active": len(bundle.audit_exceptions) if bundle else 0,
    }

class InvoiceAuditRequest(BaseModel):
    invoice_id: str
    carrier_id: str
    shipment_id: Optional[str] = None
    invoice_number: str
    invoice_date: date
    due_date: date
    lines: List[dict]

@app.post("/audit/invoice", tags=["Audit Engine"])
def audit_incoming_invoice(req: InvoiceAuditRequest):
    """
    Ingest a new invoice and execute the multi-stage freight audit engine.
    """
    if not auditor:
        raise HTTPException(status_code=500, detail="Auditor engine not initialized.")

    lines = [InvoiceLine(**l) for l in req.lines]
    billed_total = sum(l.billed_amount for l in lines)
    inv = FreightInvoice(
        invoice_id=req.invoice_id,
        carrier_id=req.carrier_id,
        shipment_id=req.shipment_id,
        invoice_number=req.invoice_number,
        invoice_date=req.invoice_date,
        due_date=req.due_date,
        billed_total_amount=billed_total,
    )

    audited_inv, audited_lines, exceptions, events = auditor.audit_invoice(inv, lines)

    return {
        "invoice": audited_inv.model_dump(),
        "lines": [l.model_dump() for l in audited_lines],
        "exceptions": [e.model_dump() for e in exceptions],
        "events": [ev.model_dump() for ev in events],
    }

@app.get("/exceptions", tags=["Exceptions & Disputes"])
def list_exceptions(
    status_filter: Optional[ExceptionStatus] = None,
    severity: Optional[ExceptionSeverity] = None,
    limit: int = 50,
):
    """
    List audit exceptions with optional filtering by workflow status and severity.
    """
    if not bundle:
        return []
    res = bundle.audit_exceptions
    if status_filter:
        res = [e for e in res if e.status == status_filter]
    if severity:
        res = [e for e in res if e.severity == severity]
    return [e.model_dump() for e in res[:limit]]

class DisputeResolutionRequest(BaseModel):
    decision: ExceptionStatus = Field(..., description="APPROVED_DISPUTE or REJECTED_DISPUTE")
    decided_by: str = Field(default="Operations Manager")
    decision_reason: str
    approved_amount: Optional[float] = None

@app.post("/exceptions/{exception_id}/resolve", tags=["Exceptions & Disputes"])
def resolve_exception(exception_id: str, req: DisputeResolutionRequest):
    """
    Logistics Analyst or Operations Manager decision on an audit exception.
    """
    if not bundle:
        raise HTTPException(status_code=500, detail="System not loaded.")

    target_ex = next((e for e in bundle.audit_exceptions if e.exception_id == exception_id), None)
    if not target_ex:
        raise HTTPException(status_code=404, detail=f"Exception {exception_id} not found.")

    updated_ex, event = recon_engine.resolve_exception_dispute(
        exception=target_ex,
        decision=req.decision,
        decided_by=req.decided_by,
        decision_reason=req.decision_reason,
        approved_amount=req.approved_amount,
    )
    bundle.audit_resolution_events.append(event)

    return {
        "message": f"Exception {exception_id} successfully transitioned to {req.decision.value}.",
        "exception": updated_ex.model_dump(),
        "resolution_event": event.model_dump(),
    }

class CreditNoteRequest(BaseModel):
    carrier_id: str
    credit_amount: Optional[float] = None
    force_overcredit_ratio: float = 1.0

@app.post("/exceptions/{exception_id}/issue-credit", tags=["Credit Notes"])
def issue_credit_note(exception_id: str, req: CreditNoteRequest):
    """
    Issue a credit note settling an approved audit exception and reconcile balance.
    """
    if not bundle:
        raise HTTPException(status_code=500, detail="System not loaded.")

    target_ex = next((e for e in bundle.audit_exceptions if e.exception_id == exception_id), None)
    if not target_ex:
        raise HTTPException(status_code=404, detail=f"Exception {exception_id} not found.")

    if target_ex.status != ExceptionStatus.APPROVED_DISPUTE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot issue credit note: exception is {target_ex.status.value}, not APPROVED_DISPUTE.",
        )

    cn = recon_engine.generate_credit_note_for_exception(
        exception=target_ex,
        carrier_id=req.carrier_id,
        credit_amount=req.credit_amount,
        force_overcredit_ratio=req.force_overcredit_ratio,
    )
    bundle.credit_notes.append(cn)

    success, msg, excess_ex = recon_engine.reconcile_credit_note(cn, target_ex)
    if excess_ex:
        bundle.audit_exceptions.append(excess_ex)

    return {
        "credit_note": cn.model_dump(),
        "reconciliation_success": success,
        "message": msg,
        "excess_exception": excess_ex.model_dump() if excess_ex else None,
    }

@app.get("/metrics", tags=["Analytics & Evaluation"])
def get_performance_metrics():
    """
    Calculate and return precision, recall, F1, accuracy, and financial recovery metrics.
    """
    if not bundle:
        raise HTTPException(status_code=500, detail="System not loaded.")

    report = AuditMetricsEvaluator.evaluate(bundle)
    return report.__dict__
