"""
Freight Invoice Audit Engine - MySQL Ingestion CLI
Loads generated synthetic freight audit datasets directly into a MySQL database instance.
"""
import argparse
import os
from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from freight_audit.database.mysql_manager import MySQLManager, MySQLConfig, load_env_file
from freight_audit.generator.seed_generator import FreightDataGenerator

def main():
    load_env_file()
    parser = argparse.ArgumentParser(description="Ingest Freight Audit Dataset into MySQL")
    parser.add_argument("--scale", choices=["starter", "full"], default="starter", help="Dataset scale")
    parser.add_argument("--seed", type=int, default=20261022, help="Random seed")
    parser.add_argument("--host", default=os.getenv("MYSQL_HOST", "localhost"), help="MySQL Host")
    parser.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")), help="MySQL Port")
    parser.add_argument("--user", default=os.getenv("MYSQL_USER", "root"), help="MySQL Username")
    parser.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""), help="MySQL Password")
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "freight_audit_db"), help="MySQL Database Name")
    parser.add_argument("--sql-file", type=str, default=None, help="Import from existing .sql dump file instead of generating")

    args = parser.parse_args()

    config = MySQLConfig(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
    )

    manager = MySQLManager(config)

    print("=" * 70)
    print("FREIGHT INVOICE AUDIT - MYSQL INGESTION")
    print(f"Target: {config.user}@{config.host}:{config.port}/{config.database}")
    print("=" * 70)

    # 1. Test Connection
    print("\n[1/3] Testing MySQL connection...")
    success, msg = manager.test_connection()
    if not success:
        print(f"Error: {msg}")
        print("\nPlease check your credentials or run with flags:")
        print(f"  python scripts/load_to_mysql.py --user {config.user} --password <your_pwd> --database {config.database}")
        print(f"\nAlternatively, you can manually import the generated SQL dump:")
        dump_path = ROOT_DIR / "data" / args.scale / "freight_audit_mysql.sql"
        print(f"  mysql -u {config.user} -p {config.database} < {dump_path}")
        sys.exit(1)

    print(f"  {msg}")

    # 2. Ingest
    print(f"\n[2/3] Generating & Preparing '{args.scale}' dataset...")
    gen = FreightDataGenerator(seed=args.seed)
    if args.scale == "full":
        bundle = gen.generate(num_carriers=100, num_shipments=20000, num_invoices=15000, num_lanes=500)
    else:
        bundle = gen.generate(num_carriers=25, num_shipments=500, num_invoices=400, num_lanes=100)

    print("\n[3/3] Creating schema & streaming records into MySQL...")
    start_t = time.time()
    counts = manager.populate_from_bundle(bundle)
    elapsed = time.time() - start_t

    total_rows = sum(counts.values())
    print("\n" + "=" * 70)
    print(f"INGESTION COMPLETE in {elapsed:.2f} seconds!")
    print(f"Total Rows Ingested: {total_rows:,}")
    print("-" * 70)
    for tbl, cnt in counts.items():
        print(f"  {tbl:26}: {cnt:>8,} rows")
    print("=" * 70)

if __name__ == "__main__":
    main()
