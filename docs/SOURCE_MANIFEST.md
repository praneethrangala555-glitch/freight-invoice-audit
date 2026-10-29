# Synthetic Data Source Manifest

## Provenance and lawful use

Every carrier, lane, rate, shipment, measurement, invoice, accessorial,
exception, and credit record in the starter and full datasets is generated
synthetically from the deterministic code in `freight_audit/generator/`. No
external freight dataset, carrier feed, customer information, or personal data
is used.

Carrier contact addresses use the reserved `.example` domain. Company names,
synthetic SCAC-like identifiers, rates, routes, and event records are fictional
test values; they must not be used as real carrier/contact data.

No public dataset is redistributed, so there is no external dataset URL,
version, retrieval date, or third-party license to attribute. The schema is
informed by common freight-invoice and load-tender concepts; it does not copy
external transactional records or published rate tables.

## Reproducible configuration

| Parameter                              |    Starter |       Full |
| -------------------------------------- | ---------: | ---------: |
| Seed                                   | `20261022` | `20261022` |
| Carriers                               |         25 |        100 |
| Lanes                                  |        100 |        500 |
| Rate cards, including expired versions |      1,500 |      6,000 |
| Shipments                              |        500 |     20,000 |
| Freight invoices                       |        400 |     15,000 |

The CLI accepts `--carriers`, `--lanes`, `--shipments`, and `--invoices`
overrides. The actual seed and generation configuration are written to each
`export_manifest.json`.

```powershell
python scripts\run_generator.py --scale starter --seed 20261022
python scripts\run_generator.py --scale full --seed 20261022
python scripts\verify_reproducibility.py --scale starter --seed 20261022
python scripts\verify_reproducibility.py --scale full --seed 20261022
```

By default, generation writes local CSV, JSON, SQLite, and MySQL SQL-dump
artifacts only. To also populate the configured live MySQL database, opt in
explicitly with `--populate-mysql`; do not use that option against a database
whose contents should be preserved.

The API and dashboard rebuild their deterministic baseline in memory and store
new invoices, current exception/credit state, and append-only workflow events in
SQLite under `.state/`. Set `FREIGHT_AUDIT_STATE_DB` to choose the API journal
location. Dashboard journals are isolated by scale and seed. This runtime
journal is separate from the generated export database.

## Ground-truth separation

Ground truth is exported only to `ground_truth.csv` and `ground_truth.json`,
outside the model input tables. Labels are derived from injected rules and
calculated outcomes. The validator verifies that labelled invoice/credit IDs
exist, decisions and amounts match their labels, and intentional unknown
shipment references have no resolved shipment FK.
