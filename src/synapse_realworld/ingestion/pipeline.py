from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import datetime, timezone

from synapse_realworld.domain.events import CanonicalEvent, SourceSnapshot
from synapse_realworld.ingestion.models import IngestionResult
from synapse_realworld.persistence.ports import EventStore, SnapshotStore


class EventIngestor:
    def __init__(
        self,
        event_store: EventStore,
        snapshot_store: SnapshotStore | None = None,
    ) -> None:
        self.event_store = event_store
        self.snapshot_store = snapshot_store

    def ingest(
        self,
        *,
        source_id: str,
        events: Iterable[CanonicalEvent],
        snapshot: SourceSnapshot | None = None,
    ) -> IngestionResult:
        materialized = tuple(events)
        mismatched = [event.source_id for event in materialized if event.source_id != source_id]
        if mismatched:
            raise ValueError("all events must match the ingestion source_id")

        inserted, duplicates = self.event_store.append_events(materialized)
        snapshot_recorded = False
        if snapshot is not None:
            if snapshot.source_id != source_id:
                raise ValueError("snapshot source_id must match ingestion source_id")
            if self.snapshot_store is None:
                raise ValueError("snapshot_store is required when snapshot is provided")
            snapshot_recorded = self.snapshot_store.record_snapshot(snapshot)

        return IngestionResult(
            source_id=source_id,
            received=len(materialized),
            inserted=inserted,
            duplicates=duplicates,
            snapshot_recorded=snapshot_recorded,
        )


def build_snapshot(
    *,
    source_id: str,
    content: bytes,
    record_count: int,
    captured_at: datetime | None = None,
    schema_version: str = "1",
    metadata: dict[str, object] | None = None,
) -> SourceSnapshot:
    return SourceSnapshot(
        source_id=source_id,
        captured_at=captured_at or datetime.now(timezone.utc),
        content_hash=hashlib.sha256(content).hexdigest(),
        record_count=record_count,
        schema_version=schema_version,
        metadata=metadata or {},
    )
