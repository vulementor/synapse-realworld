from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from synapse_realworld.domain.models import Unit


class TemporalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UnitVersion(TemporalModel):
    version_id: UUID = Field(default_factory=uuid4)
    unit: Unit
    effective_from: datetime
    effective_to: datetime | None = None
    source_id: str

    @model_validator(mode="after")
    def validate_range(self) -> UnitVersion:
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be later than effective_from")
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        return self

    def active_at(self, timestamp: datetime) -> bool:
        return self.effective_from <= timestamp and (
            self.effective_to is None or timestamp < self.effective_to
        )


class FeatureObservation(TemporalModel):
    observation_id: UUID = Field(default_factory=uuid4)
    household_id: UUID
    feature_name: str
    value: Any
    observed_at: datetime
    source_id: str
    confidence: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_source(self) -> FeatureObservation:
        if not self.feature_name.strip():
            raise ValueError("feature_name is required")
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        return self
