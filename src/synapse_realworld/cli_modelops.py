from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from synapse_realworld.experiments import (
    FileExperimentRegistry,
    assess_experiment_quality,
    build_model_experiment_scorecard,
    evaluate_experiment,
)
from synapse_realworld.modelops import RecalibrationPolicy, assess_recalibration_need


def register_modelops_commands(app: typer.Typer) -> None:
    @app.command("experiment-qa")
    def experiment_qa(
        experiment_id: Annotated[UUID, typer.Argument(help="Experiment UUID")],
        registry_dir: Annotated[
            Path, typer.Option(help="Experiment registry directory")
        ] = Path("experiment_registry"),
        expected_treatment_share: Annotated[
            float,
            typer.Option(min=0.001, max=0.999, help="Expected treatment allocation share"),
        ] = 0.5,
        sample_ratio_z_threshold: Annotated[
            float,
            typer.Option(min=0.01, help="Absolute z-score threshold for SRM warning"),
        ] = 3.29,
    ) -> None:
        """Check experiment allocation, sample sufficiency and causal-design declarations."""
        registry = FileExperimentRegistry(registry_dir)
        definition = registry.get_definition(experiment_id)
        if definition is None:
            raise typer.BadParameter(f"unknown experiment: {experiment_id}")
        assessment = assess_experiment_quality(
            definition=definition,
            observations=registry.list_observations(experiment_id),
            expected_treatment_share=expected_treatment_share,
            sample_ratio_z_threshold=sample_ratio_z_threshold,
        )
        typer.echo(json.dumps(assessment.model_dump(mode="json"), ensure_ascii=False, indent=2))

    @app.command("model-recalibration-assess")
    def model_recalibration_assess(
        artifact_id: Annotated[UUID, typer.Argument(help="Model artifact UUID")],
        registry_dir: Annotated[
            Path, typer.Option(help="Experiment registry directory")
        ] = Path("experiment_registry"),
        minimum_evaluated_experiments: Annotated[
            int, typer.Option(min=1, help="Experiments required before drift assessment")
        ] = 5,
        minimum_causal_experiments: Annotated[
            int, typer.Option(min=0, help="Randomized experiments required")
        ] = 3,
        maximum_mean_absolute_effect_error: Annotated[
            float, typer.Option(min=0, help="Maximum acceptable mean effect error")
        ] = 0.05,
        minimum_interval_coverage_rate: Annotated[
            float, typer.Option(min=0, max=1, help="Minimum prediction interval coverage")
        ] = 0.80,
        minimum_direction_accuracy: Annotated[
            float, typer.Option(min=0, max=1, help="Minimum effect-direction accuracy")
        ] = 0.70,
    ) -> None:
        """Recommend monitor/recalibration review without automatic retraining."""
        registry = FileExperimentRegistry(registry_dir)
        evaluations = []
        pending: list[str] = []
        for definition in registry.list_experiments():
            prediction = registry.get_prediction(definition.experiment_id)
            if prediction is None or prediction.model_artifact_id != artifact_id:
                continue
            try:
                evaluation = evaluate_experiment(
                    definition=definition,
                    prediction=prediction,
                    observations=registry.list_observations(definition.experiment_id),
                )
            except ValueError:
                pending.append(str(definition.experiment_id))
                continue
            evaluations.append(evaluation)

        scorecard = build_model_experiment_scorecard(
            evaluations,
            model_artifact_id=artifact_id,
        )
        policy = RecalibrationPolicy(
            minimum_evaluated_experiments=minimum_evaluated_experiments,
            minimum_causal_experiments=minimum_causal_experiments,
            maximum_mean_absolute_effect_error=maximum_mean_absolute_effect_error,
            minimum_interval_coverage_rate=minimum_interval_coverage_rate,
            minimum_direction_accuracy=minimum_direction_accuracy,
        )
        assessment = assess_recalibration_need(scorecard, policy=policy)
        typer.echo(
            json.dumps(
                {
                    "assessment": assessment.model_dump(mode="json"),
                    "pending_experiments": pending,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
