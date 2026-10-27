"""
Unit Tests for Freight Rating Engine
"""
from datetime import date
import pytest
from freight_audit.engine.rating import (
    RatingEngine,
    calculate_dim_weight,
    determine_weight_tier,
)
from freight_audit.models.entities import RateCard, Accessorial
from freight_audit.models.enums import ServiceLevel, WeightTier, AccessorialCode, RateCardStatus

@pytest.fixture
def sample_rate_card():
    return RateCard(
        rate_card_id="RATE-CAR-000001-2026-01",
        carrier_id="CAR-000001",
        lane_id="LANE-000001",
        service_level=ServiceLevel.STANDARD,
        effective_start_date=date(2026, 1, 1),
        effective_end_date=date(2026, 12, 31),
        base_min_charge=75.00,
        rate_tier_1_cwt=35.00,  # < 500 lbs
        rate_tier_2_cwt=30.00,  # 500 - 1999 lbs
        rate_tier_3_cwt=25.00,  # 2000 - 4999 lbs
        rate_tier_4_cwt=20.00,  # 5000 - 9999 lbs
        rate_tier_5_cwt=16.00,  # >= 10000 lbs
        dim_factor=139,
        fuel_surcharge_pct=0.20,
        status=RateCardStatus.ACTIVE,
    )

def test_dim_weight_calculation():
    # 48 x 40 x 48 inches = 92,160 in3 / 139 = 663.02 lbs
    dim_wt = calculate_dim_weight(48.0, 40.0, 48.0, 139)
    assert dim_wt == 663.02

def test_weight_tier_selection():
    tier1, field1 = determine_weight_tier(450.0)
    assert tier1 == WeightTier.TIER_1
    assert field1 == "rate_tier_1_cwt"

    tier2, field2 = determine_weight_tier(1200.0)
    assert tier2 == WeightTier.TIER_2
    assert field2 == "rate_tier_2_cwt"

    tier3, field3 = determine_weight_tier(3500.0)
    assert tier3 == WeightTier.TIER_3
    assert field3 == "rate_tier_3_cwt"

    tier5, field5 = determine_weight_tier(15000.0)
    assert tier5 == WeightTier.TIER_5
    assert field5 == "rate_tier_5_cwt"

def test_rating_under_min_charge(sample_rate_card):
    engine = RatingEngine([sample_rate_card])
    # 100 lbs at Tier 1 ($35/cwt) = $35.00 raw, should clamp to min charge $75.00
    res = engine.calculate_expected_charges(
        rate_card=sample_rate_card,
        actual_weight_lbs=100.0,
        dim_weight_lbs=80.0,
        authorized_accessorials=[],
    )
    assert res.base_charge == 75.00
    assert res.min_charge_applied is True
    assert res.fuel_surcharge_amount == 15.00  # 20% of 75.00
    assert res.total_expected_charge == 90.00

def test_rating_with_dim_weight_and_accessorials(sample_rate_card):
    engine = RatingEngine([sample_rate_card])
    # Scale wt: 500 lbs, Dim wt: 2200 lbs (dim weight governs: Tier 3 @ $25/cwt)
    # CWT = 22.00 * 25.00 = $550.00 base
    # Fuel: 20% of $550.00 = $110.00
    # Accessorials: Liftgate $75.00
    # Total = 550 + 110 + 75 = $735.00
    acc = Accessorial(
        accessorial_id="ACC-2026-000001",
        shipment_id="SHP-2026-000001",
        code=AccessorialCode.LIFTGATE,
        description="Liftgate Delivery",
        standard_fee=75.00,
        authorized=True,
    )
    res = engine.calculate_expected_charges(
        rate_card=sample_rate_card,
        actual_weight_lbs=500.0,
        dim_weight_lbs=2200.0,
        authorized_accessorials=[acc],
    )
    assert res.is_dim_weight_applied is True
    assert res.billable_weight_lbs == 2200.0
    assert res.applied_weight_tier == WeightTier.TIER_3
    assert res.base_charge == 550.00
    assert res.fuel_surcharge_amount == 110.00
    assert res.accessorials_amount == 75.00
    assert res.total_expected_charge == 735.00
