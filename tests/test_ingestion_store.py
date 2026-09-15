from datetime import datetime, timezone

from synapse_realworld.domain.events import CanonicalEvent
from synapse_realworld.ingestion import EventIngestor, build_snapshot
from synapse_realworld.persistence import DuckDBStore


def test_duckdb_ingestion_is_idempotent(tmp_path) -> None:
    event = CanonicalEvent(
        event_type="qualification_observed",
        entity_type="household",
        entity_id="hh-001",
        occurred_at=datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc),
        source_id="crm-test",
        source_event_key="lead-001:qualification",
        payload={"purchase_purpose": "own_stay"},
    )
    content = b"same export bytes"
    snapshot = build_snapshot(
        source_id="crm-test",
        content=content,
        record_count=1,
        captured_at=datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc),
    )

    db_path = tmp_path / "synapse.duckdb"
    with DuckDBStore(db_path) as store:
        ingestor = EventIngestor(store, store)
        first = ingestor.ingest(source_id="crm-test", events=[event], snapshot=snapshot)
        second = ingestor.ingest(source_id="crm-test", events=[event], snapshot=snapshot)

        assert first.inserted == 1
        assert first.duplicates == 0
        assert first.snapshot_recorded is True
        assert second.inserted == 0
        assert second.duplicates == 1
        assert second.snapshot_recorded is False
        assert store.count_events() == 1
        stored = store.list_events(entity_id="hh-001")
        assert len(stored) == 1
        assert stored[0].payload["purchase_purpose"] == "own_stay"
        assert len(store.list_snapshots(source_id="crm-test")) == 1
