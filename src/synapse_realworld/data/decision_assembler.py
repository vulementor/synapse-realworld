from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from uuid import UUID

from synapse_realworld.data.choice_set import TemporalChoiceSetBuilder
from synapse_realworld.domain.enums import DecisionStage, OutsideOption
from synapse_realworld.domain.events import CanonicalEvent
from synapse_realworld.domain.identity import analytics_uuid
from synapse_realworld.domain.models import ChoiceAlternative, ChoiceEvent

CommuteProvider = Callable[[UUID, UUID, datetime], float | None]

OUTSIDE_ALTERNATIVE_IDS = {
    OutsideOption.COMPETITOR_PROJECT.value: "OUT-COMPETITOR",
    OutsideOption.LAND_HOUSE.value: "OUT-LAND-HOUSE",
    OutsideOption.CONTINUE_RENTING.value: "OUT-RENT",
    OutsideOption.POSTPONED.value: "OUT-POSTPONE",
    OutsideOption.NO_PURCHASE.value: "OUT-NO-PURCHASE",
}

OUTCOME_OUTSIDE_OPTIONS = {
    "selected_competitor": OutsideOption.COMPETITOR_PROJECT.value,
    "selected_land_house": OutsideOption.LAND_HOUSE.value,
    "continue_renting": OutsideOption.CONTINUE_RENTING.value,
    "postponed": OutsideOption.POSTPONED.value,
    "no_purchase": OutsideOption.NO_PURCHASE.value,
    "lost": OutsideOption.NO_PURCHASE.value,
}

OUTCOME_STAGE = {
    "site_tour": DecisionStage.SITE_TOUR,
    "revisit": DecisionStage.SHORTLIST,
    "hold": DecisionStage.NEGOTIATION,
    "booking": DecisionStage.BOOKING,
    "deposit": DecisionStage.FINAL,
    "contract": DecisionStage.FINAL,
    "cancel": DecisionStage.FINAL,
    "lost": DecisionStage.FINAL,
    "postponed": DecisionStage.FINAL,
    "selected_competitor": DecisionStage.FINAL,
    "selected_land_house": DecisionStage.FINAL,
    "continue_renting": DecisionStage.FINAL,
    "no_purchase": DecisionStage.FINAL,
}


class HistoricalDecisionAssembler:
    def __init__(
        self,
        choice_set_builder: TemporalChoiceSetBuilder,
        *,
        commute_provider: CommuteProvider | None = None,
    ) -> None:
        self.choice_set_builder = choice_set_builder
        self.commute_provider = commute_provider

    def _add_commute(
        self,
        household_id: UUID,
        occurred_at: datetime,
        alternatives: tuple[ChoiceAlternative, ...],
    ) -> tuple[ChoiceAlternative, ...]:
        if self.commute_provider is None:
            return alternatives
        enriched: list[ChoiceAlternative] = []
        for alternative in alternatives:
            if alternative.unit is None:
                enriched.append(alternative)
                continue
            commute = self.commute_provider(
                household_id,
                alternative.unit.unit_id,
                occurred_at,
            )
            enriched.append(alternative.model_copy(update={"commute_min": commute}))
        return tuple(enriched)

    @staticmethod
    def _selected_alternative_id(event: CanonicalEvent) -> str | None:
        unit_code = event.payload.get("unit_code")
        if unit_code:
            return str(unit_code)
        outside_option = event.payload.get("outside_option")
        if not outside_option:
            outside_option = OUTCOME_OUTSIDE_OPTIONS.get(str(event.payload.get("outcome_type", "")))
        if outside_option:
            try:
                return OUTSIDE_ALTERNATIVE_IDS[str(outside_option)]
            except KeyError as exc:
                raise ValueError(f"unknown outside option: {outside_option}") from exc
        return None

    @staticmethod
    def _stage(event: CanonicalEvent) -> DecisionStage:
        raw_stage = event.payload.get("stage")
        if raw_stage:
            return DecisionStage(str(raw_stage))
        outcome_type = str(event.payload.get("outcome_type", ""))
        return OUTCOME_STAGE.get(outcome_type, DecisionStage.FINAL)

    def assemble(
        self,
        events: Iterable[CanonicalEvent],
        *,
        verified_only: bool = True,
    ) -> tuple[ChoiceEvent, ...]:
        decisions: list[ChoiceEvent] = []
        for event in sorted(events, key=lambda item: item.occurred_at):
            if event.event_type != "decision_outcome_observed":
                continue
            if verified_only and not bool(event.payload.get("verified", False)):
                continue

            household_id = analytics_uuid(event.entity_id, namespace="household")
            alternatives = self.choice_set_builder.build(as_of=event.occurred_at)
            alternatives = self._add_commute(household_id, event.occurred_at, alternatives)
            selected = self._selected_alternative_id(event)
            available_ids = {alternative.alternative_id for alternative in alternatives}
            if selected is not None and selected not in available_ids:
                raise ValueError(
                    f"selected alternative {selected!r} was unavailable at {event.occurred_at.isoformat()}"
                )

            decisions.append(
                ChoiceEvent(
                    household_id=household_id,
                    occurred_at=event.occurred_at,
                    stage=self._stage(event),
                    alternatives=alternatives,
                    selected_alternative_id=selected,
                    source_id=f"{event.source_id}:{event.source_event_key}",
                )
            )
        return tuple(decisions)
