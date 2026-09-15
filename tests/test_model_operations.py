from datetime import datetime, timezone
from uuid import UUID

from synapse_realworld.experiments import (
    AssignmentMethod,
    ExperimentDefinition,
    ExperimentObservation,
    ModelExperimentScorecard,
    assess_experiment_quality,
)
from synapse_realworld.modelops import (
    RecalibrationPolicy,
    RecalibrationState,
    assess_recalibration_need,
)

MODEL_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
EXPERIMENT_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
OBSERVED_AT = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _observation(variant: str, trials: int, successes: int, key: str) -> ExperimentObservation:
    return ExperimentObservation(
        experiment_id=EXPERIMENT_ID,
        variant=variant,
        metric_name="laa_choice_rate",
        successes=successes,
        trials=trials,
        observed_at=OBSERVED_AT,
        source_id="test-results",
        source_event_key=key,
    )


def test_experiment_qa_accepts_balanced_randomized_allocation() -> None:
    definition = ExperimentDefinition(
        experiment_id=EXPERIMENT_ID,
        name="Balanced randomized test",
        hypothesis="Treatment increases choice rate",
        created_by="test",
        minimum_trials_per_variant=50,
    )
    assessment = assess_experiment_quality(
        definition=definition,
        observations=(
            _observation("control", 100, 20, "c"),
            _observation("treatment", 100, 28, "t"),
        ),
    )
    assert assessment.sample_ratio_mismatch is False
    assert assessment.sample_ratio_zscore == 0.0
    assert assessment.minimum_sample_reached is True
    assert assessment.causal_design_declared is True
    assert assessment.warnings == ()


def test_experiment_qa_flags_sample_ratio_mismatch() -> None:
    definition = ExperimentDefinition(
        experiment_id=EXPERIMENT_ID,
        name="Imbalanced randomized test",
        hypothesis="Treatment increases choice rate",
        created_by="test",
    )
    assessment = assess_experiment_quality(
        definition=definition,
        observations=(
            _observation("control", 50, 10, "c"),
            _observation("treatment", 150, 42, "t"),
        ),
    )
    assert assessment.sample_ratio_mismatch is True
    assert abs(assessment.sample_ratio_zscore) > 3.29
    assert "sample_ratio_mismatch" in assessment.warnings


def test_experiment_qa_preserves_noncausal_boundary() -> None:
    definition = ExperimentDefinition(
        experiment_id=EXPERIMENT_ID,
        name="Observed comparison",
        hypothesis="Observed treatment group has a higher rate",
        assignment_method=AssignmentMethod.OBSERVATIONAL,
        created_by="test",
    )
    assessment = assess_experiment_quality(
        definition=definition,
        observations=(
            _observation("control", 100, 20, "c"),
            _observation("treatment", 100, 28, "t"),
        ),
    )
    assert assessment.causal_design_declared is False
    assert any("non_randomized_assignment" in item for item in assessment.warnings)


def _scorecard(
    *,
    experiments: int,
    causal: int,
    mae: float,
    coverage: float,
    direction: float,
) -> ModelExperimentScorecard:
    return ModelExperimentScorecard(
        model_artifact_id=MODEL_ID,
        evaluated_experiments=experiments,
        causal_experiments=causal,
        minimum_sample_experiments=experiments,
        mean_absolute_effect_error=mae,
        predicted_interval_coverage_rate=coverage,
        direction_accuracy=direction,
        minimum_sample_rate=1.0,
        causal_experiment_rate=causal / experiments if experiments else None,
    )


def test_recalibration_assessment_requires_sufficient_prospective_evidence() -> None:
    assessment = assess_recalibration_need(
        _scorecard(experiments=2, causal=2, mae=0.01, coverage=1.0, direction=1.0)
    )
    assert assessment.state == RecalibrationState.INSUFFICIENT_EVIDENCE
    assert assessment.human_review_required is True
    assert assessment.automatic_retraining_allowed is False
    assert "insufficient_evaluated_experiments" in assessment.reasons
    assert "insufficient_causal_experiments" in assessment.reasons


def test_recalibration_assessment_monitors_healthy_model() -> None:
    assessment = assess_recalibration_need(
        _scorecard(experiments=6, causal=5, mae=0.02, coverage=0.90, direction=0.85)
    )
    assert assessment.state == RecalibrationState.MONITOR
    assert assessment.reasons == ()
    assert assessment.automatic_retraining_allowed is False


def test_recalibration_assessment_recommends_human_review_when_thresholds_fail() -> None:
    policy = RecalibrationPolicy(
        minimum_evaluated_experiments=5,
        minimum_causal_experiments=3,
        maximum_mean_absolute_effect_error=0.05,
        minimum_interval_coverage_rate=0.80,
        minimum_direction_accuracy=0.70,
    )
    assessment = assess_recalibration_need(
        _scorecard(experiments=6, causal=5, mae=0.08, coverage=0.60, direction=0.50),
        policy=policy,
    )
    assert assessment.state == RecalibrationState.REVIEW_RECALIBRATION
    assert set(assessment.reasons) == {
        "mean_absolute_effect_error_above_threshold",
        "prediction_interval_coverage_below_threshold",
        "effect_direction_accuracy_below_threshold",
    }
    assert assessment.human_review_required is True
    assert assessment.automatic_retraining_allowed is False
