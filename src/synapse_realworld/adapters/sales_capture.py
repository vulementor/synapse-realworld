from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from synapse_realworld.domain.events import CanonicalEvent


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    if not normalized:
        raise ValueError("captured_at is required")
    return datetime.fromisoformat(normalized)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or stripped.lower() in {"unknown", "auto"}:
        return None
    return stripped


def _stable_row_key(row: dict[str, str]) -> str:
    canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sales_capture_row_to_events(
    row: dict[str, str],
    *,
    source_id: str = "laa-sales-capture",
) -> tuple[CanonicalEvent, ...]:
    captured_at = _parse_datetime(row.get("captured_at", ""))
    household_id = _clean(row.get("household_id"))
    party_id = _clean(row.get("party_id"))
    entity_type = "household" if household_id is not None else "party"
    entity_id = household_id or party_id
    if entity_id is None:
        raise ValueError("sales capture row requires household_id or party_id")

    row_key = _stable_row_key(row)
    events: list[CanonicalEvent] = []

    qualification_fields = (
        "purchase_purpose",
        "household_size_band",
        "children_band",
        "household_income_band",
        "liquid_capital_band",
        "max_monthly_payment_band",
        "purchase_horizon",
        "workplace_zone",
        "spouse_workplace_zone",
        "stated_max_travel_min",
        "preferred_product_type",
        "shortlisted_unit_code",
        "competitor_mentioned",
    )
    qualification = {
        field: value
        for field in qualification_fields
        if (value := _clean(row.get(field))) is not None
    }
    if qualification:
        events.append(
            CanonicalEvent(
                event_type="qualification_observed",
                entity_type=entity_type,
                entity_id=entity_id,
                occurred_at=captured_at,
                source_id=source_id,
                source_event_key=f"{row_key}:qualification",
                payload=qualification,
            )
        )

    stage = _clean(row.get("decision_stage"))
    if stage is not None:
        payload: dict[str, object] = {"stage": stage}
        outside_option = _clean(row.get("outside_option"))
        if outside_option is not None:
            payload["outside_option"] = outside_option
        next_action = _clean(row.get("next_action"))
        if next_action is not None:
            payload["next_action"] = next_action
        next_action_date = _clean(row.get("next_action_date"))
        if next_action_date is not None:
            payload["next_action_date"] = next_action_date
        events.append(
            CanonicalEvent(
                event_type="decision_stage_observed",
                entity_type=entity_type,
                entity_id=entity_id,
                occurred_at=captured_at,
                source_id=source_id,
                source_event_key=f"{row_key}:stage",
                payload=payload,
            )
        )

    for index in (1, 2):
        reason = _clean(row.get(f"reason_{index}"))
        direction = _clean(row.get(f"reason_{index}_direction"))
        if reason is None:
            continue
        events.append(
            CanonicalEvent(
                event_type="reason_observed",
                entity_type=entity_type,
                entity_id=entity_id,
                occurred_at=captured_at,
                source_id=source_id,
                source_event_key=f"{row_key}:reason:{index}",
                payload={
                    "reason_code": reason,
                    "direction": direction or "unknown",
                    "evidence_type": "explicit",
                },
            )
        )

    return tuple(events)


def load_sales_capture_csv(
    path: str | Path,
    *,
    source_id: str = "laa-sales-capture",
) -> tuple[CanonicalEvent, ...]:
    events: list[CanonicalEvent] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            events.extend(sales_capture_row_to_events(dict(row), source_id=source_id))
    return tuple(events)


def iter_sales_capture_rows(path: str | Path) -> Iterable[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        yield from (dict(row) for row in csv.DictReader(handle))
