from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.behaviour import BaselineUtilityModel, UtilityWeights
from synapse_realworld.population import PopulationGenerator
from synapse_realworld.registry import ModelStatus, RegisteredModel
from synapse_realworld.simulation.engine import RealWorldSimulator
from synapse_realworld.simulation.models import Scenario, SimulationResult


class UncertaintyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QuantileSummary(UncertaintyModel):
    mean: float
    p05: float
    p50: float
    p95: float
    minimum: float
    maximum: float
    samples: int = Field(gt=0)


class ScenarioUncertaintyResult(UncertaintyModel):
    scenario_id: str
    parameter_source: str
    model_artifact_id: UUID | None = None
    model_status: str | None = None
    population_version: str
    population_size_per_run: int = Field(gt=0)
    parameter_samples: int = Field(gt=0)
    replications_per_parameter: int = Field(gt=0)
    run_count: int = Field(gt=0)
    point_estimate: SimulationResult
    laa_share: QuantileSummary
    outside_option_share: QuantileSummary
    choice_share: dict[str, QuantileSummary]
    segment_laa_share: dict[str, QuantileSummary]
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("quantile summary requires at least one value")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return ordered[lower_index] * (1 - fraction) + ordered[upper_index] * fraction


def summarize(values: Iterable[float]) -> QuantileSummary:
    materialized = [float(value) for value in values]
    if not materialized:
        raise ValueError("quantile summary requires at least one value")
    return QuantileSummary(
        mean=sum(materialized) / len(materialized),
        p05=_percentile(materialized, 0.05),
        p50=_percentile(materialized, 0.50),
        p95=_percentile(materialized, 0.95),
        minimum=min(materialized),
        maximum=max(materialized),
        samples=len(materialized),
    )


def _simulator_with_weights(
    base: RealWorldSimulator,
    *,
    weights: dict[str, float],
    population_generator: PopulationGenerator,
    model_version: str,
) -> RealWorldSimulator:
    behaviour_model = BaselineUtilityModel(UtilityWeights(**weights))
    behaviour_model.model_version = model_version
    return RealWorldSimulator(
        choice_set_factory=base.choice_set_factory,
        population_generator=population_generator,
        behaviour_model=behaviour_model,
        as_of=base.as_of,
        input_snapshot_id=base.input_snapshot_id,
        code_commit_sha=base.code_commit_sha,
    )


def simulate_scenario_uncertainty(
    *,
    base_simulator: RealWorldSimulator,
    scenario: Scenario,
    population_generator: PopulationGenerator,
    parameter_samples: Iterable[dict[str, float]],
    central_weights: dict[str, float],
    parameter_source: str,
    population_size: int = 5000,
    seed: int = 42,
    replications_per_parameter: int = 1,
    model_artifact_id: UUID | None = None,
    model_status: str | None = None,
    warnings: Iterable[str] = (),
) -> ScenarioUncertaintyResult:
    samples = tuple(dict(item) for item in parameter_samples)
    if not samples:
        raise ValueError("scenario uncertainty requires bootstrap parameter samples")
    if population_size <= 0:
        raise ValueError("population_size must be positive")
    if replications_per_parameter <= 0:
        raise ValueError("replications_per_parameter must be positive")

    point_simulator = _simulator_with_weights(
        base_simulator,
        weights=central_weights,
        population_generator=population_generator,
        model_version=f"{parameter_source}:point",
    )
    point_estimate = point_simulator.simulate(
        scenario,
        population_size=population_size,
        seed=seed,
    )

    runs: list[SimulationResult] = []
    for sample_index, weights in enumerate(samples):
        simulator = _simulator_with_weights(
            base_simulator,
            weights=weights,
            population_generator=population_generator,
            model_version=f"{parameter_source}:bootstrap:{sample_index}",
        )
        for replication in range(replications_per_parameter):
            # Common random numbers: every parameter vector sees the same population
            # and random stream for a given replication, reducing Monte Carlo noise.
            run_seed = seed + replication
            runs.append(
                simulator.simulate(
                    scenario,
                    population_size=population_size,
                    seed=run_seed,
                )
            )

    alternative_ids = sorted({key for run in runs for key in run.choice_share})
    choice_summaries = {
        alternative_id: summarize(
            run.choice_share.get(alternative_id, 0.0) for run in runs
        )
        for alternative_id in alternative_ids
    }

    sample_household = population_generator.generate(1, seed=seed)[0]
    laa_ids = {
        alternative.alternative_id
        for alternative in base_simulator.choice_set_factory(sample_household)
        if alternative.alternative_type == "laa_unit"
    }
    segments = sorted({segment for run in runs for segment in run.segment_choice_share})
    segment_laa_share = {
        segment: summarize(
            sum(
                run.segment_choice_share.get(segment, {}).get(alternative_id, 0.0)
                for alternative_id in laa_ids
            )
            for run in runs
        )
        for segment in segments
    }

    return ScenarioUncertaintyResult(
        scenario_id=scenario.scenario_id,
        parameter_source=parameter_source,
        model_artifact_id=model_artifact_id,
        model_status=model_status,
        population_version=population_generator.population_version,
        population_size_per_run=population_size,
        parameter_samples=len(samples),
        replications_per_parameter=replications_per_parameter,
        run_count=len(runs),
        point_estimate=point_estimate,
        laa_share=summarize(run.laa_share for run in runs),
        outside_option_share=summarize(run.outside_option_share for run in runs),
        choice_share=choice_summaries,
        segment_laa_share=segment_laa_share,
        diagnostics={
            "common_random_numbers": True,
            "laa_alternative_ids": sorted(laa_ids),
        },
        warnings=tuple(dict.fromkeys(str(item) for item in warnings)),
    )


def simulate_registered_model_uncertainty(
    *,
    registered_model: RegisteredModel,
    base_simulator: RealWorldSimulator,
    scenario: Scenario,
    population_generator: PopulationGenerator,
    population_size: int = 5000,
    seed: int = 42,
    replications_per_parameter: int = 1,
    allow_unapproved: bool = False,
) -> ScenarioUncertaintyResult:
    if registered_model.status != ModelStatus.APPROVED and not allow_unapproved:
        raise ValueError(
            "scenario simulation requires an approved model unless allow_unapproved=True"
        )
    artifact = registered_model.artifact
    raw_samples = artifact.diagnostics.get("bootstrap_parameter_samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("registered model has no bootstrap parameter samples")
    parameter_samples = tuple(
        {str(key): float(value) for key, value in sample.items()}
        for sample in raw_samples
        if isinstance(sample, dict)
    )
    if not parameter_samples:
        raise ValueError("registered model bootstrap parameter samples are invalid")

    diagnostic_warnings = artifact.diagnostics.get("warnings", [])
    warnings = [str(item) for item in diagnostic_warnings]
    if registered_model.status != ModelStatus.APPROVED:
        warnings.append(f"unapproved_model:{registered_model.status.value}")

    return simulate_scenario_uncertainty(
        base_simulator=base_simulator,
        scenario=scenario,
        population_generator=population_generator,
        parameter_samples=parameter_samples,
        central_weights=artifact.parameters,
        parameter_source=f"artifact:{artifact.artifact_id}",
        population_size=population_size,
        seed=seed,
        replications_per_parameter=replications_per_parameter,
        model_artifact_id=artifact.artifact_id,
        model_status=registered_model.status.value,
        warnings=warnings,
    )
