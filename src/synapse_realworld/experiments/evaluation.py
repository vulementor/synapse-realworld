from __future__ import annotations

import math
from collections.abc import Iterable

from synapse_realworld.experiments.models import (
    ExperimentDefinition,
    ExperimentEvaluation,
    ExperimentObservation,
    ExperimentPrediction,
    VariantAggregate,
)


def _aggregate(
    observations: Iterable[ExperimentObservation],
    *,
    variant: str,
) -> VariantAggregate:
    selected = tuple(item for item in observations if item.variant == variant)
    successes = sum(item.successes for item in selected)
    trials = sum(item.trials for item in selected)
    rate = successes / trials if trials else 0.0
    return VariantAggregate(
        variant=variant,
        successes=successes,
        trials=trials,
        rate=rate,
    )


def _effect_ci95(control: VariantAggregate, treatment: VariantAggregate) -> tuple[float, float]:
    effect = treatment.rate - control.rate
    if control.trials == 0 or treatment.trials == 0:
        return effect, effect
    variance = (
        control.rate * (1 - control.rate) / control.trials
        + treatment.rate * (1 - treatment.rate) / treatment.trials
    )
    standard_error = math.sqrt(max(variance, 0.0))
    margin = 1.96 * standard_error
    return max(-1.0, effect - margin), min(1.0, effect + margin)


def _direction(value: float, *, tolerance: float = 1e-12) -> int:
    if value > tolerance:
        return 1
    if value < -tolerance:
        return -1
    return 0


def evaluate_experiment(
    *,
    definition: ExperimentDefinition,
    prediction: ExperimentPrediction,
    observations: Iterable[ExperimentObservation],
) -> ExperimentEvaluation:
    materialized = tuple(observations)
    if prediction.experiment_id != definition.experiment_id:
        raise ValueError("prediction does not belong to experiment")
    if prediction.metric_name != definition.metric_name:
        raise ValueError("prediction metric does not match experiment metric")

    control = _aggregate(materialized, variant=definition.control_variant)
    treatment = _aggregate(materialized, variant=definition.treatment_variant)
    if control.trials == 0 or treatment.trials == 0:
        raise ValueError("both control and treatment require observations")

    observed_effect = treatment.rate - control.rate
    ci_low, ci_high = _effect_ci95(control, treatment)
    absolute_error = abs(observed_effect - prediction.effect_p50)
    within_prediction = prediction.effect_p05 <= observed_effect <= prediction.effect_p95
    direction_correct = _direction(observed_effect) == _direction(prediction.effect_p50)
    minimum_sample_reached = (
        control.trials >= definition.minimum_trials_per_variant
        and treatment.trials >= definition.minimum_trials_per_variant
    )

    warnings: list[str] = []
    if not minimum_sample_reached:
        warnings.append("minimum_sample_not_reached")
    causal_allowed = definition.assignment_method.supports_causal_interpretation
    if not causal_allowed:
        warnings.append(
            f"non_randomized_assignment:{definition.assignment_method.value}: "
            "effect is associative, not causal"
        )
    if ci_low <= 0 <= ci_high:
        warnings.append("observed_effect_ci_crosses_zero")
    if not within_prediction:
        warnings.append("observed_effect_outside_predicted_interval")

    return ExperimentEvaluation(
        experiment_id=definition.experiment_id,
        metric_name=definition.metric_name,
        prediction_id=prediction.prediction_id,
        model_artifact_id=prediction.model_artifact_id,
        control=control,
        treatment=treatment,
        observed_effect=observed_effect,
        observed_effect_ci95_low=ci_low,
        observed_effect_ci95_high=ci_high,
        predicted_effect_p05=prediction.effect_p05,
        predicted_effect_p50=prediction.effect_p50,
        predicted_effect_p95=prediction.effect_p95,
        absolute_prediction_error=absolute_error,
        observed_within_predicted_interval=within_prediction,
        prediction_direction_correct=direction_correct,
        causal_interpretation_allowed=causal_allowed,
        minimum_sample_reached=minimum_sample_reached,
        warnings=tuple(warnings),
    )
