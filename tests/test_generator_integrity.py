"""
Unit Tests for Data Generator Integrity & Validation
"""
from freight_audit.generator.seed_generator import FreightDataGenerator
from freight_audit.evaluation.validator import RelationalValidator

def test_starter_generation_validation():
    generator = FreightDataGenerator(seed=20261022)
    bundle = generator.generate(
        num_carriers=15,
        num_shipments=300,
        num_invoices=250,
        num_lanes=50,
    )

    validator = RelationalValidator(bundle)
    result = validator.validate_all()

    assert result.passed is True
    assert result.checks_failed == 0
    assert result.checks_passed == result.checks_run

def test_ground_truth_separation():
    generator = FreightDataGenerator(seed=20261022)
    bundle = generator.generate(
        num_carriers=10,
        num_shipments=100,
        num_invoices=80,
        num_lanes=30,
    )

    # Check that ground truth contains records
    assert len(bundle.ground_truth.records) > 0

    # Ensure none of the invoice entities carry ground truth internal labels
    for inv in bundle.freight_invoices:
        inv_dict = inv.model_dump()
        assert "ground_truth" not in inv_dict
        assert "anomaly_category" not in inv_dict
