from datetime import datetime, timezone

from synapse_realworld.domain.events import CanonicalEvent
from synapse_realworld.population import fit_population_from_events


def _event(entity_id: str, day: int, workplace: str) -> CanonicalEvent:
    return CanonicalEvent(
        event_type="qualification_observed",
        entity_type="household",
        entity_id=entity_id,
        occurred_at=datetime(2026, 9, day, 8, 0, tzinfo=timezone.utc),
        source_id="crm-test",
        source_event_key=f"{entity_id}:{day}",
        payload={
            "purchase_purpose": "own_stay",
            "household_size_band": "3-4",
            "children_band": "1",
            "household_income_band": "50-80m",
            "liquid_capital_band": "1-2b",
            "max_monthly_payment_band": "15-20m",
            "purchase_horizon": "90d",
            "workplace_zone": workplace,
            "stated_max_travel_min": "30",
            "preferred_product_type": "townhouse",
        },
    )


def test_population_fit_uses_all_qualified_households_and_respects_as_of() -> None:
    events = (
        _event("hh-1", 1, "OLD-WORK"),
        _event("hh-2", 2, "VSIP III"),
        _event("hh-1", 10, "NEW-WORK"),
    )
    result = fit_population_from_events(
        events,
        profile_name="test-history",
        as_of=datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc),
        minimum_profile_confidence=0.5,
        diagnostic_population_size=500,
        seed=9,
    )

    assert result.candidate_households == 2
    assert result.included_households == 2
    assert result.excluded_low_confidence == 0
    workplaces = {prototype.workplace_zone for prototype in result.profile.prototypes}
    assert workplaces == {"OLD-WORK", "VSIP III"}
    assert "NEW-WORK" not in workplaces
    assert result.profile.population_version.startswith("empirical:test-history:")
