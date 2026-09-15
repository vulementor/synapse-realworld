from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from synapse_realworld.experiments import (
    ExperimentAssignmentReceipt,
    ExperimentDefinition,
    ExperimentObservation,
    ExperimentPrediction,
    FileExperimentRegistry,
    assess_experiment_quality,
)

EXPERIMENT_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
MODEL_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PREDICTED_AT = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)


def _definition() -> ExperimentDefinition:
    return ExperimentDefinition(
        experiment_id=EXPERIMENT_ID,
        name="Assignment receipt test",
        hypothesis="Treatment increases LAA choice rate",
        created_by="test",
        minimum_trials_per_variant=50,
    )


def _prediction() -> ExperimentPrediction:
    return ExperimentPrediction(
        experiment_id=EXPERIMENT_ID,
        model_artifact_id=MODEL_ID,
        model_status="approved",
        population_version="empirical:test:1234",
        metric_name="laa_choice_rate",
        control_scenario_id="control",
        treatment_scenario_id="treatment",
        control_point_estimate=0.20,
        treatment_point_estimate=0.28,
        effect_mean=0.08,
        effect_p05=0.03,
        effect_p50=0.08,
        effect_p95=0.13,
        ensemble_samples=50,
        created_at=PREDICTED_AT,
        source_snapshot_id="snapshot:test",
    )


def _receipt(
    subject: str,
    variant: str,
    *,
    key: str,
    channel: str = "meta",
    cohort: str = "cohort-a",
    assigned_at: datetime | None = None,
) -> ExperimentAssignmentReceipt:
    return ExperimentAssignmentReceipt(
        experiment_id=EXPERIMENT_ID,
        subject_key=subject,
        variant=variant,
        assigned_at=assigned_at or PREDICTED_AT + timedelta(hours=1),
        source_id="crm-assignment",
        source_event_key=key,
        channel=channel,
        cohort=cohort,
    )


def _observation(variant: str, successes: int, key: str) -> ExperimentObservation:
    return ExperimentObservation(
        experiment_id=EXPERIMENT_ID,
        variant=variant,
        metric_name="laa_choice_rate",
        successes=successes,
        trials=100,
        observed_at=PREDICTED_AT + timedelta(days=2),
        source_id="crm-results",
        source_event_key=key,
    )


def test_assignment_registry_requires_prediction_and_blocks_cross_variant_subjects(tmp_path) -> None:
    registry = FileExperimentRegistry(tmp_path / "experiments")
    registry.create(_definition())
    receipt = _receipt("hash:subject-001", "control", key="a1")
    with pytest.raises(ValueError, match="locked prediction"):
        registry.append_assignment(receipt)

    registry.lock_prediction(_prediction())
    assert registry.append_assignment(receipt) is True
    assert registry.append_assignment(receipt) is False
    assert registry.append_assignment(
        _receipt("hash:subject-001", "control", key="a1-duplicate-source")
    ) is False
    with pytest.raises(ValueError, match="conflicting variant"):
        registry.append_assignment(
            _receipt("hash:subject-001", "treatment", key="a2")
        )
    assert len(registry.list_assignments(EXPERIMENT_ID)) == 1


def test_assignment_registry_rejects_backdated_receipt(tmp_path) -> None:
    registry = FileExperimentRegistry(tmp_path / "experiments")
    registry.create(_definition())
    registry.lock_prediction(_prediction())
    with pytest.raises(ValueError, match="predates the locked prediction"):
        registry.append_assignment(
            _receipt(
                "hash:subject-001",
                "control",
                key="backdated",
                assigned_at=PREDICTED_AT - timedelta(minutes=1),
            )
        )


def test_assignment_bucket_qa_detects_hidden_channel_imbalance() -> None:
    assignments = []
    for index in range(50):
        assignments.append(
            _receipt(
                f"hash:meta-{index}",
                "control",
                key=f"meta-{index}",
                channel="meta",
                cohort="week-1",
            )
        )
        assignments.append(
            _receipt(
                f"hash:zalo-{index}",
                "treatment",
                key=f"zalo-{index}",
                channel="zalo",
                cohort="week-1",
            )
        )

    assessment = assess_experiment_quality(
        definition=_definition(),
        observations=(
            _observation("control", 20, "control-results"),
            _observation("treatment", 28, "treatment-results"),
        ),
        assignments=assignments,
    )
    assert assessment.allocation_source == "assignment_receipts"
    assert assessment.control_assignments == 50
    assert assessment.treatment_assignments == 50
    assert assessment.sample_ratio_mismatch is False

    channel_checks = {
        item.bucket: item
        for item in assessment.allocation_buckets
        if item.bucket_type == "channel"
    }
    assert channel_checks["meta"].sample_ratio_mismatch is True
    assert channel_checks["zalo"].sample_ratio_mismatch is True
    assert any("sample_ratio_mismatch:channel:meta" == item for item in assessment.warnings)
    assert any("sample_ratio_mismatch:channel:zalo" == item for item in assessment.warnings)
