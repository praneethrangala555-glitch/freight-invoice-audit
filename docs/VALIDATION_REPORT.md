# Validation and Verification Report

Generated with seed `20261022` after the rule and validation fixes.

## Validation coverage

The generator now runs 59 checks and stops before export if any fail. Both
published presets passed all 59 checks:

| Area | Enforced invariants |
|---|---|
| Keys and cardinality | Unique entity/event IDs, carrier SCACs, BOLs, credit-note numbers, invoice line numbers and shipment leg/piece sequence values |
| Relationships | All master/detail/event FKs resolve; shipment and invoice rate-card IDs are valid; invoice accessorial links belong to the billed shipment; credits match an approved exception and its invoice |
| Intentional negative records | Unknown shipment IDs use a null shipment FK plus a raw `shipment_reference`; only labelled unknown-shipment cases may use that path |
| Enums and lifecycle | Enum-typed values, allowed invoice transitions, event-to-final-state reconciliation, and resolution-event coverage for resolved exceptions |
| Dates | Shipment/delivery/leg ordering, invoice/delivery/due-date ordering, rate-card date ranges, and credit issuance ordering |
| Arithmetic | Shipment measurement sums and dimensional weight, contract-derived expected charges, invoice line/component totals, line/invoice variances, and credit reconciliation |
| Ground truth | Every invoice and credit note has a corresponding source row and a rule-derived expected decision; required edge-case labels match their records |

SQLite exports are created with foreign-key enforcement enabled and have **zero**
foreign-key violations. Unknown shipment input is preserved in the separate raw
reference field rather than as an invalid FK.

## Dataset sizes

| Entity/table | Starter | Full |
|---|---:|---:|
| Carriers | 25 | 100 |
| Lanes | 100 | 500 |
| Rate cards (active and expired) | 1,500 | 6,000 |
| Shipments | 500 | 20,000 |
| Shipment legs | 500 | 20,000 |
| Weight measurements | 1,220 | 50,088 |
| Accessorials | 162 | 7,045 |
| Freight invoices | 400 | 15,000 |
| Invoice lines | 958 | 36,319 |
| Audit exceptions | 120 | 4,500 |
| Credit notes | 16 | 600 |
| Invoice status events | 400 | 15,000 |
| Audit resolution events | 16 | 600 |
| **Total relational/event rows** | **5,917** | **175,752** |

## Ground-truth coverage

At full scale, invoice labels include 10,800 clean baselines and 600 examples
each of unknown shipment, expired rate card, weight-tier misapplication,
duplicate surcharge, rate variance with a credit workflow, duplicate billing,
and invalid accessorial. Credit-note labels separately include 300 correctly
reconciled notes and 300 over-credit cases. Ground truth is exported only to its
own CSV/JSON files.

## Synthetic evaluation metrics (full scale)

| Metric | Result |
|---|---:|
| Invoices | 15,000 |
| Clean invoices / exception invoices | 10,800 / 4,200 |
| Precision / recall / F1 / accuracy | 100% / 100% / 1.0000 / 100% |
| Billed spend | $12,954,220.82 |
| Expected spend from expected line amounts | $11,812,761.47 |
| Positive detected invoice variances | $1,141,459.35 |
| Credit notes issued / exact-reconciled | $57,339.62 / $23,470.20 |
| Correctly reconciled / over-credited credit notes | 300 / 300 |
| Over-credit amount | $16,934.71 |
| Reconciled-credit / positive-variance ratio | 2.06% |

These are synthetic rule-coverage metrics; they are not a claim about
performance on real-world carrier invoices. The ratio is explicitly defined as
exactly reconciled credit dollars divided by positive detected invoice
variances, not as the percentage of invoices recovered.

## Reproducibility

The command below generated the full preset twice, compared row counts and
SHA-256 hashes for all **31 exported artifacts** (including SQLite and the SQL
dump), and found no differences:

```powershell
python scripts\verify_reproducibility.py --scale full --seed 20261022
```

The starter preset is also covered by the test suite. Live MySQL population is
disabled by default during export and reproducibility checks; enabling it is an
explicit operator action.
