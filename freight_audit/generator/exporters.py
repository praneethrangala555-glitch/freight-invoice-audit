"""
Dataset Exporter & Reproducibility Verifier
Exports relational entities to CSV, JSON, SQL, and SQLite database formats.
Calculates SHA-256 cryptographic hashes for exact byte-level reproducibility testing.
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List

import pandas as pd
from freight_audit.generator.seed_generator import DatasetBundle
from freight_audit.models.schema import SQL_SCHEMA_DDL

def calculate_file_sha256(filepath: Path) -> str:
    """Calculate SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

class DatasetExporter:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_all(self, bundle: DatasetBundle) -> Dict[str, Any]:
        """
        Export all entities to CSV, JSON, and SQLite database.
        Returns manifest summary with row counts and SHA-256 checksums.
        """
        manifest: Dict[str, Any] = {
            "tables": {},
            "total_rows": 0,
            "seed": bundle.ground_truth.records[0].explanation if bundle.ground_truth.records else "",
        }

        # Entities to export
        tables: Dict[str, List[Any]] = {
            "carriers": bundle.carriers,
            "lanes": bundle.lanes,
            "rate_cards": bundle.rate_cards,
            "shipments": bundle.shipments,
            "shipment_legs": bundle.shipment_legs,
            "weight_measurements": bundle.weight_measurements,
            "accessorials": bundle.accessorials,
            "freight_invoices": bundle.freight_invoices,
            "invoice_lines": bundle.invoice_lines,
            "audit_exceptions": bundle.audit_exceptions,
            "credit_notes": bundle.credit_notes,
            "invoice_status_events": bundle.invoice_status_events,
            "audit_resolution_events": bundle.audit_resolution_events,
        }

        csv_dir = self.output_dir / "csv"
        json_dir = self.output_dir / "json"
        csv_dir.mkdir(parents=True, exist_ok=True)
        json_dir.mkdir(parents=True, exist_ok=True)

        # 1. Export each table to CSV & JSON
        for table_name, rows in tables.items():
            dict_rows = [r.model_dump(mode="json") if hasattr(r, "model_dump") else r.__dict__ for r in rows]
            manifest["total_rows"] += len(dict_rows)

            # CSV Export
            csv_path = csv_dir / f"{table_name}.csv"
            if dict_rows:
                keys = list(dict_rows[0].keys())
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=keys)
                    writer.writeheader()
                    writer.writerows(dict_rows)
            else:
                csv_path.touch()

            # JSON Export
            json_path = json_dir / f"{table_name}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(dict_rows, f, indent=2, default=str)

            manifest["tables"][table_name] = {
                "row_count": len(dict_rows),
                "csv_sha256": calculate_file_sha256(csv_path),
                "json_sha256": calculate_file_sha256(json_path),
            }

        # 2. Export Ground Truth Separately (Step 7 requirement: never leak into input tables)
        gt_csv_path = self.output_dir / "ground_truth.csv"
        gt_json_path = self.output_dir / "ground_truth.json"
        gt_dicts = bundle.ground_truth.to_dicts()

        if gt_dicts:
            gt_keys = list(gt_dicts[0].keys())
            with open(gt_csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=gt_keys)
                writer.writeheader()
                writer.writerows(gt_dicts)
        else:
            gt_csv_path.touch()

        with open(gt_json_path, "w", encoding="utf-8") as f:
            json.dump(gt_dicts, f, indent=2)

        manifest["ground_truth"] = {
            "record_count": len(gt_dicts),
            "csv_sha256": calculate_file_sha256(gt_csv_path),
            "json_sha256": calculate_file_sha256(gt_json_path),
        }

        # 3. Export to SQLite database with schema DDL
        db_path = self.output_dir / "freight_audit.db"
        if db_path.exists():
            db_path.unlink()

        conn = sqlite3.connect(str(db_path))
        conn.executescript(SQL_SCHEMA_DDL)

        for table_name, rows in tables.items():
            if rows:
                dict_rows = [r.model_dump(mode="json") if hasattr(r, "model_dump") else r.__dict__ for r in rows]
                df = pd.DataFrame(dict_rows)
                df.to_sql(table_name, conn, if_exists="append", index=False)

        conn.commit()
        conn.close()

        manifest["sqlite_db"] = {
            "filename": "freight_audit.db",
            "sha256": calculate_file_sha256(db_path),
        }

        # 4. Save manifest file
        manifest_path = self.output_dir / "export_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return manifest
