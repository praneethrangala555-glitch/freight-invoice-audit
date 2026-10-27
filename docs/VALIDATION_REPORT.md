# Freight Invoice Audit Engine — Validation & Verification Report

This report summarizes the comprehensive automated data integrity, referential consistency, arithmetic reconciliation, and reproducibility verification executed across both **Starter** and **Full Scale** datasets.

---

## 1. Automated Validation Check Matrix (28/28 Passed)

| Category | Check Name | Target Entities | Rule / Invariant | Status |
| :--- | :--- | :--- | :--- | :--- |
| **PK Uniqueness** | `PK Uniqueness (carriers)` | `Carrier` | Zero duplicate IDs in `carrier_id` | **PASSED** |
| **PK Uniqueness** | `PK Uniqueness (lanes)` | `Lane` | Zero duplicate IDs in `lane_id` | **PASSED** |
| **PK Uniqueness** | `PK Uniqueness (rate_cards)` | `RateCard` | Zero duplicate IDs in `rate_card_id` | **PASSED** |
| **PK Uniqueness** | `PK Uniqueness (shipments)` | `Shipment` | Zero duplicate IDs in `shipment_id` | **PASSED** |
| **PK Uniqueness** | `PK Uniqueness (shipment_legs)` | `ShipmentLeg` | Zero duplicate IDs in `leg_id` | **PASSED** |
| **PK Uniqueness** | `PK Uniqueness (weight_measurements)` | `WeightMeasurement` | Zero duplicate IDs in `measurement_id` | **PASSED** |
| **PK Uniqueness** | `PK Uniqueness (accessorials)` | `Accessorial` | Zero duplicate IDs in `accessorial_id` | **PASSED** |
| **PK Uniqueness** | `PK Uniqueness (freight_invoices)` | `FreightInvoice` | Zero duplicate IDs in `invoice_id` | **PASSED** |
| **PK Uniqueness** | `PK Uniqueness (invoice_lines)` | `InvoiceLine` | Zero duplicate IDs in `line_id` | **PASSED** |
| **PK Uniqueness** | `PK Uniqueness (audit_exceptions)` | `AuditException` | Zero duplicate IDs in `exception_id` | **PASSED** |
| **PK Uniqueness** | `PK Uniqueness (credit_notes)` | `CreditNote` | Zero duplicate IDs in `credit_note_id` | **PASSED** |
| **FK Integrity** | `FK RateCard -> Carrier` | `RateCard` -> `Carrier` | Every `carrier_id` references an active Carrier | **PASSED** |
| **FK Integrity** | `FK RateCard -> Lane` | `RateCard` -> `Lane` | Every `lane_id` references an existing Lane | **PASSED** |
| **FK Integrity** | `FK Shipment -> Carrier` | `Shipment` -> `Carrier` | Every `carrier_id` references an existing Carrier | **PASSED** |
| **FK Integrity** | `FK Shipment -> Lane` | `Shipment` -> `Lane` | Every `lane_id` references an existing Lane | **PASSED** |
| **FK Integrity** | `FK ShipmentLeg -> Shipment`| `ShipmentLeg` -> `Shipment` | Every `shipment_id` references an existing Shipment | **PASSED** |
| **FK Integrity** | `FK WeightMeasurement -> Shipment` | `WeightMeasurement` -> `Shipment` | Every `shipment_id` references an existing Shipment | **PASSED** |
| **FK Integrity** | `FK Accessorial -> Shipment`| `Accessorial` -> `Shipment` | Every `shipment_id` references an existing Shipment | **PASSED** |
| **FK Integrity** | `FK FreightInvoice -> Carrier` | `FreightInvoice` -> `Carrier`| Every `carrier_id` references an existing Carrier | **PASSED** |
| **FK Integrity** | `FK InvoiceLine -> FreightInvoice` | `InvoiceLine` -> `FreightInvoice` | Every `invoice_id` references a parent invoice | **PASSED** |
| **FK Integrity** | `FK CreditNote -> AuditException` | `CreditNote` -> `AuditException` | Every `exception_id` references a valid exception | **PASSED** |
| **Chronology** | `Shipment Date <= Delivery Date` | `Shipment` | `ship_date <= delivery_date` | **PASSED** |
| **Chronology** | `RateCard Start <= End` | `RateCard` | `effective_start_date <= effective_end_date` | **PASSED** |
| **Chronology** | `Invoice Date <= Due Date` | `FreightInvoice` | `invoice_date <= due_date` | **PASSED** |
| **Arithmetic** | `Invoice Total == Sum(Lines)` | `FreightInvoice`, `InvoiceLine` | `billed_total_amount == sum(lines.billed_amount)` | **PASSED** |
| **Arithmetic** | `Billable Weight == Max(Actual, Dim)` | `Shipment` | `billable_weight_lbs == max(actual_wt, dim_wt)` | **PASSED** |
| **Arithmetic** | `Expected Total == Base + FSC + Acc` | `Shipment` | `expected_total == base + fuel + accessorials` | **PASSED** |
| **Integrity** | `No Unintended Duplicate Invoices` | `FreightInvoice` | Duplicate invoice numbers only exist where labeled | **PASSED** |

---

## 2. Scale Volume Summary

### Starter Preset
- **Carriers:** 25
- **Lanes:** 100
- **Shipments:** 500
- **Freight Invoices:** 400
- **Total Relational Rows:** 5,070
- **Generation Time:** 0.06 seconds
- **Validation Time:** 0.01 seconds

### Full Scale (Target Volume)
- **Carriers:** 100
- **Lanes:** 500
- **Shipments:** 20,000
- **Freight Invoices:** 15,000
- **Handling Units (Weight Measurements):** ~50,000
- **Invoice Line Items:** ~45,000
- **Total Relational Rows:** 168,808
- **Generation Time:** 2.02 seconds
- **Validation Time:** 0.24 seconds

---

## 3. Step 10: Fixed-Seed Reproducibility Verification

To satisfy Step 10:
> *"Regenerate twice with the same seed and compare row counts/checksums to demonstrate reproducibility."*

The test suite executes independent generation passes in isolated temporary directories with seed `20261022` and computes cryptographic SHA-256 hashes of every exported artifact.

```
[Pass 1/2] Generating dataset in Run 1 directory...
          Run 1 exported 5,070 rows across 29 files.
[Pass 2/2] Generating dataset in Run 2 directory...
          Run 2 exported 5,070 rows across 29 files.

Comparing row counts and file checksums:
  [OK] csv/accessorials.csv                SHA256: 7b61cb3cf4d3d476... MATCH
  [OK] csv/audit_exceptions.csv            SHA256: 9170388c9d3e9d08... MATCH
  [OK] csv/audit_resolution_events.csv     SHA256: 76fda91209ded5d6... MATCH
  [OK] csv/carriers.csv                    SHA256: 83e45b975f235d21... MATCH
  [OK] csv/credit_notes.csv                SHA256: e78ea6ef0ecf2dcc... MATCH
  [OK] csv/freight_invoices.csv            SHA256: 64f85361c3208bb5... MATCH
  [OK] csv/invoice_lines.csv               SHA256: ee9815dc69d82aec... MATCH
  [OK] csv/invoice_status_events.csv       SHA256: 6e4062c6e36d7ab7... MATCH
  [OK] csv/lanes.csv                       SHA256: c34f812e8d9ab542... MATCH
  [OK] csv/rate_cards.csv                  SHA256: 174c0c19fb0f5709... MATCH
  [OK] csv/shipment_legs.csv               SHA256: 30d9d91082546de7... MATCH
  [OK] csv/shipments.csv                   SHA256: 9cc09a0bcadd37ff... MATCH
  [OK] csv/weight_measurements.csv         SHA256: 56b92f2b74a049eb... MATCH
  [OK] export_manifest.json                SHA256: c35088eb4c83bd5f... MATCH
  [OK] ground_truth.csv                    SHA256: c477421596e37617... MATCH
  [OK] ground_truth.json                   SHA256: 9b423c3decbb37c2... MATCH
  [OK] json/accessorials.json              SHA256: 681fa080595f843e... MATCH
  [OK] json/audit_exceptions.json          SHA256: 193f164884473156... MATCH
  [OK] json/audit_resolution_events.json   SHA256: d40ccd2f672aa842... MATCH
  [OK] json/carriers.json                  SHA256: 5d2555f4ee0cd104... MATCH
  [OK] json/credit_notes.json              SHA256: 0d56ec4b119c85c6... MATCH
  [OK] json/freight_invoices.json          SHA256: fed7b8dfd5dcf887... MATCH
  [OK] json/invoice_lines.json             SHA256: c2142ac548144a7d... MATCH
  [OK] json/invoice_status_events.json     SHA256: 326b7550a453998d... MATCH
  [OK] json/lanes.json                     SHA256: 2cd1b0a158594b96... MATCH
  [OK] json/rate_cards.json                SHA256: 3d84ea3ca414bdd3... MATCH
  [OK] json/shipment_legs.json             SHA256: 565c9e370a340312... MATCH
  [OK] json/shipments.json                 SHA256: 9d080c538c4462cd... MATCH
  [OK] json/weight_measurements.json       SHA256: e78d88384c315cd5... MATCH
======================================================================
REPRODUCIBILITY VERIFICATION: PASSED (100% IDENTICAL CHECKSUMS)
```

**Result:** Every byte, ID, counter, timestamp, and numeric charge is 100% reproducible.
