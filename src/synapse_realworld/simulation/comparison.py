from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.behaviour import BaselineUtilityModel, UtilityWeights
from synapse_realworld.population import PopulationGenerator
from synapse_realworld.registry import ModelStatus, RegisteredModel
from synapse_realworld.simulation.engine import RealWorldSimulator
from synapse_realworld.simulation.models import Scenario, SimulationResult
from synapse_realworld.simulation.uncertainty import QuantileSummary, summarize


class ComparisonModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScenarioComparisonResult(ComparisonModel):
    model_artifact_id: UUID
    model_status: str
    population_version: str
    control_scenario_id: str
    treatment_scenario_id: str
    metric_name: str = "laa_choice_rate"
    population_size_per_run: int = Field(gt=0)
    parameter_samples: int = Field(gt=0)
    replications_per_parameter: int = Field(gt=0)
    run_pairs: int = Field(gt=0)
    control_point_estimate: SimulationResult
    treatment_point_estimate: SimulationResult
    control_laa_share: QuantileSummary
    treatment_laa_share: QuantileSummary
    effect: QuantileSummary
    warnings: tuple[str, ...] = ()


def _weighted_simulator(
    base: RealWorldSimulator,
    *,
    population_generator: PopulationGenerator,
    weights: dict[str, float],
    model_version: str,
) -> RealWorldSimulator:
    behavior = BaselineUtilityModel(UtilityWeights(**weights))
    behavior.model_version = model_version
    return RealWorldSimulator(
        choice_set_factory=base.choice_set_factory,
        population_generator=population_generator,
        behaviour_model=behavior,
        as_of=base.as_of,
        input_snapshot_id=base.input_snapshot_id,
        code_commit_sha=base.code_commit_sha,
    )


def _bootstrap_samples(registered_model: RegisteredModel) -> tuple[dict[str, float], ...]:
    raw = registered_model.artifact.diagnostics.get("bootstrap_parameter_samples")
    if not isinstance(raw, list) or not raw:
        raise ValueError("registered model has no bootstrap parameter samples")
    samples = tuple(
        {str(key): float(value) for key, value in sample.items()}
        for sample in raw
        if isinstance(sample, dict)
    )
    if not samples:
        raise ValueError("registered model bootstrap parameter samples are invalid")
    return samples


def compare_registered_model_scenarios(
    *,
    registered_model: RegisteredModel,
    base_simulator: RealWorldSimulator,
    population_generator: PopulationGenerator,
    control: Scenario,
    treatment: Scenario,
    population_size: int = 5000,
    seed: int = 42,
    replications_per_parameter: int = 1,
    allow_unapproved: bool = False,
) -> ScenarioComparisonResult:
    if registered_model.status != ModelStatus.APPROVED and not allow_unapproved:
        raise ValueError("scenario comparison requires an approved model")
    if population_size <= 0:
        raise ValueError("population_size must be positive")
    if replications_per_parameter <= 0:
        raise ValueError("replications_per_parameter must be positive")

    artifact = registered_model.artifact
    samples = _bootstrap_samples(registered_model)
    central = _weighted_simulator(
        base_simulator,
        population_generator=population_generator,
        weights=artifact.parameters,
        model_version=f"artifact:{artifact.artifact_id}:point",
    )
    control_point = central.simulate(control, population_size=population_size, seed=seed)
    treatment_point = central.simulate(treatment, population_size=population_size, seed=seed)

    control_values: list[float] = []
    treatment_values: list[float] = []
    effects: list[float] = []
    for sample_index, weights in enumerate(samples):
        simulator = _weighted_simulator(
            base_simulator,
            population_generator=population_generator,
            weights=weights,
            model_version=f"artifact:{artifact.artifact_id}:bootstrap:{sample_index}",
        )
        for replication in range(replications_per_parameter):
            run_seed = seed + replication
            control_run = simulator.simulate(
                control,
                population_size=population_size,
                seed=run_seed,
            )
            treatment_run = simulator.simulate(
                treatment,
                population_size=population_size,
                seed=run_seed,
            )
            control_values.append(control_run.laa_share)
            treatment_values.append(treatment_run.laa_share)
            effects.append(treatment_run.laa_share - control_run.laa_share)

    warnings = [
        str(item) for item in artifact.diagnostics.get("warnings", []) if item is not None
    ]
    if registered_model.status != ModelStatus.APPROVED:
        warnings.append(f"unapproved_model:{registered_model.status.value}")

    return ScenarioComparisonResult(
        model_artifact_id=artifact.artifact_id,
        model_status=registered_model.status.value,
        population_version=population_generator.population_version,
        control_scenario_id=control.scenario_id,
        treatment_scenario_id=treatment.scenario_id,
        population_size_per_run=population_size,
        parameter_samples=len(samples),
        replications_per_parameter=replications_per_parameter,
        run_pairs=len(effects),
        control_point_estimate=control_point,
        treatment_point_estimate=treatment_point,
        control_laa_share=summarize(control_values),
        treatment_laa_share=summarize(treatment_values),
        effect=summarize(effects),
        warnings=tuple(dict.fromkeys(warnings)),
    )
