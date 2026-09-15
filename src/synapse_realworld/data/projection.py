from __future__ import annotations

from collections.abc import Iterable

from synapse_realworld.domain.enums import ReasonCode, ReasonDirection
from synapse_realworld.domain.events import CanonicalEvent
from synapse_realworld.domain.identity import analytics_uuid
from synapse_realworld.domain.models import ReasonObservation
from synapse_realworld.domain.temporal import FeatureObservation

FEATURE_EVENT_TYPES = {"qualification_observed", "decision_stage_observed"}
NON_MODEL_FIELDS = {"next_action", "next_action_date"}


def project_feature_observations(
    events: Iterable[CanonicalEvent],
) -> tuple[FeatureObservation, ...]:
    observations: list[FeatureObservation] = []
    for event in events:
        if event.event_type not in FEATURE_EVENT_TYPES:
            continue
        household_id = analytics_uuid(event.entity_id, namespace="household")
        for feature_name, value in event.payload.items():
            if feature_name in NON_MODEL_FIELDS:
                continue
            observations.append(
                FeatureObservation(
                    household_id=household_id,
                    feature_name=feature_name,
                    value=value,
                    observed_at=event.occurred_at,
                    source_id=f"{event.source_id}:{event.source_event_key}",
                )
            )
    return tuple(observations)


def project_reason_observations(
    events: Iterable[CanonicalEvent],
) -> tuple[ReasonObservation, ...]:
    observations: list[ReasonObservation] = []
    for event in events:
        if event.event_type != "reason_observed":
            continue
        reason_code = ReasonCode(str(event.payload.get("reason_code", "unknown")))
        raw_direction = str(event.payload.get("direction", "objection"))
        direction = (
            ReasonDirection.MOTIVATOR
            if raw_direction == ReasonDirection.MOTIVATOR.value
            else ReasonDirection.OBJECTION
        )
        observations.append(
            ReasonObservation(
                household_id=analytics_uuid(event.entity_id, namespace="household"),
                reason_code=reason_code,
                direction=direction,
                confidence=float(event.payload.get("confidence", 1.0)),
                evidence_type=str(event.payload.get("evidence_type", "explicit")),
                observed_at=event.occurred_at,
                source_ref=f"{event.source_id}:{event.source_event_key}",
            )
        )
    return tuple(observations)
