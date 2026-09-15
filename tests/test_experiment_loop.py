from datetime import datetime, timezone
from uuid import UUID

import pytest

from synapse_realworld.experiments import (
    AssignmentMethod,
    ExperimentDefinition,
    ExperimentObservation,
    ExperimentPrediction,
    FileExperimentRegistry,
    build_model_experiment_scorecard,
    evaluate_experiment,
)

MODEL_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PREDICTED_AT = datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc)
OBSERVED_AT = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _prediction(experiment_id: UUID) -> ExperimentPrediction:
    return ExperimentPrediction(
        experiment_id=experiment_id,
        model_artifact_id=MODEL_ID,
        model_status="approved",
        population_version="empirical:test:1234",
        metric_name="laa_choice_rate",
        control_scenario_id="control",
        treatment_scenario_id="treatment",
        control_point_estimate=0.20,
        treatment_point_estimate=0.30,
        effect_mean=0.10,
        effect_p05=0.05,
        effect_p50=0.10,
        effect_p95=0.15,
        ensemble_samples=100,
        created_at=PREDICTED_AT,
        source_snapshot_id="snapshot:test",
    )


def _observation(
    experiment_id: UUID,
    *,
    variant: str,
    successes: int,
    trials: int,
    key: str,
    observed_at: datetime = OBSERVED_AT,
) -> ExperimentObservation:
    return ExperimentObservation(
        experiment_id=experiment_id,
        variant=variant,
        metric_name="laa_choice_rate",
        successes=successes,
        trials=trials,
        observed_at=observed_at,
        source_id="crm-test",
        source_event_key=key,
    )


def test_experiment_prediction_is_locked_before_observations(tmp_path) -> None:
    registry = FileExperimentRegistry(tmp_path / "experiments")
    definition = ExperimentDefinition(
        name="LAA offer test",
        hypothesis="Treatment increases LAA choice rate",
        created_by="test",
        minimum_trials_per_variant=50,
    )
    assert registry.create(definition) is True
    prediction = _prediction(definition.experiment_id)
    assert registry.lock_prediction(prediction) is True

    control = _observation(
        definition.experiment_id,
        variant="control",
        successes=20,
        trials=100,
        key="control-batch-1",
    )
    treatment = _observation(
        definition.experiment_id,
        variant="treatment",
        successes=30,
        trials=100,
        key="treatment-batch-1",
    )
    assert registry.append_observation(control) is True
    assert registry.append_observation(control) is False
    assert registry.append_observation(treatment) is True

    with pytest.raises(ValueError, match="before the first observation"):
        registry.lock_prediction(prediction.model_copy(update={"effect_p50": 0.12}))

    stored_prediction = registry.get_prediction(definition.experiment_id)
    assert stored_prediction is not None
    evaluation = evaluate_experiment(
        definition=definition,
        prediction=stored_prediction,
        observations=registry.list_observations(definition.experiment_id),
    )
    assert evaluation.control.rate == 0.20
    assert evaluation.treatment.rate == 0.30
    assert evaluation.observed_effect == pytest.approx(0.10)
    assert evaluation.observed_within_predicted_interval is True
    assert evaluation.prediction_direction_correct is True
    assert evaluation.causal_interpretation_allowed is True
    assert evaluation.minimum_sample_reached is True


def test_registry_rejects_backdated_observation(tmp_path) -> None:
    registry = FileExperimentRegistry(tmp_path / "experiments")
    definition = ExperimentDefinition(
        name="Prospective test",
        hypothesis="Treatment raises the choice rate",
        created_by="test",
    )
    registry.create(definition)
    registry.lock_prediction(_prediction(definition.experiment_id))
    backdated = _observation(
        definition.experiment_id,
        variant="control",
        successes=5,
        trials=20,
        key="backdated",
        observed_at=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc),
    )
    with pytest.raises(ValueError, match="predates the locked prediction"):
        registry.append_observation(backdated)


def test_non_randomized_experiment_is_not_labeled_causal() -> None:
    definition = ExperimentDefinition(
        name="Observed policy comparison",
        hypothesis="Observed treatment group has higher choice rate",
        assignment_method=AssignmentMethod.OBSERVATIONAL,
        created_by="test",
    )
    prediction = _prediction(definition.experiment_id)
    observations = (
        _observation(
            definition.experiment_id,
            variant="control",
            successes=10,
            trials=50,
            key="c",
        ),
        _observation(
            definition.experiment_id,
            variant="treatment",
            successes=15,
            trials=50,
            key="t",
        ),
    )
    evaluation = evaluate_experiment(
        definition=definition,
        prediction=prediction,
        observations=observations,
    )
    assert evaluation.causal_interpretation_allowed is False
    assert any("non_randomized_assignment" in warning for warning in evaluation.warnings)


def test_model_scorecard_aggregates_real_world_forecast_accuracy() -> None:
    randomized = ExperimentDefinition(
        name="Randomized offer test",
        hypothesis="Treatment raises the choice rate",
        created_by="test",
    )
    observational = ExperimentDefinition(
        name="Observed comparison",
        hypothesis="Treatment group has higher choice rate",
        assignment_method=AssignmentMethod.OBSERVATIONAL,
        created_by="test",
    )
    evaluations = []
    for definition, treatment_successes in (
        (randomized, 30),
        (observational, 28),
    ):
        evaluations.append(
            evaluate_experiment(
                definition=definition,
                prediction=_prediction(definition.experiment_id),
                observations=(
                    _observation(
                        definition.experiment_id,
                        variant="control",
                        successes=20,
                        trials=100,
                        key=f"{definition.experiment_id}:control",
                    ),
                    _observation(
                        definition.experiment_id,
                        variant="treatment",
                        successes=treatment_successes,
                        trials=100,
                        key=f"{definition.experiment_id}:treatment",
                    ),
                ),
            )
        )

    scorecard = build_model_experiment_scorecard(
        evaluations,
        model_artifact_id=MODEL_ID,
    )
    assert scorecard.evaluated_experiments == 2
    assert scorecard.causal_experiments == 1
    assert scorecard.minimum_sample_experiments == 2
    assert scorecard.direction_accuracy == 1.0
    assert scorecard.mean_absolute_effect_error == pytest.approx(0.01)
    assert any("small_experiment_history" in warning for warning in scorecard.warnings)
