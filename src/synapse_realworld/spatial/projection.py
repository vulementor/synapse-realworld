from __future__ import annotations

from collections.abc import Iterable

from synapse_realworld.domain.events import CanonicalEvent
from synapse_realworld.domain.identity import analytics_uuid
from synapse_realworld.domain.temporal import UnitVersion
from synapse_realworld.spatial.travel_time import (
    HouseholdAnchorObservation,
    HouseholdCommuteProvider,
    TemporalHouseholdAnchorIndex,
    TemporalTravelTimeIndex,
    TravelTimeObservation,
)


def project_household_workplace_anchors(
    events: Iterable[CanonicalEvent],
) -> tuple[HouseholdAnchorObservation, ...]:
    observations: list[HouseholdAnchorObservation] = []
    for event in events:
        if event.event_type != "qualification_observed":
            continue
        workplace_zone = event.payload.get("workplace_zone")
        if workplace_zone is None:
            continue
        anchor_id = str(workplace_zone).strip()
        if not anchor_id or anchor_id.lower() == "unknown":
            continue
        observations.append(
            HouseholdAnchorObservation(
                household_id=analytics_uuid(event.entity_id, namespace="household"),
                anchor_id=anchor_id,
                observed_at=event.occurred_at,
                source_id=f"{event.source_id}:{event.source_event_key}",
            )
        )
    return tuple(observations)


def build_project_commute_provider(
    *,
    events: Iterable[CanonicalEvent],
    unit_versions: Iterable[UnitVersion],
    travel_times: Iterable[TravelTimeObservation],
    destination_anchor_id: str,
) -> HouseholdCommuteProvider:
    materialized_events = tuple(events)
    anchors = project_household_workplace_anchors(materialized_events)
    unit_destinations = {
        version.unit.unit_id: destination_anchor_id for version in tuple(unit_versions)
    }
    return HouseholdCommuteProvider(
        travel_times=TemporalTravelTimeIndex(tuple(travel_times)),
        household_anchor_index=TemporalHouseholdAnchorIndex(anchors),
        unit_destination_anchors=unit_destinations,
    )
