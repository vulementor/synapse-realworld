from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence

from synapse_realworld.domain.enums import ProductType, PurchasePurpose
from synapse_realworld.domain.models import Household


@dataclass(frozen=True, slots=True)
class PopulationProfile:
    name: str = "laa-demo-v0.1"
    own_stay_share: float = 0.58
    investment_share: float = 0.27
    mixed_share: float = 0.10
    business_share: float = 0.05

    def purpose_weights(self) -> tuple[float, ...]:
        return (
            self.own_stay_share,
            self.investment_share,
            self.mixed_share,
            self.business_share,
        )


class SyntheticPopulationGenerator:
    population_version = "synthetic-demo-v0.1"

    def __init__(self, profile: PopulationProfile | None = None):
        self.profile = profile or PopulationProfile()

    def generate(self, size: int, *, seed: int) -> list[Household]:
        if size <= 0:
            raise ValueError("size must be positive")
        rng = random.Random(seed)
        purposes: Sequence[PurchasePurpose] = (
            PurchasePurpose.OWN_STAY,
            PurchasePurpose.INVESTMENT,
            PurchasePurpose.MIXED,
            PurchasePurpose.BUSINESS,
        )
        product_types = tuple(ProductType)
        households: list[Household] = []
        for _ in range(size):
            purpose = rng.choices(purposes, weights=self.profile.purpose_weights(), k=1)[0]
            preferred = rng.choice(product_types)
            households.append(
                Household(
                    purchase_purpose=purpose,
                    household_size_band=rng.choices(
                        ["1", "2", "3-4", "5+"], weights=[0.07, 0.22, 0.53, 0.18], k=1
                    )[0],
                    children_band=rng.choices(
                        ["0", "1", "2+"], weights=[0.30, 0.44, 0.26], k=1
                    )[0],
                    income_midpoint_million=rng.choices(
                        [25, 40, 65, 100, 150], weights=[0.12, 0.27, 0.34, 0.19, 0.08], k=1
                    )[0],
                    liquid_capital_million=rng.choices(
                        [350, 750, 1500, 2500, 4000],
                        weights=[0.12, 0.28, 0.34, 0.18, 0.08],
                        k=1,
                    )[0],
                    max_monthly_payment_million=rng.choices(
                        [10, 15, 20, 30, 45], weights=[0.14, 0.27, 0.31, 0.20, 0.08], k=1
                    )[0],
                    purchase_horizon_days=rng.choices(
                        [30, 90, 180, 365], weights=[0.18, 0.37, 0.29, 0.16], k=1
                    )[0],
                    workplace_zone=rng.choice(["VSIP III", "Nam Tan Uyen", "THACO", "Other"]),
                    commute_tolerance_min=rng.choice([20, 25, 30, 35, 45]),
                    preferred_product_type=preferred,
                    profile_confidence=0.35,
                )
            )
        return households
