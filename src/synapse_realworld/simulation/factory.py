from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime

from synapse_realworld.behaviour import BaselineUtilityModel
from synapse_realworld.data.choice_set import TemporalChoiceSetBuilder
from synapse_realworld.domain.models import ChoiceAlternative, Household, Offer
from synapse_realworld.domain.temporal import UnitVersion
from synapse_realworld.population import PopulationGenerator
from synapse_realworld.simulation.engine import RealWorldSimulator
from synapse_realworld.spatial import (
    DepartureBucket,
    TemporalTravelTimeIndex,
    TravelMode,
    TravelTimeObservation,
)


def build_temporal_choice_set_factory(
    *,
    unit_versions: Iterable[UnitVersion],
    offers: Iterable[Offer],
    as_of: datetime,
    travel_times: Iterable[TravelTimeObservation] = (),
    project_anchor_id: str = "LAA",
    travel_mode: TravelMode = TravelMode.MOTORBIKE,
    departure_bucket: DepartureBucket = DepartureBucket.AM_PEAK,
) -> Callable[[Household], tuple[ChoiceAlternative, ...]]:
    builder = TemporalChoiceSetBuilder(
        unit_versions=tuple(unit_versions),
        offers=tuple(offers),
    )
    travel_index = TemporalTravelTimeIndex(tuple(travel_times))

    def choice_set(household: Household) -> tuple[ChoiceAlternative, ...]:
        alternatives = builder.build(as_of=as_of)
        if not household.workplace_zone:
            return alternatives
        travel = travel_index.get(
            origin_anchor_id=household.workplace_zone,
            destination_anchor_id=project_anchor_id,
            at=as_of,
            mode=travel_mode,
            departure_bucket=departure_bucket,
        )
        if travel is None:
            return alternatives
        enriched: list[ChoiceAlternative] = []
        for alternative in alternatives:
            if alternative.alternative_type == "laa_unit":
                enriched.append(
                    alternative.model_copy(update={"commute_min": travel.travel_time_min})
                )
            else:
                enriched.append(alternative)
        return tuple(enriched)

    return choice_set


def build_real_data_simulator(
    *,
    unit_versions: Iterable[UnitVersion],
    offers: Iterable[Offer],
    as_of: datetime,
    population_generator: PopulationGenerator,
    input_snapshot_id: str,
    travel_times: Iterable[TravelTimeObservation] = (),
    project_anchor_id: str = "LAA",
    behaviour_model: BaselineUtilityModel | None = None,
    code_commit_sha: str = "dev",
) -> RealWorldSimulator:
    choice_set_factory = build_temporal_choice_set_factory(
        unit_versions=tuple(unit_versions),
        offers=tuple(offers),
        as_of=as_of,
        travel_times=tuple(travel_times),
        project_anchor_id=project_anchor_id,
    )
    return RealWorldSimulator(
        choice_set_factory=choice_set_factory,
        population_generator=population_generator,
        behaviour_model=behaviour_model,
        as_of=as_of,
        input_snapshot_id=input_snapshot_id,
        code_commit_sha=code_commit_sha,
    )
