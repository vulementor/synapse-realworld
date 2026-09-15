from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RegistryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelStatus(StrEnum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ModelArtifact(RegistryModel):
    artifact_id: UUID = Field(default_factory=uuid4)
    model_name: str
    model_version: str
    model_family: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    code_commit_sha: str
    dataset_snapshot_id: str
    training_window_start: datetime | None = None
    training_window_end: datetime | None = None
    feature_schema_version: str
    parameters: dict[str, float]
    train_metrics: dict[str, float]
    holdout_metrics: dict[str, float]
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> ModelArtifact:
        for field_name in (
            "model_name",
            "model_version",
            "model_family",
            "code_commit_sha",
            "dataset_snapshot_id",
            "feature_schema_version",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} is required")
        if self.training_window_start and self.training_window_end:
            if self.training_window_start >= self.training_window_end:
                raise ValueError("training_window_start must be before training_window_end")
        return self

    @property
    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"artifact_id", "created_at"})
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ModelDecision(RegistryModel):
    decision_id: UUID = Field(default_factory=uuid4)
    artifact_id: UUID
    status: ModelStatus
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decided_by: str
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_decision(self) -> ModelDecision:
        if not self.decided_by.strip():
            raise ValueError("decided_by is required")
        if not self.reason.strip():
            raise ValueError("reason is required")
        return self


class RegisteredModel(RegistryModel):
    artifact: ModelArtifact
    status: ModelStatus
    latest_decision: ModelDecision | None = None
