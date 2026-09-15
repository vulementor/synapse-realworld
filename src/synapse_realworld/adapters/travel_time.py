from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from synapse_realworld.spatial.travel_time import (
    DepartureBucket,
    TravelMode,
    TravelTimeObservation,
)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))


def load_travel_times_csv(path: str | Path) -> tuple[TravelTimeObservation, ...]:
    observations: list[TravelTimeObservation] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            observations.append(
                TravelTimeObservation(
                    origin_anchor_id=row["origin_anchor_id"],
                    destination_anchor_id=row["destination_anchor_id"],
                    mode=TravelMode(row["mode"]),
                    departure_bucket=DepartureBucket(row["departure_bucket"]),
                    travel_time_min=float(row["travel_time_min"]),
                    distance_km=(
                        float(row["distance_km"]) if row.get("distance_km") else None
                    ),
                    reliability_p90_min=(
                        float(row["reliability_p90_min"])
                        if row.get("reliability_p90_min")
                        else None
                    ),
                    observed_at=_dt(row["observed_at"]),
                    valid_from=_dt(row["valid_from"]),
                    valid_to=_dt(row["valid_to"]) if row.get("valid_to") else None,
                    source_id=row["source_id"],
                )
            )
    return tuple(observations)
