from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from uuid import UUID

import duckdb

from synapse_realworld.domain.events import CanonicalEvent, SourceSnapshot


class DuckDBStore:
    """Local analytical store for deterministic backfill and experimentation.

    DuckDB is the default local engine. Production deployments can implement the
    same persistence ports with PostgreSQL/PostGIS without changing domain code.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.connection = duckdb.connect(self.path)
        self._initialize()

    def _initialize(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS canonical_events (
                event_id VARCHAR PRIMARY KEY,
                dedupe_key VARCHAR UNIQUE NOT NULL,
                event_type VARCHAR NOT NULL,
                entity_type VARCHAR NOT NULL,
                entity_id VARCHAR NOT NULL,
                occurred_at TIMESTAMPTZ NOT NULL,
                source_id VARCHAR NOT NULL,
                source_event_key VARCHAR NOT NULL,
                payload_json VARCHAR NOT NULL,
                payload_hash VARCHAR NOT NULL,
                schema_version VARCHAR NOT NULL,
                ingested_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS source_snapshots (
                snapshot_id VARCHAR PRIMARY KEY,
                source_id VARCHAR NOT NULL,
                captured_at TIMESTAMPTZ NOT NULL,
                content_hash VARCHAR NOT NULL,
                record_count BIGINT NOT NULL,
                schema_version VARCHAR NOT NULL,
                metadata_json VARCHAR NOT NULL,
                UNIQUE(source_id, content_hash, schema_version)
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_event_entity "
            "ON canonical_events(entity_type, entity_id, occurred_at)"
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_event_type_time "
            "ON canonical_events(event_type, occurred_at)"
        )

    def append_events(self, events: Iterable[CanonicalEvent]) -> tuple[int, int]:
        inserted = 0
        duplicates = 0
        for event in events:
            exists = self.connection.execute(
                "SELECT 1 FROM canonical_events WHERE dedupe_key = ? LIMIT 1",
                [event.dedupe_key],
            ).fetchone()
            if exists is not None:
                duplicates += 1
                continue
            self.connection.execute(
                """
                INSERT INTO canonical_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    str(event.event_id),
                    event.dedupe_key,
                    event.event_type,
                    event.entity_type,
                    event.entity_id,
                    event.occurred_at,
                    event.source_id,
                    event.source_event_key,
                    json.dumps(event.payload, ensure_ascii=False, sort_keys=True, default=str),
                    event.payload_hash,
                    event.schema_version,
                    event.ingested_at,
                ],
            )
            inserted += 1
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
                clauses.append(f"{column} = ?")
                params.append(value)
        if occurred_from is not None:
            clauses.append("occurred_at >= ?")
            params.append(occurred_from)
        if occurred_to is not None:
            clauses.append("occurred_at < ?")
            params.append(occurred_to)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.connection.execute(
            "SELECT event_id, event_type, entity_type, entity_id, occurred_at, "
            "source_id, source_event_key, payload_json, schema_version, ingested_at "
            f"FROM canonical_events{where} ORDER BY occurred_at, event_id",
            params,
        ).fetchall()
        return tuple(
            CanonicalEvent(
                event_id=UUID(row[0]),
                event_type=row[1],
                entity_type=row[2],
                entity_id=row[3],
                occurred_at=row[4],
                source_id=row[5],
                source_event_key=row[6],
                payload=json.loads(row[7]),
                schema_version=row[8],
                ingested_at=row[9],
            )
            for row in rows
        )

    def count_events(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM canonical_events").fetchone()[0])

    def record_snapshot(self, snapshot: SourceSnapshot) -> bool:
        exists = self.connection.execute(
            """
            SELECT 1 FROM source_snapshots
            WHERE source_id = ? AND content_hash = ? AND schema_version = ? LIMIT 1
            """,
            [snapshot.source_id, snapshot.content_hash, snapshot.schema_version],
        ).fetchone()
        if exists is not None:
            return False
        self.connection.execute(
            """
            INSERT INTO source_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(snapshot.snapshot_id),
                snapshot.source_id,
                snapshot.captured_at,
                snapshot.content_hash,
                snapshot.record_count,
                snapshot.schema_version,
                json.dumps(snapshot.metadata, ensure_ascii=False, sort_keys=True, default=str),
            ],
        )
        return True

    def list_snapshots(self, *, source_id: str | None = None) -> Sequence[SourceSnapshot]:
        if source_id is None:
            rows = self.connection.execute(
                """
                SELECT snapshot_id, source_id, captured_at, content_hash, record_count,
                       schema_version, metadata_json
                FROM source_snapshots ORDER BY captured_at, snapshot_id
                """
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT snapshot_id, source_id, captured_at, content_hash, record_count,
                       schema_version, metadata_json
                FROM source_snapshots WHERE source_id = ? ORDER BY captured_at, snapshot_id
                """,
                [source_id],
            ).fetchall()
        return tuple(
            SourceSnapshot(
                snapshot_id=UUID(row[0]),
                source_id=row[1],
                captured_at=row[2],
                content_hash=row[3],
                record_count=row[4],
                schema_version=row[5],
                metadata=json.loads(row[6]),
            )
            for row in rows
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> DuckDBStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
