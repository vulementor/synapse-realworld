from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SpatialModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TravelMode(StrEnum):
    MOTORBIKE = "motorbike"
    CAR = "car"
    TRANSIT = "transit"
    WALK = "walk"


class DepartureBucket(StrEnum):
    AM_PEAK = "am_peak"
    MIDDAY = "midday"
    PM_PEAK = "pm_peak"
    OFFPEAK = "offpeak"


class LocationAnchor(SpatialModel):
    anchor_id: str
    anchor_type: str
    name: str | None = None
    zone_code: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def validate_anchor(self) -> LocationAnchor:
        if not self.anchor_id.strip():
            raise ValueError("anchor_id is required")
        if not self.anchor_type.strip():
            raise ValueError("anchor_type is required")
        return self


class HouseholdAnchorObservation(SpatialModel):
    household_id: UUID
    anchor_id: str
    observed_at: datetime
    source_id: str

    @model_validator(mode="after")
    def validate_text(self) -> HouseholdAnchorObservation:
        if not self.anchor_id.strip():
            raise ValueError("anchor_id is required")
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        return self


class TemporalHouseholdAnchorIndex:
    def __init__(self, observations: Iterable[HouseholdAnchorObservation]) -> None:
        self.observations = tuple(observations)

    def get(self, household_id: UUID, *, at: datetime) -> HouseholdAnchorObservation | None:
        candidates = [
            item
            for item in self.observations
            if item.household_id == household_id and item.observed_at <= at
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.observed_at)


class TravelTimeObservation(SpatialModel):
    origin_anchor_id: str
    destination_anchor_id: str
    mode: TravelMode
    departure_bucket: DepartureBucket
    travel_time_min: float = Field(gt=0)
    distance_km: float | None = Field(default=None, ge=0)
    reliability_p90_min: float | None = Field(default=None, gt=0)
    observed_at: datetime
    valid_from: datetime
    valid_to: datetime | None = None
    source_id: str

    @model_validator(mode="after")
    def validate_window(self) -> TravelTimeObservation:
        if self.valid_to is not None and self.valid_from >= self.valid_to:
            raise ValueError("valid_from must be before valid_to")
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        return self

    def active_at(self, at: datetime) -> bool:
        return self.valid_from <= at and (self.valid_to is None or at < self.valid_to)


class TemporalTravelTimeIndex:
    def __init__(self, observations: Iterable[TravelTimeObservation]) -> None:
        self.observations = tuple(observations)

    def get(
        self,
        *,
        origin_anchor_id: str,
        destination_anchor_id: str,
        at: datetime,
        mode: TravelMode = TravelMode.MOTORBIKE,
        departure_bucket: DepartureBucket = DepartureBucket.AM_PEAK,
    ) -> TravelTimeObservation | None:
        candidates = [
            item
            for item in self.observations
            if item.origin_anchor_id == origin_anchor_id
            and item.destination_anchor_id == destination_anchor_id
            and item.mode == mode
            and item.departure_bucket == departure_bucket
            and item.active_at(at)
            and item.observed_at <= at
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.observed_at)


class HouseholdCommuteProvider:
    """Leakage-safe historical commute feature provider.

    Prefer `household_anchor_index` for observed workplace changes over time.
    `household_origin_anchors` remains available for immutable/static contexts.
    Exact private home addresses are intentionally not required.
    """

    def __init__(
        self,
        *,
        travel_times: TemporalTravelTimeIndex,
        unit_destination_anchors: Mapping[UUID, str],
        household_anchor_index: TemporalHouseholdAnchorIndex | None = None,
        household_origin_anchors: Mapping[UUID, str] | None = None,
        mode: TravelMode = TravelMode.MOTORBIKE,
        departure_bucket: DepartureBucket = DepartureBucket.AM_PEAK,
    ) -> None:
        if household_anchor_index is None and household_origin_anchors is None:
            raise ValueError("a temporal or static household origin source is required")
        self.travel_times = travel_times
        self.household_anchor_index = household_anchor_index
        self.household_origin_anchors = dict(household_origin_anchors or {})
        self.unit_destination_anchors = dict(unit_destination_anchors)
        self.mode = mode
        self.departure_bucket = departure_bucket

    def _origin(self, household_id: UUID, at: datetime) -> str | None:
        if self.household_anchor_index is not None:
            observation = self.household_anchor_index.get(household_id, at=at)
            if observation is not None:
                return observation.anchor_id
        return self.household_origin_anchors.get(household_id)

    def __call__(self, household_id: UUID, unit_id: UUID, at: datetime) -> float | None:
        origin = self._origin(household_id, at)
        destination = self.unit_destination_anchors.get(unit_id)
        if origin is None or destination is None:
            return None
        observation = self.travel_times.get(
            origin_anchor_id=origin,
            destination_anchor_id=destination,
            at=at,
            mode=self.mode,
            departure_bucket=self.departure_bucket,
        )
        return observation.travel_time_min if observation is not None else None
