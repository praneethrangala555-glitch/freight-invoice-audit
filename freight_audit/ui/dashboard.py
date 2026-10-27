"""
Freight Invoice Audit Engine - Interactive Operations Dashboard
Provides real-time interactive workbenches for Logistics Analysts, Operations Managers,
Planners, and Carriers to review audit decisions, dispute variances, and reconcile credits.
"""
from datetime import date
from pathlib import Path
import sys
import pandas as pd
import streamlit as st

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from freight_audit.generator.seed_generator import FreightDataGenerator, DatasetBundle
from freight_audit.evaluation.metrics import AuditMetricsEvaluator
from freight_audit.engine.credit_note import DisputeReconciliationEngine
from freight_audit.models.enums import ExceptionStatus, ExceptionSeverity

st.set_page_config(
    page_title="Freight Invoice Audit & Recovery Platform",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for executive styling
st.markdown(
    """
    <style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #1E3A8A; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.05rem; color: #4B5563; margin-bottom: 1.5rem; }
    .metric-card { background-color: #F3F4F6; border-radius: 8px; padding: 1rem; border-left: 4px solid #3B82F6; }
    .badge-clean { background-color: #DEF7EC; color: #03543F; padding: 3px 8px; border-radius: 4px; font-weight: 600; }
    .badge-error { background-color: #FDE8E8; color: #9B1C1C; padding: 3px 8px; border-radius: 4px; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

@st.cache_resource
def load_data(scale: str, seed: int) -> DatasetBundle:
    gen = FreightDataGenerator(seed=seed)
    if scale == "full":
        return gen.generate(num_carriers=100, num_shipments=20000, num_invoices=15000, num_lanes=500)
    else:
        return gen.generate(num_carriers=25, num_shipments=500, num_invoices=400, num_lanes=100)

# Sidebar Configuration
st.sidebar.title("🚚 System Controls")
scale_option = st.sidebar.selectbox("Data Scale", ["starter (400 inv)", "full (15,000 inv)"], index=0)
scale = "full" if "full" in scale_option else "starter"
seed = st.sidebar.number_input("Deterministic Seed", value=20261022, step=1)
actor_role = st.sidebar.selectbox(
    "Active Persona",
    ["Logistics Analyst", "Operations Manager", "Transportation Planner", "Carrier Representative"]
)

bundle = load_data(scale, seed)
metrics = AuditMetricsEvaluator.evaluate(bundle)

st.markdown('<div class="main-header">Freight Invoice Audit & Discrepancy Reconciliation</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-header">Active Persona: <b>{actor_role}</b> | Verified Seed: <code>{seed}</code> | Status: <b>Online</b></div>', unsafe_allow_html=True)

# Executive KPIs
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Invoices Audited", f"{metrics.total_invoices_audited:,}")
col2.metric("Total Billed Spend", f"${metrics.total_spend_billed_usd:,.2f}")
col3.metric("Overcharges Detected", f"${metrics.total_overcharge_detected_usd:,.2f}", delta=f"-${metrics.total_overcharge_detected_usd:,.2f}", delta_color="inverse")
col4.metric("Audit F1-Score", f"{metrics.f1_score:.4f}", delta=f"{metrics.precision*100:.1f}% Prec")
col5.metric("Disputes Settled", f"${metrics.credit_notes_issued_usd:,.2f}")

tabs = st.tabs([
    "📋 Invoice Audit Workbench",
    "⚖️ Exception Dispute Management",
    "📈 Anomaly Distribution & Accuracy",
    "📑 Contract & Rate Card Lookup",
])

# -------------------------------------------------------------
# TAB 1: Invoice Audit Workbench
# -------------------------------------------------------------
with tabs[0]:
    st.subheader("Invoice Line-Level Discrepancy Inspector")

    inv_status_filter = st.selectbox(
        "Filter by Audit Status",
        ["ALL", "DISCREPANCY_DETECTED", "CLEARED", "UNMATCHED_SHIPMENT", "DUPLICATE_INVOICE"],
        index=0,
    )

    filtered_invoices = bundle.freight_invoices
    if inv_status_filter != "ALL":
        filtered_invoices = [i for i in filtered_invoices if i.audit_status.value == inv_status_filter]

    inv_display = [
        {
            "Invoice ID": i.invoice_id,
            "Carrier ID": i.carrier_id,
            "Shipment ID": i.shipment_id or "N/A",
            "Billed Amount ($)": f"${i.billed_total_amount:.2f}",
            "Audit Variance ($)": f"${i.audit_variance:+.2f}",
            "Audit Status": i.audit_status.value,
            "Workflow Status": i.status.value,
        }
        for i in filtered_invoices[:150]
    ]

    st.dataframe(pd.DataFrame(inv_display), use_container_width=True, height=220)

    # Drill down selector
    selected_inv_id = st.selectbox("Select Invoice ID to Inspect Line Items", [i["Invoice ID"] for i in inv_display[:50]])

    if selected_inv_id:
        target_inv = next(i for i in bundle.freight_invoices if i.invoice_id == selected_inv_id)
        target_lines = [l for l in bundle.invoice_lines if l.invoice_id == selected_inv_id]

        c_a, c_b = st.columns([1, 2])
        with c_a:
            st.markdown("#### Invoice Details")
            st.write(f"**Carrier:** `{target_inv.carrier_id}`")
            st.write(f"**Shipment Reference:** `{target_inv.shipment_id}`")
            st.write(f"**Invoice Date:** `{target_inv.invoice_date}` (Due: `{target_inv.due_date}`)")
            st.write(f"**Billed Total:** `${target_inv.billed_total_amount:.2f}`")
            st.write(f"**Total Discrepancy:** `${target_inv.audit_variance:+.2f}`")

        with c_b:
            st.markdown("#### Itemized Line Audit Decisions")
            line_data = [
                {
                    "Line #": l.line_number,
                    "Charge Type": l.charge_type.value,
                    "Description": l.description,
                    "Billed ($)": f"${l.billed_amount:.2f}",
                    "Expected ($)": f"${l.expected_amount:.2f}",
                    "Variance ($)": f"${l.variance_amount:+.2f}",
                    "Decision": l.audit_decision.value,
                }
                for l in target_lines
            ]
            st.table(pd.DataFrame(line_data))

# -------------------------------------------------------------
# TAB 2: Exception Dispute Management
# -------------------------------------------------------------
with tabs[1]:
    st.subheader("Active Audit Exceptions & Credit Settlement")
    st.markdown("Operations Managers and Logistics Analysts review flagged billing exceptions, approve disputes, and reconcile credit notes.")

    ex_df = [
        {
            "Exception ID": e.exception_id,
            "Invoice ID": e.invoice_id,
            "Type": e.exception_type.value,
            "Severity": e.severity.value,
            "Discrepancy ($)": f"${e.discrepancy_amount:.2f}",
            "Status": e.status.value,
            "Assigned To": e.assigned_to,
            "Notes": e.resolution_notes,
        }
        for e in bundle.audit_exceptions[:100]
    ]
    st.dataframe(pd.DataFrame(ex_df), use_container_width=True, height=220)

    # Resolution action panel
    st.markdown("### Dispute Resolution & Credit Note Action")
    col_x, col_y, col_z = st.columns([1, 1, 1])

    with col_x:
        action_ex_id = st.selectbox("Select Exception to Resolve", [e.exception_id for e in bundle.audit_exceptions[:50]])
        target_ex = next((e for e in bundle.audit_exceptions if e.exception_id == action_ex_id), None)

    with col_y:
        action_type = st.radio("Resolution Decision", ["APPROVED_DISPUTE", "REJECTED_DISPUTE"])
        reason = st.text_input("Decision Rationale", "Rate discrepancy verified against contracted rate schedule.")

    with col_z:
        st.write("")
        st.write("")
        if st.button("Apply Resolution Decision"):
            recon = DisputeReconciliationEngine()
            updated_ex, event = recon.resolve_exception_dispute(
                exception=target_ex,
                decision=ExceptionStatus(action_type),
                decided_by=actor_role,
                decision_reason=reason,
            )
            bundle.audit_resolution_events.append(event)
            st.success(f"Exception `{target_ex.exception_id}` transitioned to `{action_type}`!")

# -------------------------------------------------------------
# TAB 3: Anomaly Distribution & Accuracy
# -------------------------------------------------------------
with tabs[2]:
    st.subheader("Ground Truth Benchmark & Anomaly Coverage")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Confusion Matrix & Classification Metrics")
        st.write(f"- **True Positives (Anomalies Caught):** `{metrics.true_positives:,}`")
        st.write(f"- **True Negatives (Clean Cleared):** `{metrics.true_negatives:,}`")
        st.write(f"- **False Positives:** `{metrics.false_positives:,}`")
        st.write(f"- **False Negatives:** `{metrics.false_negatives:,}`")
        st.write(f"- **Accuracy:** `{metrics.accuracy * 100:.2f}%`")
        st.write(f"- **Precision:** `{metrics.precision * 100:.2f}%`")
        st.write(f"- **Recall:** `{metrics.recall * 100:.2f}%`")

    with c2:
        st.markdown("#### Financial Recovery Breakdown")
        st.write(f"- **Gross Overcharges Flagged:** `${metrics.total_overcharge_detected_usd:,.2f}`")
        st.write(f"- **Credit Notes Disbursed:** `${metrics.credit_notes_issued_usd:,.2f}`")
        st.write(f"- **Audit Net Recovery Rate:** `{metrics.recovery_rate_pct:.2f}%`")

    st.markdown("#### Discrepancy Breakdown by Category")
    cat_rows = []
    for cat_name, stats in metrics.anomalies_by_category.items():
        cat_rows.append({
            "Anomaly Category": cat_name,
            "Total Invoices": stats["count"],
            "Detected": stats["detected"],
            "Total Variance ($)": f"${stats['total_variance_usd']:,.2f}",
        })
    st.table(pd.DataFrame(cat_rows))

# -------------------------------------------------------------
# TAB 4: Contract & Rate Card Lookup
# -------------------------------------------------------------
with tabs[3]:
    st.subheader("Contracted Rate Schedules & Lanes")
    rc_data = [
        {
            "Rate Card ID": rc.rate_card_id,
            "Carrier ID": rc.carrier_id,
            "Lane ID": rc.lane_id,
            "Service": rc.service_level.value,
            "Effective Dates": f"{rc.effective_start_date} to {rc.effective_end_date}",
            "Min Charge ($)": f"${rc.base_min_charge:.2f}",
            "Tier 1 (<500 lbs)": f"${rc.rate_tier_1_cwt:.2f}/cwt",
            "Tier 2 (500-1999)": f"${rc.rate_tier_2_cwt:.2f}/cwt",
            "Tier 3 (2000-4999)": f"${rc.rate_tier_3_cwt:.2f}/cwt",
            "Fuel Surcharge %": f"{rc.fuel_surcharge_pct * 100:.1f}%",
        }
        for rc in bundle.rate_cards[:50]
    ]
    st.dataframe(pd.DataFrame(rc_data), use_container_width=True)
