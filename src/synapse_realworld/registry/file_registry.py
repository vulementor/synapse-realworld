from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from synapse_realworld.registry.models import (
    ModelArtifact,
    ModelDecision,
    ModelStatus,
    RegisteredModel,
)

ALLOWED_TRANSITIONS: dict[ModelStatus, set[ModelStatus]] = {
    ModelStatus.CANDIDATE: {
        ModelStatus.VALIDATED,
        ModelStatus.REJECTED,
        ModelStatus.ARCHIVED,
    },
    ModelStatus.VALIDATED: {
        ModelStatus.APPROVED,
        ModelStatus.REJECTED,
        ModelStatus.ARCHIVED,
    },
    ModelStatus.APPROVED: {ModelStatus.ARCHIVED},
    ModelStatus.REJECTED: {ModelStatus.ARCHIVED},
    ModelStatus.ARCHIVED: set(),
}


class FileModelRegistry:
    """Small append-only registry suitable for local runs and CI.

    Production deployments may implement the same `ModelRegistry` protocol in
    PostgreSQL/object storage. Artifacts are immutable JSON documents and
    governance decisions are append-only JSONL records.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.artifacts_dir = self.root / "artifacts"
        self.decisions_dir = self.root / "decisions"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.decisions_dir.mkdir(parents=True, exist_ok=True)

    def _artifact_path(self, artifact_id: UUID) -> Path:
        return self.artifacts_dir / f"{artifact_id}.json"

    def _decision_path(self, artifact_id: UUID) -> Path:
        return self.decisions_dir / f"{artifact_id}.jsonl"

    def register(self, artifact: ModelArtifact) -> bool:
        path = self._artifact_path(artifact.artifact_id)
        if path.exists():
            existing = ModelArtifact.model_validate_json(path.read_text(encoding="utf-8"))
            if existing.content_hash != artifact.content_hash:
                raise ValueError("artifact_id already exists with different content")
            return False
        path.write_text(
            json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return True

    def decide(self, decision: ModelDecision) -> None:
        registered = self.get(decision.artifact_id)
        if registered is None:
            raise ValueError("cannot decide on an unregistered model artifact")
        if decision.status == ModelStatus.CANDIDATE:
            raise ValueError("candidate is the implicit initial status, not a governance decision")
        allowed = ALLOWED_TRANSITIONS[registered.status]
        if decision.status not in allowed:
            raise ValueError(
                f"invalid model status transition: {registered.status.value} -> "
                f"{decision.status.value}"
            )
        path = self._decision_path(decision.artifact_id)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(decision.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")

    def _decisions(self, artifact_id: UUID) -> tuple[ModelDecision, ...]:
        path = self._decision_path(artifact_id)
        if not path.exists():
            return ()
        decisions: list[ModelDecision] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    decisions.append(ModelDecision.model_validate_json(line))
        # The decision file is append-only, so file order is the governance order.
        # Do not re-sort by timestamp: two sequential decisions can legitimately
        # share the same clock timestamp on platforms with coarse timer resolution.
        return tuple(decisions)

    def get(self, artifact_id: UUID) -> RegisteredModel | None:
        path = self._artifact_path(artifact_id)
        if not path.exists():
            return None
        artifact = ModelArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        decisions = self._decisions(artifact_id)
        latest = decisions[-1] if decisions else None
        return RegisteredModel(
            artifact=artifact,
            status=latest.status if latest else ModelStatus.CANDIDATE,
            latest_decision=latest,
        )

    def list_models(self, *, model_name: str | None = None) -> tuple[RegisteredModel, ...]:
        models: list[RegisteredModel] = []
        for path in sorted(self.artifacts_dir.glob("*.json")):
            registered = self.get(UUID(path.stem))
            if registered is None:
                continue
            if model_name is not None and registered.artifact.model_name != model_name:
                continue
            models.append(registered)
        return tuple(
            sorted(
                models,
                key=lambda item: (item.artifact.created_at, str(item.artifact.artifact_id)),
            )
        )
