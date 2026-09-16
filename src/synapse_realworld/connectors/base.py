from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.domain.events import CanonicalEvent, SourceSnapshot


class ConnectorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConnectorBatch(ConnectorModel):
    source_id: str
    connector_name: str
    events: tuple[CanonicalEvent, ...]
    snapshot: SourceSnapshot | None = None
    warnings: tuple[str, ...] = ()
    metadata: dict[str, object] = Field(default_factory=dict)


class SourceConnector(Protocol):
    connector_name: str

    def extract(self) -> ConnectorBatch: ...


def event_types(batch: ConnectorBatch) -> tuple[str, ...]:
    return tuple(sorted({event.event_type for event in batch.events}))


def materialize_events(events: Iterable[CanonicalEvent]) -> tuple[CanonicalEvent, ...]:
    return tuple(events)
