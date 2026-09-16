from datetime import datetime, timezone
from uuid import UUID

import pytest

from synapse_realworld.registry import (
    FileModelRegistry,
    ModelArtifact,
    ModelDecision,
    ModelStatus,
)


def _artifact() -> ModelArtifact:
    return ModelArtifact(
        model_name="laa-buyer-choice",
        model_version="v0.3-test",
        model_family="multinomial_logit",
        code_commit_sha="test-sha",
        dataset_snapshot_id="snapshot:test",
        training_window_start=datetime(2026, 9, 1, tzinfo=timezone.utc),
        training_window_end=datetime(2026, 9, 10, tzinfo=timezone.utc),
        feature_schema_version="decision-features-v0.3",
        parameters={"price_per_billion": -0.5},
        train_metrics={"log_loss": 0.8},
        holdout_metrics={"log_loss": 0.9},
    )


def test_model_registry_enforces_governance_transitions(tmp_path) -> None:
    registry = FileModelRegistry(tmp_path / "registry")
    artifact = _artifact()
    assert registry.register(artifact) is True
    assert registry.register(artifact) is False
    assert registry.get(artifact.artifact_id).status == ModelStatus.CANDIDATE

    with pytest.raises(ValueError, match="invalid model status transition"):
        registry.decide(
            ModelDecision(
                artifact_id=artifact.artifact_id,
                status=ModelStatus.APPROVED,
                decided_by="test",
                reason="cannot skip validation",
            )
        )

    registry.decide(
        ModelDecision(
            artifact_id=artifact.artifact_id,
            status=ModelStatus.VALIDATED,
            decided_by="data-lead",
            reason="holdout reviewed",
        )
    )
    assert registry.get(artifact.artifact_id).status == ModelStatus.VALIDATED

    registry.decide(
        ModelDecision(
            artifact_id=artifact.artifact_id,
            status=ModelStatus.APPROVED,
            decided_by="business-owner",
            reason="approved for decision support",
        )
    )
    registered = registry.get(artifact.artifact_id)
    assert registered.status == ModelStatus.APPROVED
    assert len(registry.list_models(model_name="laa-buyer-choice")) == 1

    registry.decide(
        ModelDecision(
            artifact_id=artifact.artifact_id,
            status=ModelStatus.ARCHIVED,
            decided_by="data-lead",
            reason="superseded by later model",
        )
    )
    assert registry.get(artifact.artifact_id).status == ModelStatus.ARCHIVED


def test_registry_uses_append_order_when_decision_timestamps_match(tmp_path) -> None:
    registry = FileModelRegistry(tmp_path / "registry")
    artifact = _artifact()
    registry.register(artifact)
    same_time = datetime(2026, 9, 16, 5, 35, tzinfo=timezone.utc)

    registry.decide(
        ModelDecision(
            decision_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            artifact_id=artifact.artifact_id,
            status=ModelStatus.VALIDATED,
            decided_at=same_time,
            decided_by="data-lead",
            reason="validated first",
        )
    )
    registry.decide(
        ModelDecision(
            decision_id=UUID("00000000-0000-0000-0000-000000000001"),
            artifact_id=artifact.artifact_id,
            status=ModelStatus.APPROVED,
            decided_at=same_time,
            decided_by="business-owner",
            reason="approved second",
        )
    )

    registered = registry.get(artifact.artifact_id)
    assert registered.status == ModelStatus.APPROVED
    assert registered.latest_decision.status == ModelStatus.APPROVED
