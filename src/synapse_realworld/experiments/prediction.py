from __future__ import annotations

from synapse_realworld.experiments.models import ExperimentDefinition, ExperimentPrediction
from synapse_realworld.registry import RegisteredModel
from synapse_realworld.simulation.comparison import ScenarioComparisonResult


def prediction_from_scenario_comparison(
    *,
    definition: ExperimentDefinition,
    registered_model: RegisteredModel,
    comparison: ScenarioComparisonResult,
) -> ExperimentPrediction:
    if comparison.model_artifact_id != registered_model.artifact.artifact_id:
        raise ValueError("scenario comparison model does not match registered model")
    if definition.metric_name != comparison.metric_name:
        raise ValueError("experiment metric does not match scenario comparison metric")

    return ExperimentPrediction(
        experiment_id=definition.experiment_id,
        model_artifact_id=comparison.model_artifact_id,
        model_status=comparison.model_status,
        population_version=comparison.population_version,
        metric_name=definition.metric_name,
        control_scenario_id=comparison.control_scenario_id,
        treatment_scenario_id=comparison.treatment_scenario_id,
        control_point_estimate=comparison.control_point_estimate.laa_share,
        treatment_point_estimate=comparison.treatment_point_estimate.laa_share,
        effect_mean=comparison.effect.mean,
        effect_p05=comparison.effect.p05,
        effect_p50=comparison.effect.p50,
        effect_p95=comparison.effect.p95,
        ensemble_samples=comparison.effect.samples,
        source_snapshot_id=registered_model.artifact.dataset_snapshot_id,
        metadata={
            "parameter_samples": comparison.parameter_samples,
            "replications_per_parameter": comparison.replications_per_parameter,
            "population_size_per_run": comparison.population_size_per_run,
            "warnings": list(comparison.warnings),
        },
    )
