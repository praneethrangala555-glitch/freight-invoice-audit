# Freight Invoice Audit Engine — Data Dictionary

This document specifies the authoritative schema and validation rules for the 11 core entities in the Freight Invoice Audit System.

---

## 1. Carrier (`Carrier`)
Master record representing a contracted freight transportation service provider.

| Field Name | Type | Req / Opt | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `carrier_id` | String | Required | Matches `^CAR-\d{6}$` | N/A | **PK (Unique)** | Immutable; 6-digit zero-padded numeric suffix. |
| `name` | String | Required | 2–100 printable ASCII chars | N/A | Non-unique | Must not be empty; trimmed whitespace. |
| `scac` | String | Required | 2–4 uppercase letters `^[A-Z]{2,4}$` | N/A | Unique | Standard Carrier Alpha Code (NMFTA assigned). |
| `mode` | Enum | Required | `LTL`, `FTL`, `PARCEL`, `INTERMODAL` | N/A | Non-unique | Valid operational mode. |
| `contact_email` | String | Required | Valid RFC 5322 email string | N/A | Non-unique | Must contain `@` and valid TLD domain. |
| `payment_terms_days` | Integer | Required | `15`, `30`, `45`, `60`, `90` | Days | Non-unique | Range: 15 <= value <= 90. |
| `status` | Enum | Required | `ACTIVE`, `SUSPENDED`, `TERMINATED` | N/A | Non-unique | Only `ACTIVE` carriers are eligible for rating new shipments. |
| `created_at` | DateTime | Required | ISO 8601 UTC timestamp | UTC | Non-unique | Must not be in future; defaults to creation instant. |

---

## 2. Lane (`Lane`)
Master geographic corridor connecting an origin zone/terminal to a destination zone/terminal.

| Field Name | Type | Req / Opt | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `lane_id` | String | Required | Matches `^LANE-\d{6}$` | N/A | **PK (Unique)** | 6-digit zero-padded sequence. |
| `origin_city` | String | Required | Valid city name | N/A | Non-unique | Standard US freight hub (e.g. Chicago, Atlanta, Dallas). |
| `origin_state` | String | Required | Valid 2-letter US postal code | N/A | Non-unique | `^[A-Z]{2}$` valid US state. |
| `origin_zip_prefix` | String | Required | 3-digit numeric string `^\d{3}$` | N/A | Non-unique | First 3 digits of origin postal code. |
| `destination_city` | String | Required | Valid city name | N/A | Non-unique | Standard US freight hub. |
| `destination_state` | String | Required | Valid 2-letter US postal code | N/A | Non-unique | `^[A-Z]{2}$` valid US state. |
| `destination_zip_prefix`| String | Required | 3-digit numeric string `^\d{3}$` | N/A | Non-unique | First 3 digits of destination postal code. |
| `distance_miles` | Decimal | Required | Float > 0.0 | Statute Miles | Non-unique | Must be strictly positive; typical range 50.0 to 3200.0. |
| `standard_transit_days` | Integer | Required | 1 to 10 | Days | Non-unique | Positive integer: `ceil(distance_miles / 500)`. |

---

## 3. RateCard (`RateCard`)
Contracted pricing schedule between a Shipper and a Carrier for a designated lane and service level.

| Field Name | Type | Req / Opt | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `rate_card_id` | String | Required | Matches `^RATE-CAR-\d{6}-2026-\d{2}$` | N/A | **PK (Unique)** | Encodes Carrier ID and version/sequence. |
| `carrier_id` | String | Required | Existing `Carrier.carrier_id` | N/A | FK | Must reference a valid `ACTIVE` carrier. |
| `lane_id` | String | Required | Existing `Lane.lane_id` | N/A | FK | Must reference a valid active lane. |
| `service_level` | Enum | Required | `STANDARD`, `EXPEDITED`, `GUARANTEED`, `ECONOMY` | N/A | Non-unique | Contracted delivery service tier. |
| `effective_start_date`| Date | Required | `YYYY-MM-DD` | Date | Non-unique | Contract inception date. |
| `effective_end_date` | Date | Required | `YYYY-MM-DD` | Date | Non-unique | Must be strictly `>= effective_start_date`. |
| `base_min_charge` | Decimal | Required | >= 25.00 | USD | Non-unique | Floor charge for shipment regardless of weight. |
| `rate_tier_1_cwt` | Decimal | Required | > 0.00 | USD / cwt | Non-unique | Tier 1: Weight < 500 lbs ($/hundredweight). |
| `rate_tier_2_cwt` | Decimal | Required | > 0.00 | USD / cwt | Non-unique | Tier 2: 500 lbs <= Weight < 2,000 lbs. |
| `rate_tier_3_cwt` | Decimal | Required | > 0.00 | USD / cwt | Non-unique | Tier 3: 2,000 lbs <= Weight < 5,000 lbs. |
| `rate_tier_4_cwt` | Decimal | Required | > 0.00 | USD / cwt | Non-unique | Tier 4: 5,000 lbs <= Weight < 10,000 lbs. |
| `rate_tier_5_cwt` | Decimal | Required | > 0.00 | USD / cwt | Non-unique | Tier 5: Weight >= 10,000 lbs. Typically tier1 > tier2 > tier3 > tier4 > tier5. |
| `dim_factor` | Integer | Required | `139`, `166`, `250` | in³/lb | Non-unique | Volumetric divisor for dimensional weight calculation. |
| `fuel_surcharge_pct` | Decimal | Required | 0.05 to 0.45 (5% to 45%) | Percentage | Non-unique | Weekly or monthly contractual diesel fuel index. |
| `status` | Enum | Required | `ACTIVE`, `EXPIRED`, `SUPERSEDED` | N/A | Non-unique | Rate cards with end date < current audit date are `EXPIRED`. |

---

## 4. Shipment (`Shipment`)
Commercial transaction recording movement of goods from shipper origin to consignee destination.

| Field Name | Type | Req / Opt | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `shipment_id` | String | Required | Matches `^SHP-2026-\d{6}$` | N/A | **PK (Unique)** | 6-digit zero-padded sequence. |
| `carrier_id` | String | Required | Existing `Carrier.carrier_id` | N/A | FK | Assigned line-haul carrier. |
| `lane_id` | String | Required | Existing `Lane.lane_id` | N/A | FK | Physical shipping corridor. |
| `service_level` | Enum | Required | `STANDARD`, `EXPEDITED`, `GUARANTEED`, `ECONOMY` | N/A | Non-unique | Service level booked. |
| `status` | Enum | Required | `ORDERED`, `PICKED_UP`, `IN_TRANSIT`, `DELIVERED`, `CANCELLED` | N/A | Non-unique | Lifecycle state transition must follow order. |
| `ship_date` | Date | Required | `YYYY-MM-DD` | Date | Non-unique | Date cargo was tendered to carrier. |
| `delivery_date` | Date | Optional | `YYYY-MM-DD` | Date | Non-unique | Required if `DELIVERED`; must be `>= ship_date`. |
| `bol_number` | String | Required | `BOL-\d{8}` | N/A | Unique | Commercial Bill of Lading legal document ID. |
| `total_pieces` | Integer | Required | >= 1 | Pieces | Non-unique | Sum of handling units (pallets/cartons). |
| `total_actual_weight_lbs`| Decimal| Required | >= 1.0 | Pounds (lbs) | Non-unique | Sum of scale measurements across all pieces. |
| `total_dim_weight_lbs` | Decimal | Required | >= 1.0 | Pounds (lbs) | Non-unique | Sum of `(L*W*H)/dim_factor` across pieces. |
| `billable_weight_lbs` | Decimal | Required | >= 1.0 | Pounds (lbs) | Non-unique | Strictly derived: `max(total_actual_weight_lbs, total_dim_weight_lbs)`. |
| `expected_base_charge` | Decimal | Required | >= 0.00 | USD | Non-unique | Derived from contracted RateCard by lane & billable weight. |
| `expected_fuel_surcharge`| Decimal| Required | >= 0.00 | USD | Non-unique | Derived: `round(expected_base_charge * fuel_surcharge_pct, 2)`. |
| `expected_accessorials_charge`| Decimal| Required | >= 0.00 | USD | Non-unique | Sum of contracted rates for authorized accessorials. |
| `expected_total_charge` | Decimal | Required | >= 0.00 | USD | Non-unique | Strictly derived: base + fuel + accessorials. |
| `created_at` | DateTime | Required | ISO 8601 UTC timestamp | UTC | Non-unique | Defaults to record creation timestamp. |

---

## 5. ShipmentLeg (`ShipmentLeg`)
Discrete physical route segment or modal transfer supporting multi-stop or hub-and-spoke transit.

| Field Name | Type | Req / Opt | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `leg_id` | String | Required | Matches `^LEG-SHP-2026-\d{6}-\d{2}$` | N/A | **PK (Unique)** | Encodes shipment ID and 2-digit leg sequence. |
| `shipment_id` | String | Required | Existing `Shipment.shipment_id` | N/A | FK | Parent shipment reference. |
| `leg_sequence` | Integer | Required | >= 1 | Sequence | Non-unique | Monotonically increasing index starting at 1. |
| `origin_location` | String | Required | Terminal/city descriptor | N/A | Non-unique | E.g. "Chicago Crossdock", "Dallas Distribution Center". |
| `destination_location` | String | Required | Terminal/city descriptor | N/A | Non-unique | Next depot or final consignee. |
| `pickup_time` | DateTime | Required | ISO 8601 UTC timestamp | UTC | Non-unique | Leg dispatch time. |
| `delivery_time` | DateTime | Optional | ISO 8601 UTC timestamp | UTC | Non-unique | Must be strictly `>= pickup_time`. |
| `leg_status` | Enum | Required | `PENDING`, `IN_TRANSIT`, `COMPLETED` | N/A | Non-unique | State progression. |
| `distance_miles` | Decimal | Required | > 0.0 | Statute Miles | Non-unique | Segment distance. |

---

## 6. WeightMeasurement (`WeightMeasurement`)
Physical dimensional and scale weight record for individual cargo handling units (pallets/skids).

| Field Name | Type | Req / Opt | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `measurement_id` | String | Required | Matches `^WM-2026-\d{6}$` | N/A | **PK (Unique)** | 6-digit zero-padded sequence. |
| `shipment_id` | String | Required | Existing `Shipment.shipment_id` | N/A | FK | Parent shipment reference. |
| `piece_number` | Integer | Required | >= 1 | Index | Non-unique | 1 to `total_pieces`. |
| `length_in` | Decimal | Required | 1.0 to 120.0 | Inches | Non-unique | Cargo piece length. |
| `width_in` | Decimal | Required | 1.0 to 102.0 | Inches | Non-unique | Cargo piece width. |
| `height_in` | Decimal | Required | 1.0 to 110.0 | Inches | Non-unique | Cargo piece height. |
| `scale_weight_lbs` | Decimal | Required | 1.0 to 45,000.0 | Pounds (lbs) | Non-unique | Certified scale weight. |
| `dim_weight_lbs` | Decimal | Required | >= 0.1 | Pounds (lbs) | Non-unique | Derived: `round((length_in * width_in * height_in) / dim_factor, 2)`. |
| `measurement_type` | Enum | Required | `ORIGIN_SCALE`, `CARRIER_REWEIGH`, `AUDIT_INSPECTION` | N/A | Non-unique | Measurement audit source. |
| `measured_at` | DateTime | Required | ISO 8601 UTC timestamp | UTC | Non-unique | Timestamp of scan/weighing. |
| `scale_id` | String | Required | `SCALE-[A-Z0-9]{4,8}` | N/A | Non-unique | Calibrated NTEP scale certificate identifier. |

---

## 7. Accessorial (`Accessorial`)
Specialized supplementary freight services performed or billed outside basic line-haul transportation.

| Field Name | Type | Req / Opt | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `accessorial_id` | String | Required | Matches `^ACC-2026-\d{6}$` | N/A | **PK (Unique)** | 6-digit zero-padded sequence. |
| `shipment_id` | String | Required | Existing `Shipment.shipment_id` | N/A | FK | Parent shipment reference. |
| `code` | Enum | Required | `LIFTGATE`, `RESIDENTIAL`, `INSIDE_DELIVERY`, `DETENTION`, `RECONSIGNMENT`, `HAZMAT`, `NOTIFICATION`, `APPOINTMENT` | N/A | Non-unique | Standard industry NMFC accessorial charge codes. |
| `description` | String | Required | 5–100 characters | N/A | Non-unique | Clear text description of service performed. |
| `standard_fee` | Decimal | Required | 15.00 to 500.00 | USD | Non-unique | Contractual fixed or calculated fee for the service. |
| `authorized` | Boolean | Required | `True`, `False` | N/A | Non-unique | Whether the shipper pre-authorized the service on BOL. |
| `proof_document_id` | String | Optional | Document reference | N/A | Non-unique | Proof of delivery / delivery ticket attachment reference. |
| `created_at` | DateTime | Required | ISO 8601 UTC timestamp | UTC | Non-unique | Record timestamp. |

---

## 8. FreightInvoice (`FreightInvoice`)
Commercial billing statement presented by a Carrier to a Shipper for freight services rendered.

| Field Name | Type | Req / Opt | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `invoice_id` | String | Required | Matches `^FINV-2026-\d{6}$` | N/A | **PK (Unique)** | 6-digit zero-padded sequence. |
| `carrier_id` | String | Required | Existing `Carrier.carrier_id` | N/A | FK | Billed carrier entity. |
| `shipment_id` | String | Optional | Existing `Shipment.shipment_id` OR invalid ID in negative test cases | N/A | FK (nullable) | Referenced shipment. Foreign key violation flagged during audit. |
| `invoice_number` | String | Required | `INV-[A-Z0-9]{6,12}` | N/A | Non-unique | Carrier's internal invoice number. Duplicate check on `(carrier_id, invoice_number)`. |
| `invoice_date` | Date | Required | `YYYY-MM-DD` | Date | Non-unique | Date invoice was published. |
| `due_date` | Date | Required | `YYYY-MM-DD` | Date | Non-unique | Derived: `invoice_date + carrier.payment_terms_days`. |
| `currency` | String | Required | `USD` | N/A | Non-unique | Standard settlement currency. |
| `billed_base_charge` | Decimal | Required | >= 0.00 | USD | Non-unique | Sum of lines where `charge_type == 'BASE_FREIGHT'`. |
| `billed_fuel_surcharge`| Decimal| Required | >= 0.00 | USD | Non-unique | Sum of lines where `charge_type == 'FUEL_SURCHARGE'`. |
| `billed_accessorials_charge`| Decimal| Required | >= 0.00 | USD | Non-unique | Sum of lines where `charge_type == 'ACCESSORIAL'`. |
| `billed_total_amount` | Decimal | Required | >= 0.00 | USD | Non-unique | Arithmetic sum of all `InvoiceLine.billed_amount`. |
| `status` | Enum | Required | `PENDING_AUDIT`, `AUDITED_APPROVED`, `AUDITED_EXCEPTION`, `DISPUTED`, `PAID`, `REJECTED` | N/A | Non-unique | Invoice audit lifecycle state. |
| `audit_status` | Enum | Required | `CLEARED`, `DISCREPANCY_DETECTED`, `DUPLICATE_INVOICE`, `UNMATCHED_SHIPMENT` | N/A | Non-unique | Audit engine determination. |
| `audit_variance` | Decimal | Required | Any decimal | USD | Non-unique | `billed_total_amount - expected_total_charge`. Overcharge if > 0.00. |
| `created_at` | DateTime | Required | ISO 8601 UTC timestamp | UTC | Non-unique | System ingestion timestamp. |

---

## 9. InvoiceLine (`InvoiceLine`)
Itemized line-level charge component contributing to the total freight invoice amount.

| Field Name | Type | Req / Opt | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `line_id` | String | Required | Matches `^FLINE-FINV-2026-\d{6}-\d{2}$` | N/A | **PK (Unique)** | Encodes `invoice_id` and 2-digit line index. |
| `invoice_id` | String | Required | Existing `FreightInvoice.invoice_id` | N/A | FK | Parent freight invoice. |
| `line_number` | Integer | Required | >= 1 | Sequence | Non-unique | Monotonically increasing line item position. |
| `charge_type` | Enum | Required | `BASE_FREIGHT`, `FUEL_SURCHARGE`, `ACCESSORIAL`, `DISCOUNT`, `MISC_FEE` | N/A | Non-unique | Category of transportation billing element. |
| `description` | String | Required | 3–100 characters | N/A | Non-unique | Line description (e.g. "Base LTL Freight Tier 2", "Diesel Fuel Surcharge"). |
| `billed_rate` | Decimal | Required | >= 0.00 | USD or % | Non-unique | Applied rate per unit or rate multiplier. |
| `billed_units` | Decimal | Required | >= 0.00 | Count / CWT | Non-unique | Quantity billed (e.g. 14.5 CWT, or 1 flat service). |
| `billed_amount` | Decimal | Required | >= 0.00 | USD | Non-unique | Billed total for this specific line item. |
| `expected_amount` | Decimal | Required | >= 0.00 | USD | Non-unique | Deterministically calculated expected charge from contract. |
| `variance_amount` | Decimal | Required | Any decimal | USD | Non-unique | Derived: `billed_amount - expected_amount`. |
| `audit_decision` | Enum | Required | `MATCHED`, `OVERCHARGE`, `UNDERCHARGE`, `INVALID_LINE`, `DUPLICATE_LINE` | N/A | Non-unique | Line-level audit validation outcome. |

---

## 10. AuditException (`AuditException`)
Explicit dispute or compliance violation record generated when billed characteristics diverge from expected contractual terms.

| Field Name | Type | Req / Opt | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `exception_id` | String | Required | Matches `^FEX-2026-\d{6}$` | N/A | **PK (Unique)** | 6-digit zero-padded sequence. |
| `invoice_id` | String | Required | Existing `FreightInvoice.invoice_id` | N/A | FK | Invoiced subject to audit exception. |
| `line_id` | String | Optional | Existing `InvoiceLine.line_id` | N/A | FK (nullable) | Specific line item causing discrepancy (null if invoice-level error). |
| `exception_type` | Enum | Required | `UNKNOWN_SHIPMENT`, `RATE_CARD_EXPIRED`, `WEIGHT_TIER_MISAPPLIED`, `SURCHARGE_DUPLICATED`, `INVALID_ACCESSORIAL`, `DUPLICATE_INVOICE`, `BASE_RATE_MISMATCH`, `FUEL_SURCHARGE_MISMATCH`, `DELIVERY_DATE_MISMATCH`, `CREDIT_NOTE_EXCEEDS_EXCEPTION` | N/A | Non-unique | Strict taxonomy of freight billing audit exceptions. |
| `severity` | Enum | Required | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` | N/A | Non-unique | Risk rating based on variance magnitude or systemic compliance impact. |
| `expected_value` | String | Required | Non-empty string | N/A | Non-unique | Contractual benchmark value (e.g. "$45.00", "Tier 3", "2026-10-15"). |
| `billed_value` | String | Required | Non-empty string | N/A | Non-unique | Invoiced erroneous value (e.g. "$90.00", "Tier 1", "2025-11-01"). |
| `discrepancy_amount`| Decimal| Required | Any decimal | USD | Non-unique | Financial impact: `billed_amount - expected_amount`. |
| `status` | Enum | Required | `OPEN`, `UNDER_REVIEW`, `APPROVED_DISPUTE`, `REJECTED_DISPUTE`, `RESOLVED` | N/A | Non-unique | Workflow dispute lifecycle status. |
| `assigned_to` | String | Required | Valid actor role | N/A | Non-unique | E.g. "Logistics Analyst", "Operations Manager". |
| `resolution_notes` | String | Optional | Descriptive text | N/A | Non-unique | Documentation rationale explaining approval or rejection. |
| `created_at` | DateTime | Required | ISO 8601 UTC timestamp | UTC | Non-unique | Timestamp exception was raised. |
| `resolved_at` | DateTime | Optional | ISO 8601 UTC timestamp | UTC | Non-unique | Populated only when status is `APPROVED_DISPUTE`, `REJECTED_DISPUTE`, or `RESOLVED`. |

---

## 11. CreditNote (`CreditNote`)
Financial credit document issued by a carrier to offset and resolve approved audit exceptions and disputed overcharges.

| Field Name | Type | Req / Opt | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `credit_note_id` | String | Required | Matches `^CN-2026-\d{6}$` | N/A | **PK (Unique)** | 6-digit zero-padded sequence. |
| `carrier_id` | String | Required | Existing `Carrier.carrier_id` | N/A | FK | Carrier issuing the financial refund/credit. |
| `invoice_id` | String | Required | Existing `FreightInvoice.invoice_id` | N/A | FK | Invoiced offset by this credit note. |
| `exception_id` | String | Required | Existing `AuditException.exception_id` | N/A | FK | Disputed exception record being settled. |
| `credit_note_number`| String| Required | `CN-[A-Z0-9]{6,12}` | N/A | Unique | Carrier reference code. |
| `credit_amount` | Decimal | Required | > 0.00 | USD | Non-unique | Disbursed credit amount. |
| `original_exception_amount`| Decimal| Required | > 0.00 | USD | Non-unique | Exact value of `AuditException.discrepancy_amount`. |
| `status` | Enum | Required | `PENDING_CARRIER`, `APPLIED`, `DISPUTED`, `REJECTED` | N/A | Non-unique | Settlement state. |
| `issue_date` | Date | Required | `YYYY-MM-DD` | Date | Non-unique | Must be `>= AuditException.created_at`. |
| `reconciliation_status`| Enum| Required | `RECONCILED`, `OVERCREDITED`, `UNDERCREDITED` | N/A | Non-unique | Deterministic check: `RECONCILED` if `abs(credit_amount - original_exception_amount) < 0.01`; `OVERCREDITED` if `credit_amount > original_exception_amount`; else `UNDERCREDITED`. |
| `created_at` | DateTime | Required | ISO 8601 UTC timestamp | UTC | Non-unique | Record creation timestamp. |

---

## Cardinality & Relationship Matrix

| Primary Entity (1) | Related Entity (N) | Foreign Key | Cardinality | Optionality | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `Carrier` | `RateCard` | `RateCard.carrier_id` | 1 : N | Mandatory on child | Carrier publishes multiple contracted rate cards by lane/service. |
| `Lane` | `RateCard` | `RateCard.lane_id` | 1 : N | Mandatory on child | Lane has multiple carrier rate offerings. |
| `Carrier` | `Shipment` | `Shipment.carrier_id` | 1 : N | Mandatory on child | Carrier is tendered multiple shipments. |
| `Lane` | `Shipment` | `Shipment.lane_id` | 1 : N | Mandatory on child | Shipment traverses a defined lane. |
| `Shipment` | `ShipmentLeg` | `ShipmentLeg.shipment_id` | 1 : N | Mandatory on child | Multi-modal or intermediate transfer legs. |
| `Shipment` | `WeightMeasurement` | `WeightMeasurement.shipment_id` | 1 : N | Mandatory on child | Piece-level scale and dim weight records. |
| `Shipment` | `Accessorial` | `Accessorial.shipment_id` | 1 : N | Optional (0..N) | Supplementary services performed for the shipment. |
| `Carrier` | `FreightInvoice` | `FreightInvoice.carrier_id` | 1 : N | Mandatory on child | Carrier bills shipper via invoices. |
| `Shipment` | `FreightInvoice` | `FreightInvoice.shipment_id` | 1 : N | Optional (0..N) | Normal is 1:1; duplicate billing is 1:N; unknown shipment is 0:1. |
| `FreightInvoice` | `InvoiceLine` | `InvoiceLine.invoice_id` | 1 : N | Mandatory on child | Itemized charges summing to invoice total. |
| `FreightInvoice` | `AuditException` | `AuditException.invoice_id` | 1 : N | Optional (0..N) | Invoices with billing discrepancies spawn audit exceptions. |
| `InvoiceLine` | `AuditException` | `AuditException.line_id` | 1 : 1 | Optional (0..1) | Line-level discrepancy attribution. |
| `AuditException` | `CreditNote` | `CreditNote.exception_id` | 1 : 1 | Optional (0..1) | Approved disputes trigger compensating credit notes. |
| `Carrier` | `CreditNote` | `CreditNote.carrier_id` | 1 : N | Mandatory on child | Carrier issues credit note to settle debt. |
