from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import datetime
from uuid import UUID

from synapse_realworld.domain.events import CanonicalEvent, SourceSnapshot


class PostgresStore:
    """Production append-only store implementing the same contract as DuckDBStore.

    Install with `pip install -e '.[postgres]'`. The constructor imports psycopg
    lazily so the default local installation does not require PostgreSQL drivers.
    """

    def __init__(self, dsn: str, *, initialize: bool = True) -> None:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "PostgresStore requires the 'postgres' extra: pip install -e '.[postgres]'"
            ) from exc
        self.connection = psycopg.connect(dsn)
        if initialize:
            self._initialize()

    def _initialize(self) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS canonical_events (
                    event_id UUID PRIMARY KEY,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    occurred_at TIMESTAMPTZ NOT NULL,
                    source_id TEXT NOT NULL,
                    source_event_key TEXT NOT NULL,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    payload_hash TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    ingested_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS source_snapshots (
                    snapshot_id UUID PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    captured_at TIMESTAMPTZ NOT NULL,
                    content_hash TEXT NOT NULL,
                    record_count BIGINT NOT NULL CHECK (record_count >= 0),
                    schema_version TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    UNIQUE(source_id, content_hash, schema_version)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_canonical_events_entity_time
                ON canonical_events(entity_type, entity_id, occurred_at)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_canonical_events_type_time
                ON canonical_events(event_type, occurred_at)
                """
            )
        self.connection.commit()

    def append_events(self, events: Iterable[CanonicalEvent]) -> tuple[int, int]:
        inserted = 0
        duplicates = 0
        with self.connection.cursor() as cursor:
            for event in events:
                cursor.execute(
                    """
                    INSERT INTO canonical_events (
                        event_id, dedupe_key, event_type, entity_type, entity_id,
                        occurred_at, source_id, source_event_key, payload,
                        payload_hash, schema_version, ingested_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s
                    )
                    ON CONFLICT (dedupe_key) DO NOTHING
                    RETURNING event_id
                    """,
                    (
                        event.event_id,
                        event.dedupe_key,
                        event.event_type,
                        event.entity_type,
                        event.entity_id,
                        event.occurred_at,
                        event.source_id,
                        event.source_event_key,
                        json.dumps(event.payload, ensure_ascii=False, default=str),
                        event.payload_hash,
                        event.schema_version,
                        event.ingested_at,
                    ),
                )
                if cursor.fetchone() is None:
                    duplicates += 1
                else:
                    inserted += 1
        self.connection.commit()
        return inserted, duplicates

    def list_events(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        event_type: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
    ) -> Sequence[CanonicalEvent]:
        clauses: list[str] = []
        params: list[object] = []
        for column, value in (
            ("entity_type", entity_type),
            ("entity_id", entity_id),
            ("event_type", event_type),
        ):
            if value is not None:
                clauses.append(f"{column} = %s")
                params.append(value)
        if occurred_from is not None:
            clauses.append("occurred_at >= %s")
            params.append(occurred_from)
        if occurred_to is not None:
            clauses.append("occurred_at < %s")
            params.append(occurred_to)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            "SELECT event_id, event_type, entity_type, entity_id, occurred_at, "
            "source_id, source_event_key, payload, schema_version, ingested_at "
            f"FROM canonical_events{where} ORDER BY occurred_at, event_id"
        )
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return tuple(
            CanonicalEvent(
                event_id=UUID(str(row[0])),
                event_type=row[1],
                entity_type=row[2],
                entity_id=row[3],
                occurred_at=row[4],
                source_id=row[5],
                source_event_key=row[6],
                payload=row[7],
                schema_version=row[8],
                ingested_at=row[9],
            )
            for row in rows
        )

    def count_events(self) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM canonical_events")
            row = cursor.fetchone()
        return int(row[0])

    def record_snapshot(self, snapshot: SourceSnapshot) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO source_snapshots (
                    snapshot_id, source_id, captured_at, content_hash, record_count,
                    schema_version, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (source_id, content_hash, schema_version) DO NOTHING
                RETURNING snapshot_id
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.source_id,
                    snapshot.captured_at,
                    snapshot.content_hash,
                    snapshot.record_count,
                    snapshot.schema_version,
                    json.dumps(snapshot.metadata, ensure_ascii=False, default=str),
                ),
            )
            inserted = cursor.fetchone() is not None
        self.connection.commit()
        return inserted

    def list_snapshots(self, *, source_id: str | None = None) -> Sequence[SourceSnapshot]:
        query = (
            "SELECT snapshot_id, source_id, captured_at, content_hash, record_count, "
            "schema_version, metadata FROM source_snapshots"
        )
        params: list[object] = []
        if source_id is not None:
            query += " WHERE source_id = %s"
            params.append(source_id)
        query += " ORDER BY captured_at, snapshot_id"
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return tuple(
            SourceSnapshot(
                snapshot_id=UUID(str(row[0])),
                source_id=row[1],
                captured_at=row[2],
                content_hash=row[3],
                record_count=row[4],
                schema_version=row[5],
                metadata=row[6],
            )
            for row in rows
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> PostgresStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
