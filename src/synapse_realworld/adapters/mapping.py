from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.domain.events import CanonicalEvent


class FieldRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_field: str
    target_field: str
    required: bool = False
    default: Any = None


class EventMappingSpec(BaseModel):
    """Declarative mapping from a raw connector record into one canonical event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    event_type: str
    entity_type: str
    entity_id_field: str
    occurred_at_field: str
    source_event_key_field: str | None = None
    schema_version: str = "1"
    fields: tuple[FieldRule, ...] = Field(default_factory=tuple)


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("event timestamp must be a datetime or ISO-8601 string")
    return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))


def _stable_record_key(record: dict[str, Any]) -> str:
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def map_record_to_event(record: dict[str, Any], spec: EventMappingSpec) -> CanonicalEvent:
    raw_entity_id = record.get(spec.entity_id_field)
    if raw_entity_id is None or not str(raw_entity_id).strip():
        raise ValueError(f"missing entity id field: {spec.entity_id_field}")

    payload: dict[str, Any] = {}
    for rule in spec.fields:
        value = record.get(rule.source_field, rule.default)
        if rule.required and (value is None or value == ""):
            raise ValueError(f"missing required source field: {rule.source_field}")
        if value is not None:
            payload[rule.target_field] = value.strip() if isinstance(value, str) else value

    source_event_key: str
    if spec.source_event_key_field is not None:
        raw_key = record.get(spec.source_event_key_field)
        if raw_key is None or not str(raw_key).strip():
            raise ValueError(f"missing source event key field: {spec.source_event_key_field}")
        source_event_key = str(raw_key)
    else:
        source_event_key = _stable_record_key(record)

    return CanonicalEvent(
        event_type=spec.event_type,
        entity_type=spec.entity_type,
        entity_id=str(raw_entity_id),
        occurred_at=_parse_datetime(record.get(spec.occurred_at_field)),
        source_id=spec.source_id,
        source_event_key=source_event_key,
        payload=payload,
        schema_version=spec.schema_version,
    )
