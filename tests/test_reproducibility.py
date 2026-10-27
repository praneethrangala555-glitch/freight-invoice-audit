"""
Unit Test for Fixed-Seed Reproducibility (Step 10)
"""
from scripts.verify_reproducibility import verify_reproducibility

def test_fixed_seed_reproducibility():
    assert verify_reproducibility(seed=20261022, scale="starter") is True
