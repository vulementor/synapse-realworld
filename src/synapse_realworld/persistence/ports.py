from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Protocol

from synapse_realworld.domain.events import CanonicalEvent, SourceSnapshot


class EventStore(Protocol):
    def append_events(self, events: Iterable[CanonicalEvent]) -> tuple[int, int]:
        """Append events and return `(inserted, duplicates)` counts."""

    def list_events(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        event_type: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
    ) -> Sequence[CanonicalEvent]: ...

    def count_events(self) -> int: ...


class SnapshotStore(Protocol):
    def record_snapshot(self, snapshot: SourceSnapshot) -> bool:
        """Persist a source snapshot. Returns False when already present."""

    def list_snapshots(self, *, source_id: str | None = None) -> Sequence[SourceSnapshot]: ...
