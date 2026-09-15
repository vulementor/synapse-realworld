from datetime import datetime, timezone
from uuid import UUID

from synapse_realworld.behaviour import CalibrationExample, MultinomialLogitCalibrator, UtilityWeights
from synapse_realworld.domain.enums import InventoryState, OutsideOption, ProductType, PurchasePurpose
from synapse_realworld.domain.models import ChoiceAlternative, Household, Offer, Unit

PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")


def _unit(code: str, price: float) -> ChoiceAlternative:
    unit = Unit(
        project_id=PROJECT_ID,
        unit_code=code,
        product_type=ProductType.TOWNHOUSE,
        inventory_state=InventoryState.AVAILABLE,
    )
    offer = Offer(
        unit_id=unit.unit_id,
        list_price=price,
        payment_plan_code="TEST",
        monthly_payment_est=20_000_000,
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source_id="test",
    )
    return ChoiceAlternative(
        alternative_id=code,
        alternative_type="laa_unit",
        unit=unit,
        offer=offer,
        commute_min=20,
    )


def test_calibrator_learns_price_direction() -> None:
    cheap = _unit("CHEAP", 1_000_000_000)
    expensive = _unit("EXPENSIVE", 2_500_000_000)
    outside = ChoiceAlternative(
        alternative_id="OUTSIDE",
        alternative_type="no_purchase",
        outside_option=OutsideOption.NO_PURCHASE,
    )
    households = [
        Household(
            purchase_purpose=PurchasePurpose.OWN_STAY,
            preferred_product_type=ProductType.TOWNHOUSE,
            max_monthly_payment_million=30,
        )
        for _ in range(40)
    ]
    examples = [
        CalibrationExample(
            household=household,
            alternatives=(cheap, expensive, outside),
            selected_alternative_id="CHEAP",
        )
        for household in households
    ]

    zeros = UtilityWeights(
        price_per_billion=0,
        monthly_payment_per_10m=0,
        commute_per_10min=0,
        product_match=0,
        affordability_breach=0,
        investor_shophouse_bonus=0,
        own_stay_garden_bonus=0,
        outside_option_base=0,
    )
    result = MultinomialLogitCalibrator(max_epochs=500).fit(
        examples,
        initial_weights=zeros,
    )

    assert result.weights["price_per_billion"] < 0
    assert result.metrics.top1_accuracy == 1.0
    assert result.metrics.log_loss < 0.5
