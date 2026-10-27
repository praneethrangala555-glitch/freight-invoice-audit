"""
Freight Invoice Audit Engine - Relational SQL DDL Schema
Defines DDL for all 11 core entities, foreign key constraints, indexes, and history tables.
"""

SQL_SCHEMA_DDL = """
-- 1. Carrier Master
CREATE TABLE IF NOT EXISTS carriers (
    carrier_id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    scac VARCHAR(4) NOT NULL UNIQUE,
    mode VARCHAR(20) NOT NULL,
    contact_email VARCHAR(100) NOT NULL,
    payment_terms_days INTEGER NOT NULL DEFAULT 30,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Lane Master
CREATE TABLE IF NOT EXISTS lanes (
    lane_id VARCHAR(11) PRIMARY KEY,
    origin_city VARCHAR(50) NOT NULL,
    origin_state VARCHAR(2) NOT NULL,
    origin_zip_prefix VARCHAR(3) NOT NULL,
    destination_city VARCHAR(50) NOT NULL,
    destination_state VARCHAR(2) NOT NULL,
    destination_zip_prefix VARCHAR(3) NOT NULL,
    distance_miles REAL NOT NULL,
    standard_transit_days INTEGER NOT NULL
);

-- 3. RateCard Contract
CREATE TABLE IF NOT EXISTS rate_cards (
    rate_card_id VARCHAR(30) PRIMARY KEY,
    carrier_id VARCHAR(10) NOT NULL,
    lane_id VARCHAR(11) NOT NULL,
    service_level VARCHAR(20) NOT NULL,
    effective_start_date DATE NOT NULL,
    effective_end_date DATE NOT NULL,
    base_min_charge REAL NOT NULL,
    rate_tier_1_cwt REAL NOT NULL,
    rate_tier_2_cwt REAL NOT NULL,
    rate_tier_3_cwt REAL NOT NULL,
    rate_tier_4_cwt REAL NOT NULL,
    rate_tier_5_cwt REAL NOT NULL,
    dim_factor INTEGER NOT NULL DEFAULT 139,
    fuel_surcharge_pct REAL NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    FOREIGN KEY (carrier_id) REFERENCES carriers(carrier_id),
    FOREIGN KEY (lane_id) REFERENCES lanes(lane_id)
);

-- 4. Shipment Transaction
CREATE TABLE IF NOT EXISTS shipments (
    shipment_id VARCHAR(15) PRIMARY KEY,
    carrier_id VARCHAR(10) NOT NULL,
    lane_id VARCHAR(11) NOT NULL,
    service_level VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    ship_date DATE NOT NULL,
    delivery_date DATE,
    bol_number VARCHAR(20) NOT NULL UNIQUE,
    total_pieces INTEGER NOT NULL,
    total_actual_weight_lbs REAL NOT NULL,
    total_dim_weight_lbs REAL NOT NULL,
    billable_weight_lbs REAL NOT NULL,
    expected_base_charge REAL NOT NULL,
    expected_fuel_surcharge REAL NOT NULL,
    expected_accessorials_charge REAL NOT NULL,
    expected_total_charge REAL NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (carrier_id) REFERENCES carriers(carrier_id),
    FOREIGN KEY (lane_id) REFERENCES lanes(lane_id)
);

-- 5. Shipment Legs
CREATE TABLE IF NOT EXISTS shipment_legs (
    leg_id VARCHAR(25) PRIMARY KEY,
    shipment_id VARCHAR(15) NOT NULL,
    leg_sequence INTEGER NOT NULL,
    origin_location VARCHAR(100) NOT NULL,
    destination_location VARCHAR(100) NOT NULL,
    pickup_time TIMESTAMP NOT NULL,
    delivery_time TIMESTAMP,
    leg_status VARCHAR(20) NOT NULL,
    distance_miles REAL NOT NULL,
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id)
);

-- 6. Weight Measurements
CREATE TABLE IF NOT EXISTS weight_measurements (
    measurement_id VARCHAR(14) PRIMARY KEY,
    shipment_id VARCHAR(15) NOT NULL,
    piece_number INTEGER NOT NULL,
    length_in REAL NOT NULL,
    width_in REAL NOT NULL,
    height_in REAL NOT NULL,
    scale_weight_lbs REAL NOT NULL,
    dim_weight_lbs REAL NOT NULL,
    measurement_type VARCHAR(30) NOT NULL,
    measured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    scale_id VARCHAR(20) NOT NULL,
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id)
);

-- 7. Accessorial Services
CREATE TABLE IF NOT EXISTS accessorials (
    accessorial_id VARCHAR(15) PRIMARY KEY,
    shipment_id VARCHAR(15) NOT NULL,
    code VARCHAR(30) NOT NULL,
    description VARCHAR(100) NOT NULL,
    standard_fee REAL NOT NULL,
    authorized BOOLEAN NOT NULL DEFAULT 1,
    proof_document_id VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id)
);

-- 8. Freight Invoices
CREATE TABLE IF NOT EXISTS freight_invoices (
    invoice_id VARCHAR(16) PRIMARY KEY,
    carrier_id VARCHAR(10) NOT NULL,
    shipment_id VARCHAR(15),
    invoice_number VARCHAR(30) NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    billed_base_charge REAL NOT NULL DEFAULT 0.0,
    billed_fuel_surcharge REAL NOT NULL DEFAULT 0.0,
    billed_accessorials_charge REAL NOT NULL DEFAULT 0.0,
    billed_total_amount REAL NOT NULL DEFAULT 0.0,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING_AUDIT',
    audit_status VARCHAR(30) NOT NULL DEFAULT 'CLEARED',
    audit_variance REAL NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (carrier_id) REFERENCES carriers(carrier_id),
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id)
);

-- 9. Invoice Lines
CREATE TABLE IF NOT EXISTS invoice_lines (
    line_id VARCHAR(25) PRIMARY KEY,
    invoice_id VARCHAR(16) NOT NULL,
    line_number INTEGER NOT NULL,
    charge_type VARCHAR(30) NOT NULL,
    description VARCHAR(100) NOT NULL,
    billed_rate REAL NOT NULL,
    billed_units REAL NOT NULL,
    billed_amount REAL NOT NULL,
    expected_amount REAL NOT NULL DEFAULT 0.0,
    variance_amount REAL NOT NULL DEFAULT 0.0,
    audit_decision VARCHAR(30) NOT NULL DEFAULT 'MATCHED',
    FOREIGN KEY (invoice_id) REFERENCES freight_invoices(invoice_id)
);

-- 10. Audit Exceptions
CREATE TABLE IF NOT EXISTS audit_exceptions (
    exception_id VARCHAR(15) PRIMARY KEY,
    invoice_id VARCHAR(16) NOT NULL,
    line_id VARCHAR(25),
    exception_type VARCHAR(40) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    expected_value TEXT NOT NULL,
    billed_value TEXT NOT NULL,
    discrepancy_amount REAL NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'OPEN',
    assigned_to VARCHAR(50) NOT NULL,
    resolution_notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    FOREIGN KEY (invoice_id) REFERENCES freight_invoices(invoice_id),
    FOREIGN KEY (line_id) REFERENCES invoice_lines(line_id)
);

-- 11. Credit Notes
CREATE TABLE IF NOT EXISTS credit_notes (
    credit_note_id VARCHAR(14) PRIMARY KEY,
    carrier_id VARCHAR(10) NOT NULL,
    invoice_id VARCHAR(16) NOT NULL,
    exception_id VARCHAR(15) NOT NULL,
    credit_note_number VARCHAR(30) NOT NULL,
    credit_amount REAL NOT NULL,
    original_exception_amount REAL NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING_CARRIER',
    issue_date DATE NOT NULL,
    reconciliation_status VARCHAR(30) NOT NULL DEFAULT 'RECONCILED',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (carrier_id) REFERENCES carriers(carrier_id),
    FOREIGN KEY (invoice_id) REFERENCES freight_invoices(invoice_id),
    FOREIGN KEY (exception_id) REFERENCES audit_exceptions(exception_id)
);

-- Event History Tables for Complete Traceability
CREATE TABLE IF NOT EXISTS invoice_status_events (
    event_id VARCHAR(36) PRIMARY KEY,
    invoice_id VARCHAR(16) NOT NULL,
    from_status VARCHAR(30) NOT NULL,
    to_status VARCHAR(30) NOT NULL,
    changed_by VARCHAR(50) NOT NULL,
    reason TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (invoice_id) REFERENCES freight_invoices(invoice_id)
);

CREATE TABLE IF NOT EXISTS audit_resolution_events (
    event_id VARCHAR(36) PRIMARY KEY,
    exception_id VARCHAR(15) NOT NULL,
    from_status VARCHAR(30) NOT NULL,
    to_status VARCHAR(30) NOT NULL,
    decided_by VARCHAR(50) NOT NULL,
    decision_reason TEXT NOT NULL,
    approved_amount REAL NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (exception_id) REFERENCES audit_exceptions(exception_id)
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_rate_cards_lookup ON rate_cards(carrier_id, lane_id, service_level, status);
CREATE INDEX IF NOT EXISTS idx_shipments_carrier ON shipments(carrier_id);
CREATE INDEX IF NOT EXISTS idx_shipments_lane ON shipments(lane_id);
CREATE INDEX IF NOT EXISTS idx_invoices_carrier ON freight_invoices(carrier_id);
CREATE INDEX IF NOT EXISTS idx_invoices_shipment ON freight_invoices(shipment_id);
CREATE INDEX IF NOT EXISTS idx_lines_invoice ON invoice_lines(invoice_id);
CREATE INDEX IF NOT EXISTS idx_exceptions_invoice ON audit_exceptions(invoice_id);
CREATE INDEX IF NOT EXISTS idx_credit_notes_exception ON credit_notes(exception_id);
"""
