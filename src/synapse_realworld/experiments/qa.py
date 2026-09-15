from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.experiments.models import (
    ExperimentAssignmentReceipt,
    ExperimentDefinition,
    ExperimentObservation,
    VariantAggregate,
)


class ExperimentQAModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AllocationBucketAssessment(ExperimentQAModel):
    bucket_type: Literal["date", "channel", "cohort"]
    bucket: str
    control_assignments: int = Field(ge=0)
    treatment_assignments: int = Field(ge=0)
    total_assignments: int = Field(ge=0)
    observed_treatment_share: float = Field(ge=0, le=1)
    sample_ratio_zscore: float
    sample_ratio_mismatch: bool


class ExperimentQualityAssessment(ExperimentQAModel):
    control: VariantAggregate
    treatment: VariantAggregate
    total_trials: int = Field(ge=0)
    allocation_source: Literal["assignment_receipts", "outcome_trials"]
    control_assignments: int = Field(ge=0)
    treatment_assignments: int = Field(ge=0)
    total_assignments: int = Field(ge=0)
    expected_treatment_share: float = Field(gt=0, lt=1)
    observed_treatment_share: float = Field(ge=0, le=1)
    sample_ratio_zscore: float
    sample_ratio_mismatch: bool
    allocation_buckets: tuple[AllocationBucketAssessment, ...] = ()
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


def _allocation_stats(
    *,
    control_count: int,
    treatment_count: int,
    expected_treatment_share: float,
    sample_ratio_z_threshold: float,
) -> tuple[int, float, float, bool]:
    total = control_count + treatment_count
    observed_share = treatment_count / total if total else 0.0
    variance = total * expected_treatment_share * (1 - expected_treatment_share)
    zscore = (
        (treatment_count - total * expected_treatment_share) / math.sqrt(variance)
        if variance > 0
        else 0.0
    )
    return total, observed_share, zscore, abs(zscore) >= sample_ratio_z_threshold


def _assignment_bucket_checks(
    *,
    assignments: tuple[ExperimentAssignmentReceipt, ...],
    definition: ExperimentDefinition,
    expected_treatment_share: float,
    sample_ratio_z_threshold: float,
) -> tuple[AllocationBucketAssessment, ...]:
    grouped: dict[tuple[str, str], list[ExperimentAssignmentReceipt]] = defaultdict(list)
    for assignment in assignments:
        grouped[("date", assignment.assigned_at.date().isoformat())].append(assignment)
        if assignment.channel is not None:
            grouped[("channel", assignment.channel)].append(assignment)
        if assignment.cohort is not None:
            grouped[("cohort", assignment.cohort)].append(assignment)

    assessments: list[AllocationBucketAssessment] = []
    for (bucket_type, bucket), items in sorted(grouped.items()):
        control_count = sum(item.variant == definition.control_variant for item in items)
        treatment_count = sum(item.variant == definition.treatment_variant for item in items)
        total, observed_share, zscore, mismatch = _allocation_stats(
            control_count=control_count,
            treatment_count=treatment_count,
            expected_treatment_share=expected_treatment_share,
            sample_ratio_z_threshold=sample_ratio_z_threshold,
        )
        assessments.append(
            AllocationBucketAssessment(
                bucket_type=bucket_type,
                bucket=bucket,
                control_assignments=control_count,
                treatment_assignments=treatment_count,
                total_assignments=total,
                observed_treatment_share=observed_share,
                sample_ratio_zscore=zscore,
                sample_ratio_mismatch=mismatch,
            )
        )
    return tuple(assessments)


def assess_experiment_quality(
    *,
    definition: ExperimentDefinition,
    observations: Iterable[ExperimentObservation],
    assignments: Iterable[ExperimentAssignmentReceipt] = (),
    expected_treatment_share: float = 0.5,
    sample_ratio_z_threshold: float = 3.29,
) -> ExperimentQualityAssessment:
    if not 0 < expected_treatment_share < 1:
        raise ValueError("expected_treatment_share must be between 0 and 1")
    if sample_ratio_z_threshold <= 0:
        raise ValueError("sample_ratio_z_threshold must be positive")

    materialized = tuple(observations)
    assignment_receipts = tuple(assignments)
    control = _aggregate(materialized, variant=definition.control_variant)
    treatment = _aggregate(materialized, variant=definition.treatment_variant)
    total_trials = control.trials + treatment.trials

    if assignment_receipts:
        allocation_source = "assignment_receipts"
        control_assignments = sum(
            item.variant == definition.control_variant for item in assignment_receipts
        )
        treatment_assignments = sum(
            item.variant == definition.treatment_variant for item in assignment_receipts
        )
        bucket_checks = _assignment_bucket_checks(
            assignments=assignment_receipts,
            definition=definition,
            expected_treatment_share=expected_treatment_share,
            sample_ratio_z_threshold=sample_ratio_z_threshold,
        )
    else:
        allocation_source = "outcome_trials"
        control_assignments = control.trials
        treatment_assignments = treatment.trials
        bucket_checks = ()

    total_assignments, observed_share, zscore, mismatch = _allocation_stats(
        control_count=control_assignments,
        treatment_count=treatment_assignments,
        expected_treatment_share=expected_treatment_share,
        sample_ratio_z_threshold=sample_ratio_z_threshold,
    )
    minimum_sample = (
        control.trials >= definition.minimum_trials_per_variant
        and treatment.trials >= definition.minimum_trials_per_variant
    )
    causal_design = definition.assignment_method.supports_causal_interpretation

    warnings: list[str] = []
    if total_trials == 0:
        warnings.append("no_observations")
    if not minimum_sample:
        warnings.append("minimum_sample_not_reached")
    if mismatch:
        warnings.append("sample_ratio_mismatch")
    warnings.extend(
        f"sample_ratio_mismatch:{item.bucket_type}:{item.bucket}"
        for item in bucket_checks
        if item.sample_ratio_mismatch
    )
    if not causal_design:
        warnings.append(f"non_randomized_assignment:{definition.assignment_method.value}")

    return ExperimentQualityAssessment(
        control=control,
        treatment=treatment,
        total_trials=total_trials,
        allocation_source=allocation_source,
        control_assignments=control_assignments,
        treatment_assignments=treatment_assignments,
        total_assignments=total_assignments,
        expected_treatment_share=expected_treatment_share,
        observed_treatment_share=observed_share,
        sample_ratio_zscore=zscore,
        sample_ratio_mismatch=mismatch,
        allocation_buckets=bucket_checks,
        minimum_sample_reached=minimum_sample,
        causal_design_declared=causal_design,
        warnings=tuple(warnings),
    )
