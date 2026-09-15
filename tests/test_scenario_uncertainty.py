from dataclasses import asdict

import pytest

from synapse_realworld.behaviour import UtilityWeights
from synapse_realworld.domain.enums import ProductType, PurchasePurpose
from synapse_realworld.domain.models import Household
from synapse_realworld.population import (
    EmpiricalPopulationGenerator,
    fit_empirical_population_profile,
)
from synapse_realworld.projects.laa import build_laa_demo_world
from synapse_realworld.registry import ModelArtifact, ModelStatus, RegisteredModel
from synapse_realworld.simulation import Scenario, simulate_registered_model_uncertainty


def _population() -> EmpiricalPopulationGenerator:
    source = (
        Household(
            purchase_purpose=PurchasePurpose.OWN_STAY,
            household_size_band="3-4",
            children_band="1",
            liquid_capital_million=1500,
            max_monthly_payment_million=20,
            workplace_zone="VSIP III",
            preferred_product_type=ProductType.TOWNHOUSE,
            profile_confidence=0.9,
        ),
        Household(
            purchase_purpose=PurchasePurpose.INVESTMENT,
            household_size_band="2",
            children_band="0",
            liquid_capital_million=2500,
            max_monthly_payment_million=30,
            workplace_zone="Nam Tan Uyen",
            preferred_product_type=ProductType.SHOPHOUSE,
            profile_confidence=0.9,
        ),
    )
    return EmpiricalPopulationGenerator(
        fit_empirical_population_profile(source, name="uncertainty-test")
    )


def _artifact() -> ModelArtifact:
    central = asdict(UtilityWeights())
    lower_price = {**central, "price_per_billion": -0.35}
    higher_price = {**central, "price_per_billion": -0.90}
    return ModelArtifact(
        model_name="laa-buyer-choice",
        model_version="v0.4-test",
        model_family="multinomial_logit",
        code_commit_sha="test",
        dataset_snapshot_id="snapshot:test",
        feature_schema_version="decision-features-v0.4",
        parameters=central,
        train_metrics={"log_loss": 0.8},
        holdout_metrics={"log_loss": 0.9},
        diagnostics={
            "bootstrap_parameter_samples": [lower_price, higher_price],
            "warnings": ["synthetic_test"],
        },
    )


def test_uncertainty_requires_approved_model_by_default() -> None:
    artifact = _artifact()
    registered = RegisteredModel(
        artifact=artifact,
        status=ModelStatus.VALIDATED,
    )
    with pytest.raises(ValueError, match="approved model"):
        simulate_registered_model_uncertainty(
            registered_model=registered,
            base_simulator=build_laa_demo_world(seed=42),
            scenario=Scenario(scenario_id="price-test", price_change_pct=0.05),
            population_generator=_population(),
            population_size=50,
        )


def test_uncertainty_returns_quantiles_from_bootstrap_parameter_vectors() -> None:
    artifact = _artifact()
    registered = RegisteredModel(
        artifact=artifact,
        status=ModelStatus.APPROVED,
    )
    result = simulate_registered_model_uncertainty(
        registered_model=registered,
        base_simulator=build_laa_demo_world(seed=42),
        scenario=Scenario(scenario_id="price-test", price_change_pct=0.05),
        population_generator=_population(),
        population_size=200,
        seed=11,
    )

    assert result.model_artifact_id == artifact.artifact_id
    assert result.model_status == "approved"
    assert result.parameter_samples == 2
    assert result.run_count == 2
    assert result.laa_share.p05 <= result.laa_share.p50 <= result.laa_share.p95
    assert result.outside_option_share.p05 <= result.outside_option_share.p50
    assert result.population_version.startswith("empirical:uncertainty-test:")
    assert "synthetic_test" in result.warnings
