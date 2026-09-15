from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.experiments.models import ExperimentEvaluation


class ScorecardModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelExperimentScorecard(ScorecardModel):
    model_artifact_id: UUID
    evaluated_experiments: int = Field(ge=0)
    causal_experiments: int = Field(ge=0)
    minimum_sample_experiments: int = Field(ge=0)
    mean_absolute_effect_error: float | None = Field(default=None, ge=0)
    predicted_interval_coverage_rate: float | None = Field(default=None, ge=0, le=1)
    direction_accuracy: float | None = Field(default=None, ge=0, le=1)
    minimum_sample_rate: float | None = Field(default=None, ge=0, le=1)
    causal_experiment_rate: float | None = Field(default=None, ge=0, le=1)
    warnings: tuple[str, ...] = ()


def build_model_experiment_scorecard(
    evaluations: Iterable[ExperimentEvaluation],
    *,
    model_artifact_id: UUID,
) -> ModelExperimentScorecard:
    matching = tuple(
        item for item in evaluations if item.model_artifact_id == model_artifact_id
    )
    count = len(matching)
    if count == 0:
        return ModelExperimentScorecard(
            model_artifact_id=model_artifact_id,
            evaluated_experiments=0,
            causal_experiments=0,
            minimum_sample_experiments=0,
            warnings=("no_evaluated_experiments",),
        )

    causal = sum(item.causal_interpretation_allowed for item in matching)
    sufficient = sum(item.minimum_sample_reached for item in matching)
    mae = sum(item.absolute_prediction_error for item in matching) / count
    coverage = sum(item.observed_within_predicted_interval for item in matching) / count
    direction = sum(item.prediction_direction_correct for item in matching) / count

    warnings: list[str] = []
    if count < 5:
        warnings.append("small_experiment_history: fewer than 5 evaluated experiments")
    if sufficient < count:
        warnings.append("some_experiments_below_minimum_sample")
    if causal == 0:
        warnings.append("no_randomized_experiments: causal validation unavailable")
    if coverage < 0.8 and count >= 5:
        warnings.append("low_prediction_interval_coverage")
    if direction < 0.7 and count >= 5:
        warnings.append("low_effect_direction_accuracy")

    return ModelExperimentScorecard(
        model_artifact_id=model_artifact_id,
        evaluated_experiments=count,
        causal_experiments=causal,
        minimum_sample_experiments=sufficient,
        mean_absolute_effect_error=mae,
        predicted_interval_coverage_rate=coverage,
        direction_accuracy=direction,
        minimum_sample_rate=sufficient / count,
        causal_experiment_rate=causal / count,
        warnings=tuple(warnings),
    )
