from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from synapse_realworld.connectors.base import ConnectorBatch
from synapse_realworld.domain.events import CanonicalEvent
from synapse_realworld.ingestion import build_snapshot


class ConnectorConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CsvEventProfile(ConnectorConfigModel):
    name: str
    event_type: str
    entity_type: str
    entity_id_column: str
    occurred_at_column: str
    source_event_key_column: str | None = None
    payload_columns: tuple[str, ...] = ()
    required_columns: tuple[str, ...] = ()
    pseudonymize_entity_id: bool = False
    schema_version: str = "1"


def pseudonymous_key(value: str, *, namespace: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("cannot pseudonymize an empty identifier")
    digest = hashlib.sha256(f"{namespace}|{normalized}".encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    if not normalized:
        raise ValueError("event timestamp is required")
    parsed = datetime.fromisoformat(normalized)
    if parsed.utcoffset() is None:
        raise ValueError("event timestamp must include timezone information")
    return parsed


def _stable_row_key(row: dict[str, str]) -> str:
    canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class GenericCsvConnector:
    connector_name = "generic-csv-v1"

    def __init__(
        self,
        path: str | Path,
        *,
        source_id: str,
        profile: CsvEventProfile,
    ) -> None:
        self.path = Path(path)
        self.source_id = source_id
        self.profile = profile

    def extract(self) -> ConnectorBatch:
        content = self.path.read_bytes()
        events: list[CanonicalEvent] = []
        warnings: list[str] = []
        row_count = 0
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = tuple(reader.fieldnames or ())
            required = {
                self.profile.entity_id_column,
                self.profile.occurred_at_column,
                *self.profile.required_columns,
            }
            if self.profile.source_event_key_column:
                required.add(self.profile.source_event_key_column)
            missing = sorted(required - set(columns))
            if missing:
                raise ValueError(f"CSV missing required columns: {', '.join(missing)}")

            for index, raw_row in enumerate(reader, start=2):
                row_count += 1
                row = {str(key): (value or "") for key, value in dict(raw_row).items()}
                entity_raw = row[self.profile.entity_id_column].strip()
                if not entity_raw:
                    warnings.append(f"row:{index}:missing_entity_id")
                    continue
                entity_id = (
                    pseudonymous_key(entity_raw, namespace=self.source_id)
                    if self.profile.pseudonymize_entity_id
                    else entity_raw
                )
                occurred_at = _parse_datetime(row[self.profile.occurred_at_column])
                if self.profile.source_event_key_column:
                    event_key = row[self.profile.source_event_key_column].strip()
                    if not event_key:
                        warnings.append(f"row:{index}:missing_source_event_key")
                        continue
                else:
                    event_key = _stable_row_key(row)
                payload = {
                    column: row[column].strip()
                    for column in self.profile.payload_columns
                    if column in row and row[column].strip()
                }
                events.append(
                    CanonicalEvent(
                        event_type=self.profile.event_type,
                        entity_type=self.profile.entity_type,
                        entity_id=entity_id,
                        occurred_at=occurred_at,
                        source_id=self.source_id,
                        source_event_key=event_key,
                        payload=payload,
                        schema_version=self.profile.schema_version,
                    )
                )

        snapshot = build_snapshot(
            source_id=self.source_id,
            content=content,
            record_count=row_count,
            schema_version=self.profile.schema_version,
            metadata={
                "path": self.path.name,
                "connector": self.connector_name,
                "profile": self.profile.name,
            },
        )
        return ConnectorBatch(
            source_id=self.source_id,
            connector_name=self.connector_name,
            events=tuple(events),
            snapshot=snapshot,
            warnings=tuple(warnings),
            metadata={"profile": self.profile.name, "rows": row_count},
        )
