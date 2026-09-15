from datetime import datetime, timezone
from uuid import UUID

from synapse_realworld.behaviour import (
    CalibrationExample,
    MultinomialLogitCalibrator,
    UtilityWeights,
    build_calibration_diagnostics,
)
from synapse_realworld.domain.enums import InventoryState, ProductType, PurchasePurpose
from synapse_realworld.domain.models import ChoiceAlternative, Household, Offer, Unit

PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")


def _alternative(code: str, price: float) -> ChoiceAlternative:
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
        monthly_payment_est=15_000_000,
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


def test_bootstrap_diagnostics_include_uncertainty_and_segments() -> None:
    cheap = _alternative("CHEAP", 1_000_000_000)
    expensive = _alternative("EXPENSIVE", 2_500_000_000)
    examples = tuple(
        CalibrationExample(
            household=Household(
                purchase_purpose=(
                    PurchasePurpose.OWN_STAY if index % 2 == 0 else PurchasePurpose.INVESTMENT
                ),
                preferred_product_type=ProductType.TOWNHOUSE,
                max_monthly_payment_million=30,
            ),
            alternatives=(cheap, expensive),
            selected_alternative_id="CHEAP",
        )
        for index in range(8)
    )
    zero_weights = UtilityWeights(
        price_per_billion=0,
        monthly_payment_per_10m=0,
        commute_per_10min=0,
        product_match=0,
        affordability_breach=0,
        investor_shophouse_bonus=0,
        own_stay_garden_bonus=0,
        outside_option_base=0,
    )
    calibrator = MultinomialLogitCalibrator(max_epochs=200)
    fitted = calibrator.fit(examples, initial_weights=zero_weights)
    diagnostics = build_calibration_diagnostics(
        examples=examples,
        bootstrap_examples=examples,
        weights=fitted.weights,
        calibrator=calibrator,
        bootstrap_samples=5,
        seed=7,
    )

    assert diagnostics.coefficient_intervals["price_per_billion"].bootstrap_samples == 5
    assert diagnostics.baseline.uniform_log_loss > 0
    assert diagnostics.baseline.model_log_loss < diagnostics.baseline.uniform_log_loss
    assert set(diagnostics.segment_metrics) == {"investment", "own_stay"}
    assert any(warning.startswith("small_training_sample") for warning in diagnostics.warnings)
