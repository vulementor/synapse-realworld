from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.behaviour.calibration import MultinomialLogitCalibrator
from synapse_realworld.behaviour.diagnostics import (
    CalibrationDiagnostics,
    build_calibration_diagnostics,
)
from synapse_realworld.data.choice_set import TemporalChoiceSetBuilder
from synapse_realworld.data.dataset import DecisionDatasetBuilder
from synapse_realworld.data.decision_assembler import CommuteProvider, HistoricalDecisionAssembler
from synapse_realworld.data.projection import project_feature_observations
from synapse_realworld.data.training import build_calibration_examples, temporal_holdout
from synapse_realworld.domain.events import CanonicalEvent
from synapse_realworld.domain.models import Offer
from synapse_realworld.domain.temporal import UnitVersion
from synapse_realworld.registry.models import ModelArtifact


class CalibrationWorkflowResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact: ModelArtifact
    diagnostics: CalibrationDiagnostics
    historical_choices: int = Field(ge=0)
    train_examples: int = Field(ge=0)
    holdout_examples: int = Field(ge=0)


def calibrate_historical_choices(
    *,
    unit_versions: Iterable[UnitVersion],
    offers: Iterable[Offer],
    events: Iterable[CanonicalEvent],
    model_name: str,
    model_version: str,
    code_commit_sha: str,
    dataset_snapshot_id: str,
    commute_provider: CommuteProvider | None = None,
    feature_schema_version: str = "decision-features-v0.3",
    holdout_fraction: float = 0.2,
    bootstrap_samples: int = 100,
    seed: int = 42,
) -> CalibrationWorkflowResult:
    materialized_events = tuple(events)
    choice_builder = TemporalChoiceSetBuilder(
        unit_versions=tuple(unit_versions),
        offers=tuple(offers),
    )
    decisions = HistoricalDecisionAssembler(
        choice_builder,
        commute_provider=commute_provider,
    ).assemble(materialized_events)
    observations = project_feature_observations(materialized_events)
    rows = DecisionDatasetBuilder().build(events=decisions, observations=observations)
    timed_examples = build_calibration_examples(rows)
    if len(timed_examples) < 2:
        raise ValueError("at least two verified historical choices are required")

    train, holdout = temporal_holdout(
        timed_examples,
        holdout_fraction=holdout_fraction,
    )
    calibrator = MultinomialLogitCalibrator()
    fit = calibrator.fit(train)
    holdout_metrics = calibrator.evaluate(holdout, weights=fit.weights)
    diagnostics = build_calibration_diagnostics(
        examples=holdout,
        bootstrap_examples=train,
        weights=fit.weights,
        calibrator=calibrator,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
    )

    training_times = [item.occurred_at for item in timed_examples[: len(train)]]
    artifact = ModelArtifact(
        model_name=model_name,
        model_version=model_version,
        model_family="multinomial_logit",
        code_commit_sha=code_commit_sha,
        dataset_snapshot_id=dataset_snapshot_id,
        training_window_start=min(training_times) if training_times else None,
        training_window_end=max(training_times) if training_times else None,
        feature_schema_version=feature_schema_version,
        parameters=fit.weights,
        train_metrics={
            "examples": float(fit.metrics.examples),
            "log_loss": fit.metrics.log_loss,
            "top1_accuracy": fit.metrics.top1_accuracy,
        },
        holdout_metrics={
            "examples": float(holdout_metrics.examples),
            "log_loss": holdout_metrics.log_loss,
            "top1_accuracy": holdout_metrics.top1_accuracy,
            "uniform_log_loss": diagnostics.baseline.uniform_log_loss,
            "improvement_pct": diagnostics.baseline.improvement_pct,
        },
        diagnostics=diagnostics.model_dump(mode="json"),
        notes=(
            "Decision-support candidate. Approval must be recorded separately before "
            "business use."
        ),
    )
    return CalibrationWorkflowResult(
        artifact=artifact,
        diagnostics=diagnostics,
        historical_choices=len(timed_examples),
        train_examples=len(train),
        holdout_examples=len(holdout),
    )
