from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from synapse_realworld.behaviour.calibration import CalibrationExample
from synapse_realworld.data.dataset import DecisionRow
from synapse_realworld.domain.enums import ProductType, PurchasePurpose
from synapse_realworld.domain.models import Household


def _band_midpoint_million(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace(" ", "")
    if not text or text == "unknown":
        return None
    multiplier = 1000.0 if "b" in text else 1.0
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return None
    if len(numbers) >= 2:
        return sum(numbers[:2]) / 2 * multiplier
    number = numbers[0]
    if text.startswith("<"):
        return number * 0.8 * multiplier
    if text.endswith("+") or "+" in text:
        return number * 1.2 * multiplier
    return number * multiplier


def _parse_days(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or text == "unknown":
        return None
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def household_from_features(
    household_id: UUID,
    features: Mapping[str, Any],
) -> Household:
    purpose_raw = str(features.get("purchase_purpose", "unknown"))
    product_raw = features.get("preferred_product_type")
    try:
        purpose = PurchasePurpose(purpose_raw)
    except ValueError:
        purpose = PurchasePurpose.UNKNOWN
    try:
        preferred_product = ProductType(str(product_raw)) if product_raw else None
    except ValueError:
        preferred_product = None

    known_fields = sum(
        value not in {None, "", "unknown"}
        for value in (
            features.get("purchase_purpose"),
            features.get("household_size_band"),
            features.get("children_band"),
            features.get("household_income_band"),
            features.get("liquid_capital_band"),
            features.get("max_monthly_payment_band"),
            features.get("purchase_horizon"),
            features.get("workplace_zone"),
            features.get("stated_max_travel_min"),
            features.get("preferred_product_type"),
        )
    )
    profile_confidence = min(1.0, known_fields / 10)

    household_size = str(features.get("household_size_band", "unknown"))
    if household_size not in {"1", "2", "3-4", "5+", "unknown"}:
        household_size = "unknown"
    children_band = str(features.get("children_band", "unknown"))
    if children_band not in {"0", "1", "2+", "unknown"}:
        children_band = "unknown"

    return Household(
        household_id=household_id,
        purchase_purpose=purpose,
        household_size_band=household_size,
        children_band=children_band,
        income_midpoint_million=_band_midpoint_million(features.get("household_income_band")),
        liquid_capital_million=_band_midpoint_million(features.get("liquid_capital_band")),
        max_monthly_payment_million=_band_midpoint_million(
            features.get("max_monthly_payment_band")
        ),
        purchase_horizon_days=_parse_days(features.get("purchase_horizon")),
        workplace_zone=(
            str(features["workplace_zone"])
            if features.get("workplace_zone") not in {None, "", "unknown"}
            else None
        ),
        commute_tolerance_min=_parse_float(features.get("stated_max_travel_min")),
        preferred_product_type=preferred_product,
        profile_confidence=profile_confidence,
    )


def household_from_decision_row(row: DecisionRow) -> Household:
    return household_from_features(row.choice_event.household_id, row.features)


@dataclass(frozen=True, slots=True)
class TimedCalibrationExample:
    occurred_at: datetime
    example: CalibrationExample


def build_calibration_examples(
    rows: Iterable[DecisionRow],
) -> tuple[TimedCalibrationExample, ...]:
    result: list[TimedCalibrationExample] = []
    for row in rows:
        selected = row.choice_event.selected_alternative_id
        if selected is None:
            continue
        household = household_from_decision_row(row)
        result.append(
            TimedCalibrationExample(
                occurred_at=row.choice_event.occurred_at,
                example=CalibrationExample(
                    household=household,
                    alternatives=row.choice_event.alternatives,
                    selected_alternative_id=selected,
                ),
            )
        )
    return tuple(sorted(result, key=lambda item: item.occurred_at))


def temporal_holdout(
    examples: Iterable[TimedCalibrationExample],
    *,
    holdout_fraction: float = 0.2,
) -> tuple[tuple[CalibrationExample, ...], tuple[CalibrationExample, ...]]:
    if not 0 < holdout_fraction < 1:
        raise ValueError("holdout_fraction must be between 0 and 1")
    ordered = tuple(sorted(examples, key=lambda item: item.occurred_at))
    if len(ordered) < 2:
        raise ValueError("temporal holdout requires at least two examples")
    holdout_size = max(1, round(len(ordered) * holdout_fraction))
    split = len(ordered) - holdout_size
    if split <= 0:
        split = 1
    train = tuple(item.example for item in ordered[:split])
    test = tuple(item.example for item in ordered[split:])
    return train, test
