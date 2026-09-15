from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable
from uuid import UUID

from synapse_realworld.data.quality import DataQualityError, QualityIssue, validate_choice_set
from synapse_realworld.domain.enums import InventoryState, OutsideOption
from synapse_realworld.domain.models import ChoiceAlternative, Offer
from synapse_realworld.domain.temporal import UnitVersion


class TemporalChoiceSetBuilder:
    """Reconstruct a buyer's feasible alternatives at an exact historical time."""

    def __init__(
        self,
        *,
        unit_versions: Iterable[UnitVersion],
        offers: Iterable[Offer],
    ) -> None:
        self.unit_versions = tuple(unit_versions)
        self.offers = tuple(offers)

    def _active_unit_versions(self, as_of: datetime) -> dict[UUID, UnitVersion]:
        grouped: dict[UUID, list[UnitVersion]] = defaultdict(list)
        for version in self.unit_versions:
            if version.active_at(as_of):
                grouped[version.unit.unit_id].append(version)

        result: dict[UUID, UnitVersion] = {}
        for unit_id, versions in grouped.items():
            versions.sort(key=lambda item: item.effective_from, reverse=True)
            if len(versions) > 1 and versions[0].effective_from == versions[1].effective_from:
                raise DataQualityError(
                    [
                        QualityIssue(
                            "ambiguous_unit_version",
                            f"unit {unit_id} has overlapping versions with the same effective_from",
                        )
                    ]
                )
            result[unit_id] = versions[0]
        return result

    def _active_offer_by_unit(self, as_of: datetime) -> dict[UUID, Offer]:
        grouped: dict[UUID, list[Offer]] = defaultdict(list)
        for offer in self.offers:
            if offer.unit_id is None:
                continue
            if offer.effective_from > as_of:
                continue
            if offer.effective_to is not None and as_of >= offer.effective_to:
                continue
            grouped[offer.unit_id].append(offer)

        result: dict[UUID, Offer] = {}
        for unit_id, offers in grouped.items():
            offers.sort(key=lambda item: item.effective_from, reverse=True)
            if len(offers) > 1 and offers[0].effective_from == offers[1].effective_from:
                raise DataQualityError(
                    [
                        QualityIssue(
                            "ambiguous_offer",
                            f"unit {unit_id} has ambiguous active offers",
                        )
                    ]
                )
            result[unit_id] = offers[0]
        return result

    def build(
        self,
        *,
        as_of: datetime,
        commute_by_unit: dict[UUID, float] | None = None,
        include_default_outside_options: bool = True,
    ) -> tuple[ChoiceAlternative, ...]:
        commute_by_unit = commute_by_unit or {}
        unit_versions = self._active_unit_versions(as_of)
        offers = self._active_offer_by_unit(as_of)
        alternatives: list[ChoiceAlternative] = []

        for unit_id, version in sorted(
            unit_versions.items(), key=lambda item: item[1].unit.unit_code
        ):
            unit = version.unit
            if unit.inventory_state != InventoryState.AVAILABLE:
                continue
            offer = offers.get(unit_id)
            if offer is None:
                continue
            alternatives.append(
                ChoiceAlternative(
                    alternative_id=unit.unit_code,
                    alternative_type="laa_unit",
                    unit=unit,
                    offer=offer,
                    commute_min=commute_by_unit.get(unit_id),
                    availability_confirmed=True,
                )
            )

        if include_default_outside_options:
            alternatives.extend(_default_outside_options())

        validate_choice_set(alternatives, as_of=as_of, fail_closed=True)
        return tuple(alternatives)


def _default_outside_options() -> tuple[ChoiceAlternative, ...]:
    return (
        ChoiceAlternative(
            alternative_id="OUT-COMPETITOR",
            alternative_type="competitor_project",
            outside_option=OutsideOption.COMPETITOR_PROJECT,
        ),
        ChoiceAlternative(
            alternative_id="OUT-LAND-HOUSE",
            alternative_type="land_house",
            outside_option=OutsideOption.LAND_HOUSE,
        ),
        ChoiceAlternative(
            alternative_id="OUT-RENT",
            alternative_type="continue_renting",
            outside_option=OutsideOption.CONTINUE_RENTING,
        ),
        ChoiceAlternative(
            alternative_id="OUT-POSTPONE",
            alternative_type="postponed",
            outside_option=OutsideOption.POSTPONED,
        ),
        ChoiceAlternative(
            alternative_id="OUT-NO-PURCHASE",
            alternative_type="no_purchase",
            outside_option=OutsideOption.NO_PURCHASE,
        ),
    )
