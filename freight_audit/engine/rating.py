"""
Freight Rating Engine
Deterministic calculation of expected freight charges based on contracted rate cards,
actual vs dimensional weight, weight tiers, fuel surcharges, and accessorial fees.
"""
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple
from freight_audit.models.entities import RateCard, Accessorial
from freight_audit.models.enums import RateCardStatus, WeightTier, ServiceLevel

@dataclass
class RatingBreakdown:
    rate_card_id: str
    billable_weight_lbs: float
    is_dim_weight_applied: bool
    applied_weight_tier: WeightTier
    applied_cwt_rate: float
    cwt_units: float
    unclamped_base_charge: float
    base_charge: float
    min_charge_applied: bool
    fuel_surcharge_pct: float
    fuel_surcharge_amount: float
    accessorials_amount: float
    total_expected_charge: float

def determine_weight_tier(weight_lbs: float) -> Tuple[WeightTier, str]:
    """Determine weight tier enum and field name in RateCard."""
    if weight_lbs < 500.0:
        return WeightTier.TIER_1, "rate_tier_1_cwt"
    elif weight_lbs < 2000.0:
        return WeightTier.TIER_2, "rate_tier_2_cwt"
    elif weight_lbs < 5000.0:
        return WeightTier.TIER_3, "rate_tier_3_cwt"
    elif weight_lbs < 10000.0:
        return WeightTier.TIER_4, "rate_tier_4_cwt"
    else:
        return WeightTier.TIER_5, "rate_tier_5_cwt"

def calculate_dim_weight(length_in: float, width_in: float, height_in: float, dim_factor: int = 139) -> float:
    """Calculate volumetric dimensional weight for a package/handling unit."""
    cubic_inches = length_in * width_in * height_in
    return round(cubic_inches / max(dim_factor, 1), 2)

class RatingEngine:
    """
    Contract-driven rating engine for freight shipments.
    """
    def __init__(self, rate_cards: Optional[List[RateCard]] = None):
        # Key: (carrier_id, lane_id, service_level) -> List[RateCard]
        self.rate_card_index: Dict[Tuple[str, str, ServiceLevel], List[RateCard]] = {}
        if rate_cards:
            for rc in rate_cards:
                self.add_rate_card(rc)

    def add_rate_card(self, rate_card: RateCard):
        key = (rate_card.carrier_id, rate_card.lane_id, rate_card.service_level)
        if key not in self.rate_card_index:
            self.rate_card_index[key] = []
        self.rate_card_index[key].append(rate_card)

    def find_active_rate_card(
        self, carrier_id: str, lane_id: str, service_level: ServiceLevel, as_of_date: date
    ) -> Optional[RateCard]:
        """Find the rate card effective on the specified date."""
        key = (carrier_id, lane_id, service_level)
        candidates = self.rate_card_index.get(key, [])
        for rc in candidates:
            if (
                rc.status == RateCardStatus.ACTIVE
                and rc.effective_start_date <= as_of_date <= rc.effective_end_date
            ):
                return rc
        return None

    def calculate_expected_charges(
        self,
        rate_card: RateCard,
        actual_weight_lbs: float,
        dim_weight_lbs: float,
        authorized_accessorials: Optional[List[Accessorial]] = None,
    ) -> RatingBreakdown:
        """
        Deterministically rate a shipment using contracted rate card.
        """
        billable_weight = max(actual_weight_lbs, dim_weight_lbs)
        is_dim = dim_weight_lbs > actual_weight_lbs

        tier, rate_field = determine_weight_tier(billable_weight)
        cwt_rate = getattr(rate_card, rate_field)
        cwt_units = round(billable_weight / 100.0, 2)
        raw_base = round(cwt_units * cwt_rate, 2)

        min_applied = raw_base < rate_card.base_min_charge
        base_charge = max(rate_card.base_min_charge, raw_base)

        fuel_surcharge = round(base_charge * rate_card.fuel_surcharge_pct, 2)

        accessorials_total = 0.0
        if authorized_accessorials:
            for acc in authorized_accessorials:
                if acc.authorized:
                    accessorials_total += acc.standard_fee
        accessorials_total = round(accessorials_total, 2)

        total_charge = round(base_charge + fuel_surcharge + accessorials_total, 2)

        return RatingBreakdown(
            rate_card_id=rate_card.rate_card_id,
            billable_weight_lbs=billable_weight,
            is_dim_weight_applied=is_dim,
            applied_weight_tier=tier,
            applied_cwt_rate=cwt_rate,
            cwt_units=cwt_units,
            unclamped_base_charge=raw_base,
            base_charge=base_charge,
            min_charge_applied=min_applied,
            fuel_surcharge_pct=rate_card.fuel_surcharge_pct,
            fuel_surcharge_amount=fuel_surcharge,
            accessorials_amount=accessorials_total,
            total_expected_charge=total_charge,
        )
