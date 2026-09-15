from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from synapse_realworld.domain.models import ChoiceEvent
from synapse_realworld.domain.temporal import FeatureObservation


@dataclass(frozen=True, slots=True)
class DecisionRow:
    choice_event: ChoiceEvent
    features: dict[str, object]
    feature_sources: dict[str, str]


class DecisionDatasetBuilder:
    """Build leakage-safe feature snapshots for historical choice events."""

    def build(
        self,
        *,
        events: Iterable[ChoiceEvent],
        observations: Iterable[FeatureObservation],
    ) -> tuple[DecisionRow, ...]:
        by_household: dict[UUID, list[FeatureObservation]] = defaultdict(list)
        for observation in observations:
            by_household[observation.household_id].append(observation)

        rows: list[DecisionRow] = []
        for event in sorted(events, key=lambda item: item.occurred_at):
            latest: dict[str, FeatureObservation] = {}
            for observation in by_household.get(event.household_id, []):
                # Future observations are deliberately ignored to prevent target leakage.
                if observation.observed_at > event.occurred_at:
                    continue
                current = latest.get(observation.feature_name)
                if current is None or observation.observed_at > current.observed_at:
                    latest[observation.feature_name] = observation

            rows.append(
                DecisionRow(
                    choice_event=event,
                    features={name: obs.value for name, obs in latest.items()},
                    feature_sources={name: obs.source_id for name, obs in latest.items()},
                )
            )
        return tuple(rows)
