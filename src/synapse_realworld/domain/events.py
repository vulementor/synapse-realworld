from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EventModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CanonicalEvent(EventModel):
    """Append-only observation emitted by a source adapter.

    `source_event_key` must be stable for the same source record. It is the
    idempotency boundary used during repeated CRM/SAP/CSV backfills.
    """

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    entity_type: str
    entity_id: str
    occurred_at: datetime
    source_id: str
    source_event_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = "1"
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_required_text(self) -> CanonicalEvent:
        for name in ("event_type", "entity_type", "entity_id", "source_id", "source_event_key"):
            value = getattr(self, name)
            if not value.strip():
                raise ValueError(f"{name} is required")
        return self

    @property
    def dedupe_key(self) -> str:
        raw = f"{self.source_id}|{self.source_event_key}|{self.schema_version}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @property
    def payload_hash(self) -> str:
        body = json.dumps(self.payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


class SourceSnapshot(EventModel):
    snapshot_id: UUID = Field(default_factory=uuid4)
    source_id: str
    captured_at: datetime
    content_hash: str
    record_count: int = Field(ge=0)
    schema_version: str = "1"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source(self) -> SourceSnapshot:
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        if not self.content_hash.strip():
            raise ValueError("content_hash is required")
        return self
