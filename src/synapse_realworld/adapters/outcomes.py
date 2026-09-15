from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

from synapse_realworld.domain.events import CanonicalEvent


def _stable_key(row: dict[str, str]) -> str:
    canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def outcome_row_to_event(
    row: dict[str, str],
    *,
    source_id: str = "laa-decision-outcomes",
) -> CanonicalEvent:
    occurred_at = datetime.fromisoformat(row["occurred_at"].strip().replace("Z", "+00:00"))
    household_id = row["household_id"].strip()
    if not household_id:
        raise ValueError("outcome row requires household_id")
    source_record_id = row.get("source_record_id", "").strip() or _stable_key(row)
    payload = {
        "outcome_type": row["outcome_type"].strip(),
        "unit_code": row.get("unit_code", "").strip() or None,
        "outside_option": row.get("outside_option", "").strip() or None,
        "stage": row.get("stage", "").strip() or None,
        "verified": row.get("verified", "true").strip().lower() in {"1", "true", "yes", "y"},
    }
    return CanonicalEvent(
        event_type="decision_outcome_observed",
        entity_type="household",
        entity_id=household_id,
        occurred_at=occurred_at,
        source_id=source_id,
        source_event_key=source_record_id,
        payload=payload,
    )


def load_outcomes_csv(
    path: str | Path,
    *,
    source_id: str = "laa-decision-outcomes",
) -> tuple[CanonicalEvent, ...]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return tuple(
            outcome_row_to_event(dict(row), source_id=source_id)
            for row in csv.DictReader(handle)
        )
