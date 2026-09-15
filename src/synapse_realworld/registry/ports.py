from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from synapse_realworld.registry.models import ModelArtifact, ModelDecision, RegisteredModel


class ModelRegistry(Protocol):
    def register(self, artifact: ModelArtifact) -> bool:
        """Register an immutable model artifact. False means identical artifact exists."""

    def decide(self, decision: ModelDecision) -> None:
        """Append a governance decision for an existing model artifact."""

    def get(self, artifact_id: UUID) -> RegisteredModel | None: ...

    def list_models(self, *, model_name: str | None = None) -> Sequence[RegisteredModel]: ...
