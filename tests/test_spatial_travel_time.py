from datetime import datetime, timezone
from uuid import UUID

from synapse_realworld.spatial import (
    DepartureBucket,
    HouseholdAnchorObservation,
    HouseholdCommuteProvider,
    TemporalHouseholdAnchorIndex,
    TemporalTravelTimeIndex,
    TravelMode,
    TravelTimeObservation,
)

HH_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
UNIT_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _time(day: int) -> datetime:
    return datetime(2026, 9, day, 7, 30, tzinfo=timezone.utc)


def test_temporal_commute_provider_uses_latest_valid_observation() -> None:
    index = TemporalTravelTimeIndex(
        (
            TravelTimeObservation(
                origin_anchor_id="VSIP-III",
                destination_anchor_id="LAA",
                mode=TravelMode.MOTORBIKE,
                departure_bucket=DepartureBucket.AM_PEAK,
                travel_time_min=31,
                reliability_p90_min=42,
                observed_at=_time(1),
                valid_from=_time(1),
                source_id="routing:test:v1",
            ),
            TravelTimeObservation(
                origin_anchor_id="VSIP-III",
                destination_anchor_id="LAA",
                mode=TravelMode.MOTORBIKE,
                departure_bucket=DepartureBucket.AM_PEAK,
                travel_time_min=27,
                reliability_p90_min=36,
                observed_at=_time(10),
                valid_from=_time(10),
                source_id="routing:test:v2",
            ),
        )
    )
    provider = HouseholdCommuteProvider(
        travel_times=index,
        household_origin_anchors={HH_ID: "VSIP-III"},
        unit_destination_anchors={UNIT_ID: "LAA"},
    )

    assert provider(HH_ID, UNIT_ID, _time(5)) == 31
    assert provider(HH_ID, UNIT_ID, _time(12)) == 27
    assert provider(UUID(int=3), UNIT_ID, _time(12)) is None


def test_future_workplace_anchor_does_not_leak_into_past_decision() -> None:
    travel_times = TemporalTravelTimeIndex(
        (
            TravelTimeObservation(
                origin_anchor_id="OLD-WORK",
                destination_anchor_id="LAA",
                mode=TravelMode.MOTORBIKE,
                departure_bucket=DepartureBucket.AM_PEAK,
                travel_time_min=35,
                observed_at=_time(1),
                valid_from=_time(1),
                source_id="routing:test",
            ),
            TravelTimeObservation(
                origin_anchor_id="NEW-WORK",
                destination_anchor_id="LAA",
                mode=TravelMode.MOTORBIKE,
                departure_bucket=DepartureBucket.AM_PEAK,
                travel_time_min=18,
                observed_at=_time(10),
                valid_from=_time(10),
                source_id="routing:test",
            ),
        )
    )
    anchors = TemporalHouseholdAnchorIndex(
        (
            HouseholdAnchorObservation(
                household_id=HH_ID,
                anchor_id="OLD-WORK",
                observed_at=_time(1),
                source_id="crm:old",
            ),
            HouseholdAnchorObservation(
                household_id=HH_ID,
                anchor_id="NEW-WORK",
                observed_at=_time(10),
                source_id="crm:new",
            ),
        )
    )
    provider = HouseholdCommuteProvider(
        travel_times=travel_times,
        household_anchor_index=anchors,
        unit_destination_anchors={UNIT_ID: "LAA"},
    )

    assert provider(HH_ID, UNIT_ID, _time(5)) == 35
    assert provider(HH_ID, UNIT_ID, _time(12)) == 18
