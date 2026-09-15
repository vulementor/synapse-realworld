from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from synapse_realworld.domain.events import CanonicalEvent


def load_events_jsonl(path: str | Path) -> tuple[CanonicalEvent, ...]:
    events: list[CanonicalEvent] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
                events.append(CanonicalEvent.model_validate(payload))
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"invalid canonical event at line {line_number}") from exc
    return tuple(events)


def write_events_jsonl(path: str | Path, events: Iterable[CanonicalEvent]) -> int:
    count = 0
    with Path(path).open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")
            count += 1
    return count
