"""
Freight Invoice Audit Engine - MySQL Database Manager
Handles MySQL connection management, schema initialization, dataset export,
and interactive query utilities using SQLAlchemy and PyMySQL.
"""
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import urllib.parse

import pymysql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from freight_audit.generator.seed_generator import DatasetBundle
from freight_audit.models.schema import MYSQL_SCHEMA_DDL

logger = logging.getLogger(__name__)


def load_env_file(env_path: Path | None = None) -> None:
    """Load key-value pairs from .env file into os.environ if not already set."""
    if env_path is None:
        potential_paths = [
            Path(".env"),
            Path(__file__).resolve().parent.parent.parent / ".env",
        ]
        for p in potential_paths:
            if p.exists() and p.is_file():
                env_path = p
                break

    if env_path and env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except OSError as exc:
            logger.warning("Could not read .env file %s: %s", env_path, exc)


@dataclass
class MySQLConfig:
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = "freight_audit_db"

    @classmethod
    def from_env(cls) -> "MySQLConfig":
        load_env_file()
        return cls(
            host=os.getenv("MYSQL_HOST", "localhost"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            database=os.getenv("MYSQL_DATABASE", "freight_audit_db"),
        )

    def get_sqlalchemy_url(self, include_db: bool = True) -> str:
        safe_pass = urllib.parse.quote_plus(self.password)
        db_part = f"/{self.database}" if include_db else ""
        return f"mysql+pymysql://{self.user}:{safe_pass}@{self.host}:{self.port}{db_part}?charset=utf8mb4"


class MySQLManager:
    """Manages MySQL schema lifecycle, table ingestion, and database operations."""

    def __init__(self, config: MySQLConfig | None = None):
        self.config = config or MySQLConfig.from_env()

    def test_connection(self) -> tuple[bool, str]:
        """Test connection to the MySQL server."""
        try:
            conn = pymysql.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                charset="utf8mb4",
                connect_timeout=5,
            )
            with conn.cursor() as cursor:
                cursor.execute("SELECT VERSION();")
                version = cursor.fetchone()
            conn.close()
            return True, f"Successfully connected to MySQL {version[0]} at {self.config.host}:{self.config.port}"
        except pymysql.Error as exc:
            return False, f"Connection failed: {exc!s}"

    def create_database(self) -> bool:
        """Create the target database if it does not already exist."""
        conn = pymysql.connect(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            password=self.config.password,
            charset="utf8mb4",
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{self.config.database}` "
                    f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                )
            conn.commit()
            return True
        finally:
            conn.close()

    def get_engine(self) -> Engine:
        """Get SQLAlchemy Engine connected to the target database."""
        return create_engine(self.config.get_sqlalchemy_url(include_db=True), pool_pre_ping=True)

    def initialize_schema(self) -> None:
        """Run the DDL to drop/create tables in MySQL."""
        self.create_database()
        conn = pymysql.connect(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
            charset="utf8mb4",
            client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS,
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute(MYSQL_SCHEMA_DDL)
            conn.commit()
        finally:
            conn.close()

    def populate_from_bundle(self, bundle: DatasetBundle) -> dict[str, int]:
        """
        Populate the MySQL database with all records from a DatasetBundle
        in strict foreign-key dependency order.
        """
        import pandas as pd

        self.initialize_schema()
        engine = self.get_engine()

        table_order = [
            ("carriers", bundle.carriers),
            ("lanes", bundle.lanes),
            ("rate_cards", bundle.rate_cards),
            ("shipments", bundle.shipments),
            ("shipment_legs", bundle.shipment_legs),
            ("weight_measurements", bundle.weight_measurements),
            ("accessorials", bundle.accessorials),
            ("freight_invoices", bundle.freight_invoices),
            ("invoice_lines", bundle.invoice_lines),
            ("audit_exceptions", bundle.audit_exceptions),
            ("credit_notes", bundle.credit_notes),
            ("invoice_status_events", bundle.invoice_status_events),
            ("audit_resolution_events", bundle.audit_resolution_events),
        ]

        row_counts = {}
        with engine.connect() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
            conn.commit()

            for table_name, rows in table_order:
                if rows:
                    dict_rows = [
                        r.model_dump(mode="json") if hasattr(r, "model_dump") else r.__dict__
                        for r in rows
                    ]
                    df = pd.DataFrame(dict_rows)
                    df.to_sql(table_name, con=engine, if_exists="append", index=False, chunksize=1000)
                    row_counts[table_name] = len(dict_rows)
                else:
                    row_counts[table_name] = 0

            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
            conn.commit()

        return row_counts

    @staticmethod
    def generate_sql_dump_file(bundle: DatasetBundle, output_sql_path: Path) -> int:
        """
        Generate a complete, self-contained MySQL SQL dump file containing
        all DDL and INSERT statements ready for `mysql < dump.sql`.
        """
        output_sql_path = Path(output_sql_path)
        output_sql_path.parent.mkdir(parents=True, exist_ok=True)

        table_order = [
            ("carriers", bundle.carriers),
            ("lanes", bundle.lanes),
            ("rate_cards", bundle.rate_cards),
            ("shipments", bundle.shipments),
            ("shipment_legs", bundle.shipment_legs),
            ("weight_measurements", bundle.weight_measurements),
            ("accessorials", bundle.accessorials),
            ("freight_invoices", bundle.freight_invoices),
            ("invoice_lines", bundle.invoice_lines),
            ("audit_exceptions", bundle.audit_exceptions),
            ("credit_notes", bundle.credit_notes),
            ("invoice_status_events", bundle.invoice_status_events),
            ("audit_resolution_events", bundle.audit_resolution_events),
        ]

        total_inserted = 0
        with open(output_sql_path, "w", encoding="utf-8") as f:
            f.write("-- ========================================================\n")
            f.write("-- Freight Invoice Audit Engine - MySQL Complete Database Dump\n")
            f.write("-- ========================================================\n\n")
            f.write(MYSQL_SCHEMA_DDL)
            f.write("\n\n-- Data Ingestion (SET FOREIGN_KEY_CHECKS = 0 during bulk insert)\n")
            f.write("SET FOREIGN_KEY_CHECKS = 0;\n\n")

            for table_name, rows in table_order:
                if not rows:
                    continue
                dict_rows = [
                    r.model_dump(mode="json") if hasattr(r, "model_dump") else r.__dict__
                    for r in rows
                ]
                total_inserted += len(dict_rows)
                columns = list(dict_rows[0].keys())
                col_names = ", ".join(f"`{c}`" for c in columns)

                # Write in batches of 250 rows for performant MySQL bulk inserts
                batch_size = 250
                for i in range(0, len(dict_rows), batch_size):
                    batch = dict_rows[i : i + batch_size]
                    values_list = []
                    for row in batch:
                        val_strs = []
                        for col in columns:
                            val = row.get(col)
                            if val is None:
                                val_strs.append("NULL")
                            elif isinstance(val, bool):
                                val_strs.append("1" if val else "0")
                            elif isinstance(val, (int, float)):
                                val_strs.append(str(val))
                            else:
                                escaped = str(val).replace("\\", "\\\\").replace("'", "\\'")
                                val_strs.append(f"'{escaped}'")
                        values_list.append(f"({', '.join(val_strs)})")
                    f.write(f"INSERT INTO `{table_name}` ({col_names}) VALUES\n  " + ",\n  ".join(values_list) + ";\n")
                f.write("\n")

            f.write("SET FOREIGN_KEY_CHECKS = 1;\n")
            f.write("-- Ingestion complete.\n")

        return total_inserted
