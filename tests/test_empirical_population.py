from uuid import UUID

from synapse_realworld.domain.enums import ProductType, PurchasePurpose
from synapse_realworld.domain.models import Household
from synapse_realworld.population import (
    EmpiricalPopulationGenerator,
    diagnose_population,
    fit_empirical_population_profile,
)


def _household(
    household_id: str,
    purpose: PurchasePurpose,
    workplace: str,
    capital: float,
) -> Household:
    return Household(
        household_id=UUID(household_id),
        purchase_purpose=purpose,
        household_size_band="3-4",
        children_band="1",
        income_midpoint_million=65,
        liquid_capital_million=capital,
        max_monthly_payment_million=20,
        purchase_horizon_days=90,
        workplace_zone=workplace,
        commute_tolerance_min=30,
        preferred_product_type=ProductType.TOWNHOUSE,
        profile_confidence=0.9,
    )


def test_empirical_population_removes_source_ids_and_preserves_joint_prototypes() -> None:
    source = (
        _household(
            "11111111-1111-1111-1111-111111111111",
            PurchasePurpose.OWN_STAY,
            "VSIP III",
            1500,
        ),
        _household(
            "22222222-2222-2222-2222-222222222222",
            PurchasePurpose.INVESTMENT,
            "Nam Tan Uyen",
            2500,
        ),
    )
    profile = fit_empirical_population_profile(source, name="test-population")
    assert profile.source_households == 2
    assert "household_id" not in profile.prototypes[0].model_dump()

    generator = EmpiricalPopulationGenerator(profile)
    first = generator.generate(2000, seed=7)
    second = generator.generate(2000, seed=7)
    assert [item.household_id for item in first] == [item.household_id for item in second]
    source_ids = {item.household_id for item in source}
    assert not source_ids.intersection(item.household_id for item in first)

    allowed_pairs = {
        (PurchasePurpose.OWN_STAY, "VSIP III", 1500.0),
        (PurchasePurpose.INVESTMENT, "Nam Tan Uyen", 2500.0),
    }
    assert {
        (item.purchase_purpose, item.workplace_zone, item.liquid_capital_million)
        for item in first
    }.issubset(allowed_pairs)

    diagnostics = diagnose_population(profile=profile, synthetic=first)
    assert diagnostics.synthetic_households == 2000
    assert diagnostics.max_total_variation_distance < 0.1
    assert any("very_small_population_sample" in warning for warning in diagnostics.warnings)
