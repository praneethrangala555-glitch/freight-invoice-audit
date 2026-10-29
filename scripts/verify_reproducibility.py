"""
Reproducibility Verification Script (Step 10)
Generates the synthetic dataset twice independently using the exact same fixed seed,
computes cryptographic SHA-256 hashes for all output files, and verifies 100%
byte-level reproducibility.
"""
import hashlib
import json
import argparse
from pathlib import Path
import shutil
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from freight_audit.generator.seed_generator import FreightDataGenerator
from freight_audit.generator.exporters import DatasetExporter

def get_dir_hashes(directory: Path) -> dict:
    hashes = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            sha256 = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha256.update(chunk)
            rel_path = str(path.relative_to(directory)).replace("\\", "/")
            hashes[rel_path] = {
                "size_bytes": path.stat().st_size,
                "sha256": sha256.hexdigest(),
            }
    return hashes

def verify_reproducibility(seed: int = 20261022, scale: str = "starter") -> bool:
    print("=" * 70)
    print("STEP 10: REPRODUCIBILITY VERIFICATION")
    print(f"Seed: {seed} | Scale: {scale}")
    print("=" * 70)

    presets = {
        "starter": (25, 500, 400, 100),
        "full": (100, 20000, 15000, 500),
    }
    if scale not in presets:
        raise ValueError(f"Unsupported scale {scale!r}; expected one of {tuple(presets)}.")
    config = presets[scale]

    dir1 = Path(tempfile.mkdtemp(prefix="freight_audit_run1_"))
    dir2 = Path(tempfile.mkdtemp(prefix="freight_audit_run2_"))

    try:
        # Pass 1
        print("[Pass 1/2] Generating dataset in Run 1 directory...")
        gen1 = FreightDataGenerator(seed=seed)
        bundle1 = gen1.generate(
            num_carriers=config[0], num_shipments=config[1],
            num_invoices=config[2], num_lanes=config[3],
        )
        exp1 = DatasetExporter(dir1)
        manifest1 = exp1.export_all(bundle1, populate_mysql=False)
        hashes1 = get_dir_hashes(dir1)
        print(f"          Run 1 exported {manifest1['total_rows']:,} rows across {len(hashes1)} files.")

        # Pass 2
        print("[Pass 2/2] Generating dataset in Run 2 directory...")
        gen2 = FreightDataGenerator(seed=seed)
        bundle2 = gen2.generate(
            num_carriers=config[0], num_shipments=config[1],
            num_invoices=config[2], num_lanes=config[3],
        )
        exp2 = DatasetExporter(dir2)
        manifest2 = exp2.export_all(bundle2, populate_mysql=False)
        hashes2 = get_dir_hashes(dir2)
        print(f"          Run 2 exported {manifest2['total_rows']:,} rows across {len(hashes2)} files.")

        print("\nComparing row counts and file checksums:")
        all_match = True
        mismatches = []

        if hashes1.keys() != hashes2.keys():
            all_match = False
            mismatches.append(
                f"File set mismatch: only in Run 1={sorted(hashes1.keys() - hashes2.keys())[:5]}, "
                f"only in Run 2={sorted(hashes2.keys() - hashes1.keys())[:5]}"
            )
        if manifest1["total_rows"] != manifest2["total_rows"]:
            all_match = False
            mismatches.append(f"Total rows mismatch: {manifest1['total_rows']} vs {manifest2['total_rows']}")

        for file_rel, meta1 in hashes1.items():
            if file_rel not in hashes2:
                all_match = False
                mismatches.append(f"File missing in Run 2: {file_rel}")
                continue

            meta2 = hashes2[file_rel]
            if meta1["sha256"] != meta2["sha256"]:
                all_match = False
                mismatches.append(f"Checksum mismatch on {file_rel}: {meta1['sha256']} != {meta2['sha256']}")
            else:
                print(f"  [OK] {file_rel:35s} SHA256: {meta1['sha256'][:16]}... MATCH")

        print("=" * 70)
        if all_match:
            print("REPRODUCIBILITY VERIFICATION: PASSED (100% IDENTICAL CHECKSUMS)")
            print("Every row count, ID, attribute, and file byte is strictly deterministic.")
        else:
            print("REPRODUCIBILITY VERIFICATION: FAILED")
            for m in mismatches:
                print(f"  - {m}")
        print("=" * 70)
        return all_match

    finally:
        shutil.rmtree(dir1, ignore_errors=True)
        shutil.rmtree(dir2, ignore_errors=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify reproducibility for a configured data scale.")
    parser.add_argument("--scale", choices=["starter", "full"], default="starter")
    parser.add_argument("--seed", type=int, default=20261022)
    args = parser.parse_args()
    success = verify_reproducibility(seed=args.seed, scale=args.scale)
    sys.exit(0 if success else 1)
