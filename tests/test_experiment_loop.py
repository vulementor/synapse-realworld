from datetime import datetime, timezone
from uuid import UUID

import pytest

from synapse_realworld.experiments import (
    AssignmentMethod,
    ExperimentDefinition,
    ExperimentObservation,
    ExperimentPrediction,
    FileExperimentRegistry,
    evaluate_experiment,
)

MODEL_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


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
        source_snapshot_id="snapshot:test",
    )


def _observation(
    experiment_id: UUID,
    *,
    variant: str,
    successes: int,
    trials: int,
    key: str,
) -> ExperimentObservation:
    return ExperimentObservation(
        experiment_id=experiment_id,
        variant=variant,
        metric_name="laa_choice_rate",
        successes=successes,
        trials=trials,
        observed_at=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
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

    with pytest.raises(ValueError, match="already locked"):
        registry.lock_prediction(
            prediction.model_copy(update={"effect_p50": 0.12})
        )

    evaluation = evaluate_experiment(
        definition=definition,
        prediction=registry.get_prediction(definition.experiment_id),
        observations=registry.list_observations(definition.experiment_id),
    )
    assert evaluation.control.rate == 0.20
    assert evaluation.treatment.rate == 0.30
    assert evaluation.observed_effect == pytest.approx(0.10)
    assert evaluation.observed_within_predicted_interval is True
    assert evaluation.prediction_direction_correct is True
    assert evaluation.causal_interpretation_allowed is True
    assert evaluation.minimum_sample_reached is True


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
