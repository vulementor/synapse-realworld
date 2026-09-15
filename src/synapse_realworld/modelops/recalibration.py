from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.experiments import ModelExperimentScorecard


class ModelOpsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RecalibrationState(StrEnum):
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    MONITOR = "monitor"
    REVIEW_RECALIBRATION = "review_recalibration"


class RecalibrationPolicy(ModelOpsModel):
    minimum_evaluated_experiments: int = Field(default=5, gt=0)
    minimum_causal_experiments: int = Field(default=3, ge=0)
    maximum_mean_absolute_effect_error: float = Field(default=0.05, ge=0)
    minimum_interval_coverage_rate: float = Field(default=0.80, ge=0, le=1)
    minimum_direction_accuracy: float = Field(default=0.70, ge=0, le=1)


class RecalibrationAssessment(ModelOpsModel):
    state: RecalibrationState
    scorecard: ModelExperimentScorecard
    policy: RecalibrationPolicy
    reasons: tuple[str, ...] = ()
    human_review_required: bool = True
    automatic_retraining_allowed: bool = False


def assess_recalibration_need(
    scorecard: ModelExperimentScorecard,
    *,
    policy: RecalibrationPolicy | None = None,
) -> RecalibrationAssessment:
    applied = policy or RecalibrationPolicy()
    reasons: list[str] = []

    if scorecard.evaluated_experiments < applied.minimum_evaluated_experiments:
        reasons.append("insufficient_evaluated_experiments")
    if scorecard.causal_experiments < applied.minimum_causal_experiments:
        reasons.append("insufficient_causal_experiments")
    if reasons:
        return RecalibrationAssessment(
            state=RecalibrationState.INSUFFICIENT_EVIDENCE,
            scorecard=scorecard,
            policy=applied,
            reasons=tuple(reasons),
        )

    if (
        scorecard.mean_absolute_effect_error is not None
        and scorecard.mean_absolute_effect_error
        > applied.maximum_mean_absolute_effect_error
    ):
        reasons.append("mean_absolute_effect_error_above_threshold")
    if (
        scorecard.predicted_interval_coverage_rate is not None
        and scorecard.predicted_interval_coverage_rate
        < applied.minimum_interval_coverage_rate
    ):
        reasons.append("prediction_interval_coverage_below_threshold")
    if (
        scorecard.direction_accuracy is not None
        and scorecard.direction_accuracy < applied.minimum_direction_accuracy
    ):
        reasons.append("effect_direction_accuracy_below_threshold")

    state = (
        RecalibrationState.REVIEW_RECALIBRATION
        if reasons
        else RecalibrationState.MONITOR
    )
    return RecalibrationAssessment(
        state=state,
        scorecard=scorecard,
        policy=applied,
        reasons=tuple(reasons),
    )
