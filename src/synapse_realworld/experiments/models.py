from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExperimentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AssignmentMethod(StrEnum):
    RANDOMIZED = "randomized"
    HASH_RANDOMIZED = "hash_randomized"
    QUASI_EXPERIMENTAL = "quasi_experimental"
    MANUAL = "manual"
    OBSERVATIONAL = "observational"

    @property
    def supports_causal_interpretation(self) -> bool:
        return self in {self.RANDOMIZED, self.HASH_RANDOMIZED}


class ExperimentStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ExperimentDefinition(ExperimentModel):
    experiment_id: UUID = Field(default_factory=uuid4)
    name: str
    hypothesis: str
    metric_name: str = "laa_choice_rate"
    control_variant: str = "control"
    treatment_variant: str = "treatment"
    target_segment: str = "all"
    assignment_method: AssignmentMethod = AssignmentMethod.RANDOMIZED
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    minimum_trials_per_variant: int = Field(default=30, gt=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_definition(self) -> ExperimentDefinition:
        for field_name in (
            "name",
            "hypothesis",
            "metric_name",
            "control_variant",
            "treatment_variant",
            "created_by",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")
        if self.control_variant == self.treatment_variant:
            raise ValueError("control_variant and treatment_variant must differ")
        if self.planned_start_at and self.planned_end_at:
            if self.planned_start_at >= self.planned_end_at:
                raise ValueError("planned_start_at must be before planned_end_at")
        return self


class ExperimentPrediction(ExperimentModel):
    prediction_id: UUID = Field(default_factory=uuid4)
    experiment_id: UUID
    model_artifact_id: UUID
    model_status: str
    population_version: str
    metric_name: str
    control_scenario_id: str
    treatment_scenario_id: str
    control_point_estimate: float = Field(ge=0, le=1)
    treatment_point_estimate: float = Field(ge=0, le=1)
    effect_mean: float = Field(ge=-1, le=1)
    effect_p05: float = Field(ge=-1, le=1)
    effect_p50: float = Field(ge=-1, le=1)
    effect_p95: float = Field(ge=-1, le=1)
    ensemble_samples: int = Field(gt=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_snapshot_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_prediction(self) -> ExperimentPrediction:
        if self.effect_p05 > self.effect_p50 or self.effect_p50 > self.effect_p95:
            raise ValueError("effect quantiles must satisfy p05 <= p50 <= p95")
        if not self.metric_name.strip():
            raise ValueError("metric_name is required")
        if not self.population_version.strip():
            raise ValueError("population_version is required")
        if not self.source_snapshot_id.strip():
            raise ValueError("source_snapshot_id is required")
        return self


class ExperimentObservation(ExperimentModel):
    observation_id: UUID = Field(default_factory=uuid4)
    experiment_id: UUID
    variant: str
    metric_name: str
    successes: int = Field(ge=0)
    trials: int = Field(gt=0)
    observed_at: datetime
    source_id: str
    source_event_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_observation(self) -> ExperimentObservation:
        if self.successes > self.trials:
            raise ValueError("successes cannot exceed trials")
        for field_name in ("variant", "metric_name", "source_id", "source_event_key"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")
        return self


class VariantAggregate(ExperimentModel):
    variant: str
    successes: int = Field(ge=0)
    trials: int = Field(ge=0)
    rate: float = Field(ge=0, le=1)


class ExperimentEvaluation(ExperimentModel):
    experiment_id: UUID
    metric_name: str
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    prediction_id: UUID
    model_artifact_id: UUID
    control: VariantAggregate
    treatment: VariantAggregate
    observed_effect: float = Field(ge=-1, le=1)
    observed_effect_ci95_low: float = Field(ge=-1, le=1)
    observed_effect_ci95_high: float = Field(ge=-1, le=1)
    predicted_effect_p05: float = Field(ge=-1, le=1)
    predicted_effect_p50: float = Field(ge=-1, le=1)
    predicted_effect_p95: float = Field(ge=-1, le=1)
    absolute_prediction_error: float = Field(ge=0)
    observed_within_predicted_interval: bool
    prediction_direction_correct: bool
    causal_interpretation_allowed: bool
    minimum_sample_reached: bool
    warnings: tuple[str, ...] = ()
