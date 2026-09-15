from __future__ import annotations

import math
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.experiments.models import (
    ExperimentDefinition,
    ExperimentObservation,
    VariantAggregate,
)


class ExperimentQAModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExperimentQualityAssessment(ExperimentQAModel):
    control: VariantAggregate
    treatment: VariantAggregate
    total_trials: int = Field(ge=0)
    expected_treatment_share: float = Field(gt=0, lt=1)
    observed_treatment_share: float = Field(ge=0, le=1)
    sample_ratio_zscore: float
    sample_ratio_mismatch: bool
    minimum_sample_reached: bool
    causal_design_declared: bool
    warnings: tuple[str, ...] = ()


def _aggregate(
    observations: Iterable[ExperimentObservation],
    *,
    variant: str,
) -> VariantAggregate:
    selected = tuple(item for item in observations if item.variant == variant)
    successes = sum(item.successes for item in selected)
    trials = sum(item.trials for item in selected)
    return VariantAggregate(
        variant=variant,
        successes=successes,
        trials=trials,
        rate=successes / trials if trials else 0.0,
    )


def assess_experiment_quality(
    *,
    definition: ExperimentDefinition,
    observations: Iterable[ExperimentObservation],
    expected_treatment_share: float = 0.5,
    sample_ratio_z_threshold: float = 3.29,
) -> ExperimentQualityAssessment:
    if not 0 < expected_treatment_share < 1:
        raise ValueError("expected_treatment_share must be between 0 and 1")
    if sample_ratio_z_threshold <= 0:
        raise ValueError("sample_ratio_z_threshold must be positive")

    materialized = tuple(observations)
    control = _aggregate(materialized, variant=definition.control_variant)
    treatment = _aggregate(materialized, variant=definition.treatment_variant)
    total = control.trials + treatment.trials
    observed_share = treatment.trials / total if total else 0.0
    variance = total * expected_treatment_share * (1 - expected_treatment_share)
    zscore = (
        (treatment.trials - total * expected_treatment_share) / math.sqrt(variance)
        if variance > 0
        else 0.0
    )
    mismatch = abs(zscore) >= sample_ratio_z_threshold
    minimum_sample = (
        control.trials >= definition.minimum_trials_per_variant
        and treatment.trials >= definition.minimum_trials_per_variant
    )
    causal_design = definition.assignment_method.supports_causal_interpretation

    warnings: list[str] = []
    if total == 0:
        warnings.append("no_observations")
    if not minimum_sample:
        warnings.append("minimum_sample_not_reached")
    if mismatch:
        warnings.append("sample_ratio_mismatch")
    if not causal_design:
        warnings.append(
            f"non_randomized_assignment:{definition.assignment_method.value}"
        )

    return ExperimentQualityAssessment(
        control=control,
        treatment=treatment,
        total_trials=total,
        expected_treatment_share=expected_treatment_share,
        observed_treatment_share=observed_share,
        sample_ratio_zscore=zscore,
        sample_ratio_mismatch=mismatch,
        minimum_sample_reached=minimum_sample,
        causal_design_declared=causal_design,
        warnings=tuple(warnings),
    )
