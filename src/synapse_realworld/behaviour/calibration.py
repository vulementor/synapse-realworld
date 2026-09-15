from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.behaviour.utility import UtilityWeights
from synapse_realworld.domain.enums import PurchasePurpose
from synapse_realworld.domain.models import ChoiceAlternative, Household


FEATURE_NAMES = (
    "price_per_billion",
    "monthly_payment_per_10m",
    "commute_per_10min",
    "product_match",
    "affordability_breach",
    "investor_shophouse_bonus",
    "own_stay_garden_bonus",
    "outside_option_base",
)


class CalibrationExample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    household: Household
    alternatives: tuple[ChoiceAlternative, ...]
    selected_alternative_id: str

    def model_post_init(self, __context: object) -> None:
        ids = {alternative.alternative_id for alternative in self.alternatives}
        if self.selected_alternative_id not in ids:
            raise ValueError("selected_alternative_id must exist in alternatives")
        if len(self.alternatives) < 2:
            raise ValueError("calibration example requires at least two alternatives")


class CalibrationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    examples: int = Field(ge=0)
    log_loss: float = Field(ge=0)
    top1_accuracy: float = Field(ge=0, le=1)


class CalibrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_version: str = "multinomial-logit-v0.2"
    weights: dict[str, float]
    epochs: int = Field(gt=0)
    converged: bool
    metrics: CalibrationMetrics

    def to_utility_weights(self) -> UtilityWeights:
        return UtilityWeights(**self.weights)


@dataclass(frozen=True, slots=True)
class MultinomialLogitCalibrator:
    learning_rate: float = 0.03
    max_epochs: int = 1200
    l2: float = 0.001
    tolerance: float = 1e-8

    @staticmethod
    def _features(household: Household, alternative: ChoiceAlternative) -> dict[str, float]:
        values = {name: 0.0 for name in FEATURE_NAMES}
        if alternative.outside_option is not None:
            values["outside_option_base"] = 1.0
            return values

        assert alternative.unit is not None and alternative.offer is not None
        values["price_per_billion"] = alternative.offer.effective_price / 1_000_000_000
        values["monthly_payment_per_10m"] = alternative.offer.monthly_payment_est / 10_000_000
        values["commute_per_10min"] = (alternative.commute_min or 0.0) / 10.0
        values["product_match"] = float(
            household.preferred_product_type == alternative.unit.product_type
        )
        if household.max_monthly_payment_million is not None:
            max_payment = household.max_monthly_payment_million * 1_000_000
            values["affordability_breach"] = float(
                alternative.offer.monthly_payment_est > max_payment
            )
        values["investor_shophouse_bonus"] = float(
            household.purchase_purpose == PurchasePurpose.INVESTMENT
            and alternative.unit.product_type.value == "shophouse"
        )
        values["own_stay_garden_bonus"] = float(
            household.purchase_purpose == PurchasePurpose.OWN_STAY
            and alternative.unit.product_type.value in {"garden_townhouse", "garden_villa"}
        )
        return values

    @classmethod
    def _probabilities(
        cls,
        example: CalibrationExample,
        weights: dict[str, float],
    ) -> dict[str, float]:
        utilities: dict[str, float] = {}
        for alternative in example.alternatives:
            features = cls._features(example.household, alternative)
            utilities[alternative.alternative_id] = sum(
                weights[name] * features[name] for name in FEATURE_NAMES
            )
        maximum = max(utilities.values())
        exponentials = {key: math.exp(value - maximum) for key, value in utilities.items()}
        denominator = sum(exponentials.values())
        return {key: value / denominator for key, value in exponentials.items()}

    def fit(
        self,
        examples: Iterable[CalibrationExample],
        *,
        initial_weights: UtilityWeights | None = None,
    ) -> CalibrationResult:
        data = tuple(examples)
        if not data:
            raise ValueError("calibration requires at least one example")

        starting = initial_weights or UtilityWeights()
        weights = {name: float(getattr(starting, name)) for name in FEATURE_NAMES}
        previous_loss = math.inf
        converged = False
        completed_epochs = 0

        for epoch in range(1, self.max_epochs + 1):
            gradients = {name: 0.0 for name in FEATURE_NAMES}
            loss = 0.0
            for example in data:
                probabilities = self._probabilities(example, weights)
                selected_probability = max(
                    probabilities[example.selected_alternative_id],
                    1e-15,
                )
                loss -= math.log(selected_probability)

                for alternative in example.alternatives:
                    target = float(alternative.alternative_id == example.selected_alternative_id)
                    error = target - probabilities[alternative.alternative_id]
                    features = self._features(example.household, alternative)
                    for name in FEATURE_NAMES:
                        gradients[name] += error * features[name]

            scale = 1.0 / len(data)
            for name in FEATURE_NAMES:
                regularized_gradient = gradients[name] * scale - self.l2 * weights[name]
                weights[name] += self.learning_rate * regularized_gradient

            mean_loss = loss * scale
            completed_epochs = epoch
            if abs(previous_loss - mean_loss) <= self.tolerance:
                converged = True
                break
            previous_loss = mean_loss

        metrics = self.evaluate(data, weights=weights)
        return CalibrationResult(
            weights=weights,
            epochs=completed_epochs,
            converged=converged,
            metrics=metrics,
        )

    def evaluate(
        self,
        examples: Iterable[CalibrationExample],
        *,
        weights: dict[str, float],
    ) -> CalibrationMetrics:
        data = tuple(examples)
        if not data:
            return CalibrationMetrics(examples=0, log_loss=0.0, top1_accuracy=0.0)
        total_loss = 0.0
        correct = 0
        for example in data:
            probabilities = self._probabilities(example, weights)
            total_loss -= math.log(max(probabilities[example.selected_alternative_id], 1e-15))
            predicted = max(probabilities, key=probabilities.get)
            correct += int(predicted == example.selected_alternative_id)
        return CalibrationMetrics(
            examples=len(data),
            log_loss=total_loss / len(data),
            top1_accuracy=correct / len(data),
        )
