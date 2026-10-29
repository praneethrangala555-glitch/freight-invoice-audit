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
    rate_card_id VARCHAR(40),
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
    FOREIGN KEY (lane_id) REFERENCES lanes(lane_id),
    FOREIGN KEY (rate_card_id) REFERENCES rate_cards(rate_card_id)
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
    shipment_reference VARCHAR(30),
    rate_card_id VARCHAR(40),
    invoice_number VARCHAR(30) NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    billed_delivery_date DATE,
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
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id),
    FOREIGN KEY (rate_card_id) REFERENCES rate_cards(rate_card_id)
);

-- 9. Invoice Lines
CREATE TABLE IF NOT EXISTS invoice_lines (
    line_id VARCHAR(25) PRIMARY KEY,
    invoice_id VARCHAR(16) NOT NULL,
    accessorial_id VARCHAR(15),
    line_number INTEGER NOT NULL,
    charge_type VARCHAR(30) NOT NULL,
    description VARCHAR(100) NOT NULL,
    billed_rate REAL NOT NULL,
    billed_units REAL NOT NULL,
    billed_amount REAL NOT NULL,
    expected_amount REAL NOT NULL DEFAULT 0.0,
    variance_amount REAL NOT NULL DEFAULT 0.0,
    audit_decision VARCHAR(30) NOT NULL DEFAULT 'MATCHED',
    FOREIGN KEY (invoice_id) REFERENCES freight_invoices(invoice_id),
    FOREIGN KEY (accessorial_id) REFERENCES accessorials(accessorial_id)
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

# MySQL Specific DDL (InnoDB, Foreign Key Cascades, Datetime and Double Precisions)
MYSQL_SCHEMA_DDL = """
-- Freight Invoice Audit Engine - MySQL Relational DDL
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS audit_resolution_events;
DROP TABLE IF EXISTS invoice_status_events;
DROP TABLE IF EXISTS credit_notes;
DROP TABLE IF EXISTS audit_exceptions;
DROP TABLE IF EXISTS invoice_lines;
DROP TABLE IF EXISTS freight_invoices;
DROP TABLE IF EXISTS accessorials;
DROP TABLE IF EXISTS weight_measurements;
DROP TABLE IF EXISTS shipment_legs;
DROP TABLE IF EXISTS shipments;
DROP TABLE IF EXISTS rate_cards;
DROP TABLE IF EXISTS lanes;
DROP TABLE IF EXISTS carriers;
SET FOREIGN_KEY_CHECKS = 1;

-- 1. Carrier Master
CREATE TABLE IF NOT EXISTS carriers (
    carrier_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    scac VARCHAR(10) NOT NULL UNIQUE,
    mode VARCHAR(30) NOT NULL,
    contact_email VARCHAR(100) NOT NULL,
    payment_terms_days INT NOT NULL DEFAULT 30,
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Lane Master
CREATE TABLE IF NOT EXISTS lanes (
    lane_id VARCHAR(20) PRIMARY KEY,
    origin_city VARCHAR(50) NOT NULL,
    origin_state VARCHAR(10) NOT NULL,
    origin_zip_prefix VARCHAR(10) NOT NULL,
    destination_city VARCHAR(50) NOT NULL,
    destination_state VARCHAR(10) NOT NULL,
    destination_zip_prefix VARCHAR(10) NOT NULL,
    distance_miles DOUBLE NOT NULL,
    standard_transit_days INT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. RateCard Contract
CREATE TABLE IF NOT EXISTS rate_cards (
    rate_card_id VARCHAR(40) PRIMARY KEY,
    carrier_id VARCHAR(20) NOT NULL,
    lane_id VARCHAR(20) NOT NULL,
    service_level VARCHAR(30) NOT NULL,
    effective_start_date DATE NOT NULL,
    effective_end_date DATE NOT NULL,
    base_min_charge DOUBLE NOT NULL,
    rate_tier_1_cwt DOUBLE NOT NULL,
    rate_tier_2_cwt DOUBLE NOT NULL,
    rate_tier_3_cwt DOUBLE NOT NULL,
    rate_tier_4_cwt DOUBLE NOT NULL,
    rate_tier_5_cwt DOUBLE NOT NULL,
    dim_factor INT NOT NULL DEFAULT 139,
    fuel_surcharge_pct DOUBLE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    INDEX idx_rc_carrier (carrier_id),
    INDEX idx_rc_lane (lane_id),
    INDEX idx_rc_lookup (carrier_id, lane_id, service_level, status),
    CONSTRAINT fk_rc_carrier FOREIGN KEY (carrier_id) REFERENCES carriers(carrier_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_rc_lane FOREIGN KEY (lane_id) REFERENCES lanes(lane_id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. Shipment Transaction
CREATE TABLE IF NOT EXISTS shipments (
    shipment_id VARCHAR(30) PRIMARY KEY,
    carrier_id VARCHAR(20) NOT NULL,
    lane_id VARCHAR(20) NOT NULL,
    rate_card_id VARCHAR(40),
    service_level VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL,
    ship_date DATE NOT NULL,
    delivery_date DATE,
    bol_number VARCHAR(30) NOT NULL UNIQUE,
    total_pieces INT NOT NULL,
    total_actual_weight_lbs DOUBLE NOT NULL,
    total_dim_weight_lbs DOUBLE NOT NULL,
    billable_weight_lbs DOUBLE NOT NULL,
    expected_base_charge DOUBLE NOT NULL,
    expected_fuel_surcharge DOUBLE NOT NULL,
    expected_accessorials_charge DOUBLE NOT NULL,
    expected_total_charge DOUBLE NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_shp_carrier (carrier_id),
    INDEX idx_shp_lane (lane_id),
    CONSTRAINT fk_shp_carrier FOREIGN KEY (carrier_id) REFERENCES carriers(carrier_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_shp_lane FOREIGN KEY (lane_id) REFERENCES lanes(lane_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_shp_rate_card FOREIGN KEY (rate_card_id) REFERENCES rate_cards(rate_card_id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. Shipment Legs
CREATE TABLE IF NOT EXISTS shipment_legs (
    leg_id VARCHAR(30) PRIMARY KEY,
    shipment_id VARCHAR(30) NOT NULL,
    leg_sequence INT NOT NULL,
    origin_location VARCHAR(100) NOT NULL,
    destination_location VARCHAR(100) NOT NULL,
    pickup_time DATETIME NOT NULL,
    delivery_time DATETIME,
    leg_status VARCHAR(30) NOT NULL,
    distance_miles DOUBLE NOT NULL,
    INDEX idx_leg_shipment (shipment_id),
    CONSTRAINT fk_leg_shipment FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. Weight Measurements
CREATE TABLE IF NOT EXISTS weight_measurements (
    measurement_id VARCHAR(30) PRIMARY KEY,
    shipment_id VARCHAR(30) NOT NULL,
    piece_number INT NOT NULL,
    length_in DOUBLE NOT NULL,
    width_in DOUBLE NOT NULL,
    height_in DOUBLE NOT NULL,
    scale_weight_lbs DOUBLE NOT NULL,
    dim_weight_lbs DOUBLE NOT NULL,
    measurement_type VARCHAR(30) NOT NULL,
    measured_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    scale_id VARCHAR(30) NOT NULL,
    INDEX idx_wm_shipment (shipment_id),
    CONSTRAINT fk_wm_shipment FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. Accessorial Services
CREATE TABLE IF NOT EXISTS accessorials (
    accessorial_id VARCHAR(30) PRIMARY KEY,
    shipment_id VARCHAR(30) NOT NULL,
    code VARCHAR(40) NOT NULL,
    description VARCHAR(100) NOT NULL,
    standard_fee DOUBLE NOT NULL,
    authorized BOOLEAN NOT NULL DEFAULT 1,
    proof_document_id VARCHAR(50),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_acc_shipment (shipment_id),
    CONSTRAINT fk_acc_shipment FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. Freight Invoices
CREATE TABLE IF NOT EXISTS freight_invoices (
    invoice_id VARCHAR(30) PRIMARY KEY,
    carrier_id VARCHAR(20) NOT NULL,
    shipment_id VARCHAR(30),
    shipment_reference VARCHAR(40),
    rate_card_id VARCHAR(40),
    invoice_number VARCHAR(40) NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    billed_delivery_date DATE,
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    billed_base_charge DOUBLE NOT NULL DEFAULT 0.0,
    billed_fuel_surcharge DOUBLE NOT NULL DEFAULT 0.0,
    billed_accessorials_charge DOUBLE NOT NULL DEFAULT 0.0,
    billed_total_amount DOUBLE NOT NULL DEFAULT 0.0,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING_AUDIT',
    audit_status VARCHAR(30) NOT NULL DEFAULT 'CLEARED',
    audit_variance DOUBLE NOT NULL DEFAULT 0.0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_inv_carrier (carrier_id),
    INDEX idx_inv_shipment (shipment_id),
    CONSTRAINT fk_inv_carrier FOREIGN KEY (carrier_id) REFERENCES carriers(carrier_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_inv_shipment FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_inv_rate_card FOREIGN KEY (rate_card_id) REFERENCES rate_cards(rate_card_id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9. Invoice Lines
CREATE TABLE IF NOT EXISTS invoice_lines (
    line_id VARCHAR(40) PRIMARY KEY,
    invoice_id VARCHAR(30) NOT NULL,
    accessorial_id VARCHAR(30),
    line_number INT NOT NULL,
    charge_type VARCHAR(40) NOT NULL,
    description VARCHAR(100) NOT NULL,
    billed_rate DOUBLE NOT NULL,
    billed_units DOUBLE NOT NULL,
    billed_amount DOUBLE NOT NULL,
    expected_amount DOUBLE NOT NULL DEFAULT 0.0,
    variance_amount DOUBLE NOT NULL DEFAULT 0.0,
    audit_decision VARCHAR(30) NOT NULL DEFAULT 'MATCHED',
    INDEX idx_line_invoice (invoice_id),
    CONSTRAINT fk_line_invoice FOREIGN KEY (invoice_id) REFERENCES freight_invoices(invoice_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_line_accessorial FOREIGN KEY (accessorial_id) REFERENCES accessorials(accessorial_id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 10. Audit Exceptions
CREATE TABLE IF NOT EXISTS audit_exceptions (
    exception_id VARCHAR(30) PRIMARY KEY,
    invoice_id VARCHAR(30) NOT NULL,
    line_id VARCHAR(40),
    exception_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    expected_value TEXT NOT NULL,
    billed_value TEXT NOT NULL,
    discrepancy_amount DOUBLE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'OPEN',
    assigned_to VARCHAR(50) NOT NULL,
    resolution_notes TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,
    INDEX idx_ex_invoice (invoice_id),
    INDEX idx_ex_line (line_id),
    CONSTRAINT fk_ex_invoice FOREIGN KEY (invoice_id) REFERENCES freight_invoices(invoice_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 11. Credit Notes
CREATE TABLE IF NOT EXISTS credit_notes (
    credit_note_id VARCHAR(30) PRIMARY KEY,
    carrier_id VARCHAR(20) NOT NULL,
    invoice_id VARCHAR(30) NOT NULL,
    exception_id VARCHAR(30) NOT NULL,
    credit_note_number VARCHAR(40) NOT NULL,
    credit_amount DOUBLE NOT NULL,
    original_exception_amount DOUBLE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING_CARRIER',
    issue_date DATE NOT NULL,
    reconciliation_status VARCHAR(30) NOT NULL DEFAULT 'RECONCILED',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_cn_carrier (carrier_id),
    INDEX idx_cn_invoice (invoice_id),
    INDEX idx_cn_exception (exception_id),
    CONSTRAINT fk_cn_carrier FOREIGN KEY (carrier_id) REFERENCES carriers(carrier_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_cn_invoice FOREIGN KEY (invoice_id) REFERENCES freight_invoices(invoice_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_cn_exception FOREIGN KEY (exception_id) REFERENCES audit_exceptions(exception_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 12. State & Audit Event Records
CREATE TABLE IF NOT EXISTS invoice_status_events (
    event_id VARCHAR(50) PRIMARY KEY,
    invoice_id VARCHAR(30) NOT NULL,
    from_status VARCHAR(30) NOT NULL,
    to_status VARCHAR(30) NOT NULL,
    changed_by VARCHAR(50) NOT NULL,
    reason TEXT NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_evt_inv (invoice_id),
    CONSTRAINT fk_evt_invoice FOREIGN KEY (invoice_id) REFERENCES freight_invoices(invoice_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS audit_resolution_events (
    event_id VARCHAR(50) PRIMARY KEY,
    exception_id VARCHAR(30) NOT NULL,
    from_status VARCHAR(30) NOT NULL,
    to_status VARCHAR(30) NOT NULL,
    decided_by VARCHAR(50) NOT NULL,
    decision_reason TEXT NOT NULL,
    approved_amount DOUBLE NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_evt_ex (exception_id),
    CONSTRAINT fk_evt_exception FOREIGN KEY (exception_id) REFERENCES audit_exceptions(exception_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""
