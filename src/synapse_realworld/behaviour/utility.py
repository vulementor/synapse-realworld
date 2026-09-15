from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from synapse_realworld.domain.enums import OutsideOption, PurchasePurpose
from synapse_realworld.domain.models import ChoiceAlternative, Household


@dataclass(frozen=True, slots=True)
class UtilityWeights:
    """Transparent, deliberately simple v0.1 coefficients.

    These are not calibrated production coefficients. They exist to make the
    vertical slice deterministic and testable until LAA historical data is loaded.
    """

    price_per_billion: float = -0.58
    monthly_payment_per_10m: float = -0.42
    commute_per_10min: float = -0.28
    product_match: float = 0.85
    affordability_breach: float = -1.10
    investor_shophouse_bonus: float = 0.35
    own_stay_garden_bonus: float = 0.25
    outside_option_base: float = -0.25


class BaselineUtilityModel:
    model_version = "baseline-utility-v0.1"

    def __init__(self, weights: UtilityWeights | None = None):
        self.weights = weights or UtilityWeights()

    def utility(self, household: Household, alternative: ChoiceAlternative) -> float:
        w = self.weights
        if alternative.outside_option is not None:
            value = w.outside_option_base
            if alternative.outside_option == OutsideOption.CONTINUE_RENTING:
                value += (
                    0.12
                    if household.purchase_horizon_days and household.purchase_horizon_days > 180
                    else 0
                )
            if alternative.outside_option == OutsideOption.POSTPONED:
                value += (
                    0.18
                    if household.purchase_horizon_days and household.purchase_horizon_days > 90
                    else -0.05
                )
            if alternative.outside_option == OutsideOption.NO_PURCHASE:
                value -= 0.10
            return value

        assert alternative.unit is not None and alternative.offer is not None
        price_billion = alternative.offer.effective_price / 1_000_000_000
        monthly_10m = alternative.offer.monthly_payment_est / 10_000_000
        commute_10m = (alternative.commute_min or 0.0) / 10.0

        value = (
            w.price_per_billion * price_billion
            + w.monthly_payment_per_10m * monthly_10m
            + w.commute_per_10min * commute_10m
        )

        if household.preferred_product_type == alternative.unit.product_type:
            value += w.product_match

        if household.max_monthly_payment_million is not None:
            max_payment = household.max_monthly_payment_million * 1_000_000
            if alternative.offer.monthly_payment_est > max_payment:
                value += w.affordability_breach

        if (
            household.purchase_purpose == PurchasePurpose.INVESTMENT
            and alternative.unit.product_type.value == "shophouse"
        ):
            value += w.investor_shophouse_bonus

        if (
            household.purchase_purpose == PurchasePurpose.OWN_STAY
            and alternative.unit.product_type.value in {"garden_townhouse", "garden_villa"}
        ):
            value += w.own_stay_garden_bonus

        return value

    def probabilities(
        self, household: Household, alternatives: Iterable[ChoiceAlternative]
    ) -> dict[str, float]:
        items = tuple(alternatives)
        if not items:
            raise ValueError("alternatives cannot be empty")

        utilities = {alt.alternative_id: self.utility(household, alt) for alt in items}
        max_utility = max(utilities.values())
        exp_values = {key: math.exp(value - max_utility) for key, value in utilities.items()}
        denominator = sum(exp_values.values())
        return {key: value / denominator for key, value in exp_values.items()}
