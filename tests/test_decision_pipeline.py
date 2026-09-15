from datetime import datetime, timezone
from uuid import UUID

from synapse_realworld.data.choice_set import TemporalChoiceSetBuilder
from synapse_realworld.data.dataset import DecisionDatasetBuilder
from synapse_realworld.data.decision_assembler import HistoricalDecisionAssembler
from synapse_realworld.data.projection import project_feature_observations
from synapse_realworld.data.training import build_calibration_examples, temporal_holdout
from synapse_realworld.domain.enums import InventoryState, ProductType
from synapse_realworld.domain.events import CanonicalEvent
from synapse_realworld.domain.models import Offer, Unit
from synapse_realworld.domain.temporal import UnitVersion

PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")


def _world() -> TemporalChoiceSetBuilder:
    effective = datetime(2026, 9, 1, tzinfo=timezone.utc)
    units = []
    offers = []
    for code, price in (("LK4-42", 2_000_000_000), ("LK5-04", 2_500_000_000)):
        unit = Unit(
            project_id=PROJECT_ID,
            unit_code=code,
            product_type=ProductType.TOWNHOUSE,
            inventory_state=InventoryState.AVAILABLE,
        )
        units.append(
            UnitVersion(
                unit=unit,
                effective_from=effective,
                source_id="inventory:test",
            )
        )
        offers.append(
            Offer(
                unit_id=unit.unit_id,
                list_price=price,
                payment_plan_code="PLAN-A",
                monthly_payment_est=18_000_000,
                effective_from=effective,
                source_id="offer:test",
            )
        )
    return TemporalChoiceSetBuilder(unit_versions=units, offers=offers)


def _qualification(entity_id: str, occurred_at: datetime) -> CanonicalEvent:
    return CanonicalEvent(
        event_type="qualification_observed",
        entity_type="household",
        entity_id=entity_id,
        occurred_at=occurred_at,
        source_id="crm-test",
        source_event_key=f"{entity_id}:qualification",
        payload={
            "purchase_purpose": "own_stay",
            "household_size_band": "3-4",
            "children_band": "1",
            "household_income_band": "50-80m",
            "liquid_capital_band": "1-2b",
            "max_monthly_payment_band": "15-20m",
            "purchase_horizon": "90d",
            "workplace_zone": "VSIP III",
            "stated_max_travel_min": "30",
            "preferred_product_type": "townhouse",
        },
    )


def _outcome(entity_id: str, occurred_at: datetime, unit_code: str) -> CanonicalEvent:
    return CanonicalEvent(
        event_type="decision_outcome_observed",
        entity_type="household",
        entity_id=entity_id,
        occurred_at=occurred_at,
        source_id="sap-test",
        source_event_key=f"{entity_id}:booking",
        payload={
            "outcome_type": "booking",
            "unit_code": unit_code,
            "outside_option": None,
            "stage": "booking",
            "verified": True,
        },
    )


def test_decision_pipeline_builds_temporal_training_examples() -> None:
    assembler = HistoricalDecisionAssembler(_world())
    first_time = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)
    second_time = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
    outcomes = (
        _outcome("hh-source-1", first_time, "LK4-42"),
        _outcome("hh-source-2", second_time, "LK5-04"),
    )
    decisions = assembler.assemble(outcomes)
    features = project_feature_observations(
        (
            _qualification("hh-source-1", datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)),
            _qualification("hh-source-2", datetime(2026, 9, 11, 8, 0, tzinfo=timezone.utc)),
        )
    )
    rows = DecisionDatasetBuilder().build(events=decisions, observations=features)
    timed = build_calibration_examples(rows)
    train, test = temporal_holdout(timed, holdout_fraction=0.5)

    assert len(decisions) == 2
    assert decisions[0].selected_alternative_id == "LK4-42"
    assert len(rows) == 2
    assert len(timed) == 2
    assert timed[0].example.household.liquid_capital_million == 1500
    assert timed[0].example.household.max_monthly_payment_million == 17.5
    assert len(train) == 1
    assert len(test) == 1
    assert train[0].selected_alternative_id == "LK4-42"
    assert test[0].selected_alternative_id == "LK5-04"
