from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from synapse_realworld.adapters import (
    load_offers_csv,
    load_travel_times_csv,
    load_unit_versions_csv,
)
from synapse_realworld.experiments import (
    AssignmentMethod,
    ExperimentDefinition,
    ExperimentObservation,
    FileExperimentRegistry,
    build_model_experiment_scorecard,
    evaluate_experiment,
    prediction_from_scenario_comparison,
)
from synapse_realworld.population import EmpiricalPopulationGenerator, EmpiricalPopulationProfile
from synapse_realworld.registry import FileModelRegistry
from synapse_realworld.simulation import (
    Scenario,
    build_real_data_simulator,
    compare_registered_model_scenarios,
)


def _parse_datetime(value: str | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise typer.BadParameter(f"{field_name} must include a timezone offset")
    return parsed


def _load_population_profile(path: Path) -> EmpiricalPopulationProfile:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "profile" in payload:
        payload = payload["profile"]
    return EmpiricalPopulationProfile.model_validate(payload)


def register_experiment_commands(app: typer.Typer) -> None:
    @app.command("experiment-create")
    def experiment_create(
        name: Annotated[str, typer.Option(help="Experiment name")],
        hypothesis: Annotated[str, typer.Option(help="Pre-registered hypothesis")],
        created_by: Annotated[str, typer.Option(help="Human/role creating experiment")],
        registry_dir: Annotated[
            Path, typer.Option(help="Append-only experiment registry directory")
        ] = Path("experiment_registry"),
        metric_name: Annotated[str, typer.Option(help="Primary binary metric")] = (
            "laa_choice_rate"
        ),
        control_variant: Annotated[str, typer.Option(help="Control variant name")] = "control",
        treatment_variant: Annotated[
            str, typer.Option(help="Treatment variant name")
        ] = "treatment",
        target_segment: Annotated[str, typer.Option(help="Target segment label")] = "all",
        assignment_method: Annotated[
            AssignmentMethod, typer.Option(help="How subjects are assigned")
        ] = AssignmentMethod.RANDOMIZED,
        minimum_trials_per_variant: Annotated[
            int, typer.Option(min=1, help="Minimum sample per variant")
        ] = 30,
        planned_start_at: Annotated[
            str | None, typer.Option(help="Optional timezone-aware planned start")
        ] = None,
        planned_end_at: Annotated[
            str | None, typer.Option(help="Optional timezone-aware planned end")
        ] = None,
    ) -> None:
        """Create an immutable experiment definition before results exist."""
        definition = ExperimentDefinition(
            name=name,
            hypothesis=hypothesis,
            metric_name=metric_name,
            control_variant=control_variant,
            treatment_variant=treatment_variant,
            target_segment=target_segment,
            assignment_method=assignment_method,
            planned_start_at=_parse_datetime(planned_start_at, field_name="planned-start-at"),
            planned_end_at=_parse_datetime(planned_end_at, field_name="planned-end-at"),
            minimum_trials_per_variant=minimum_trials_per_variant,
            created_by=created_by,
        )
        registry = FileExperimentRegistry(registry_dir)
        created = registry.create(definition)
        typer.echo(
            json.dumps(
                {
                    "created": created,
                    "registry_dir": str(registry_dir),
                    "definition": definition.model_dump(mode="json"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("experiment-predict")
    def experiment_predict(
        experiment_id: Annotated[UUID, typer.Argument(help="Experiment UUID")],
        artifact_id: Annotated[UUID, typer.Argument(help="Governed model artifact UUID")],
        population_profile: Annotated[
            Path, typer.Option(exists=True, readable=True, help="Empirical population JSON")
        ],
        units_csv: Annotated[
            Path, typer.Option(exists=True, readable=True, help="Temporal unit versions CSV")
        ],
        offers_csv: Annotated[
            Path, typer.Option(exists=True, readable=True, help="Temporal offers CSV")
        ],
        as_of: Annotated[
            str, typer.Option(help="Timezone-aware timestamp for experiment scenarios")
        ],
        experiment_registry_dir: Annotated[
            Path, typer.Option(help="Experiment registry directory")
        ] = Path("experiment_registry"),
        model_registry_dir: Annotated[
            Path, typer.Option(help="Model registry directory")
        ] = Path("model_registry"),
        travel_times_csv: Annotated[
            Path | None,
            typer.Option(exists=True, readable=True, help="Optional temporal travel-time CSV"),
        ] = None,
        project_anchor_id: Annotated[str, typer.Option(help="Project anchor ID")] = "LAA",
        control_price_change: Annotated[
            float, typer.Option(help="Control relative price change")
        ] = 0.0,
        control_payment_multiplier: Annotated[
            float, typer.Option(min=0.01, help="Control payment multiplier")
        ] = 1.0,
        control_commute_multiplier: Annotated[
            float, typer.Option(min=0.01, help="Control commute multiplier")
        ] = 1.0,
        treatment_price_change: Annotated[
            float, typer.Option(help="Treatment relative price change")
        ] = 0.0,
        treatment_payment_multiplier: Annotated[
            float, typer.Option(min=0.01, help="Treatment payment multiplier")
        ] = 1.0,
        treatment_commute_multiplier: Annotated[
            float, typer.Option(min=0.01, help="Treatment commute multiplier")
        ] = 1.0,
        population_size: Annotated[
            int, typer.Option(min=1, help="Synthetic households per paired run")
        ] = 5000,
        replications_per_parameter: Annotated[
            int, typer.Option(min=1, help="Monte Carlo replications per bootstrap vector")
        ] = 1,
        seed: Annotated[int, typer.Option(help="Common random-number seed")] = 42,
        allow_unapproved: Annotated[
            bool, typer.Option(help="Allow exploratory prediction with non-approved model")
        ] = False,
        output: Annotated[
            Path | None, typer.Option(help="Optional prediction JSON output")
        ] = None,
    ) -> None:
        """Lock a paired control-vs-treatment prediction before observations arrive."""
        experiment_registry = FileExperimentRegistry(experiment_registry_dir)
        definition = experiment_registry.get_definition(experiment_id)
        if definition is None:
            raise typer.BadParameter(f"unknown experiment: {experiment_id}")

        model_registry = FileModelRegistry(model_registry_dir)
        registered = model_registry.get(artifact_id)
        if registered is None:
            raise typer.BadParameter(f"unknown model artifact: {artifact_id}")

        scenario_time = _parse_datetime(as_of, field_name="as-of")
        assert scenario_time is not None
        profile = _load_population_profile(population_profile)
        population_generator = EmpiricalPopulationGenerator(profile)
        unit_versions = load_unit_versions_csv(units_csv)
        offers = load_offers_csv(offers_csv)
        travel_times = (
            load_travel_times_csv(travel_times_csv) if travel_times_csv is not None else ()
        )
        base = build_real_data_simulator(
            unit_versions=unit_versions,
            offers=offers,
            as_of=scenario_time,
            population_generator=population_generator,
            input_snapshot_id=registered.artifact.dataset_snapshot_id,
            travel_times=travel_times,
            project_anchor_id=project_anchor_id,
            code_commit_sha=registered.artifact.code_commit_sha,
        )
        control = Scenario(
            scenario_id=f"experiment:{experiment_id}:control",
            price_change_pct=control_price_change,
            payment_multiplier=control_payment_multiplier,
            commute_multiplier=control_commute_multiplier,
        )
        treatment = Scenario(
            scenario_id=f"experiment:{experiment_id}:treatment",
            price_change_pct=treatment_price_change,
            payment_multiplier=treatment_payment_multiplier,
            commute_multiplier=treatment_commute_multiplier,
        )
        comparison = compare_registered_model_scenarios(
            registered_model=registered,
            base_simulator=base,
            population_generator=population_generator,
            control=control,
            treatment=treatment,
            population_size=population_size,
            seed=seed,
            replications_per_parameter=replications_per_parameter,
            allow_unapproved=allow_unapproved,
        )
        prediction = prediction_from_scenario_comparison(
            definition=definition,
            registered_model=registered,
            comparison=comparison,
        )
        locked = experiment_registry.lock_prediction(prediction)
        payload = {
            "locked": locked,
            "definition": definition.model_dump(mode="json"),
            "prediction": prediction.model_dump(mode="json"),
            "comparison": comparison.model_dump(mode="json"),
        }
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        if output is not None:
            output.write_text(rendered + "\n", encoding="utf-8")
        typer.echo(rendered)

    @app.command("experiment-observe")
    def experiment_observe(
        experiment_id: Annotated[UUID, typer.Argument(help="Experiment UUID")],
        variant: Annotated[str, typer.Option(help="Observed variant")],
        successes: Annotated[int, typer.Option(min=0, help="Successful outcomes")],
        trials: Annotated[int, typer.Option(min=1, help="Observed trials")],
        source_id: Annotated[str, typer.Option(help="Stable result source")],
        source_event_key: Annotated[
            str, typer.Option(help="Idempotent source event key")
        ],
        observed_at: Annotated[
            str | None,
            typer.Option(help="Timezone-aware observation timestamp; defaults to now"),
        ] = None,
        registry_dir: Annotated[
            Path, typer.Option(help="Experiment registry directory")
        ] = Path("experiment_registry"),
    ) -> None:
        """Append idempotent observed A/B outcomes after prediction lock."""
        registry = FileExperimentRegistry(registry_dir)
        definition = registry.get_definition(experiment_id)
        if definition is None:
            raise typer.BadParameter(f"unknown experiment: {experiment_id}")
        timestamp = _parse_datetime(observed_at, field_name="observed-at")
        observation = ExperimentObservation(
            experiment_id=experiment_id,
            variant=variant,
            metric_name=definition.metric_name,
            successes=successes,
            trials=trials,
            observed_at=timestamp or datetime.now(timezone.utc),
            source_id=source_id,
            source_event_key=source_event_key,
        )
        inserted = registry.append_observation(observation)
        typer.echo(
            json.dumps(
                {
                    "inserted": inserted,
                    "observation": observation.model_dump(mode="json"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("experiment-evaluate")
    def experiment_evaluate(
        experiment_id: Annotated[UUID, typer.Argument(help="Experiment UUID")],
        registry_dir: Annotated[
            Path, typer.Option(help="Experiment registry directory")
        ] = Path("experiment_registry"),
        output: Annotated[
            Path | None, typer.Option(help="Optional evaluation JSON output")
        ] = None,
    ) -> None:
        """Compare the locked prediction with append-only observed outcomes."""
        registry = FileExperimentRegistry(registry_dir)
        definition = registry.get_definition(experiment_id)
        prediction = registry.get_prediction(experiment_id)
        if definition is None:
            raise typer.BadParameter(f"unknown experiment: {experiment_id}")
        if prediction is None:
            raise typer.BadParameter("experiment has no locked prediction")
        evaluation = evaluate_experiment(
            definition=definition,
            prediction=prediction,
            observations=registry.list_observations(experiment_id),
        )
        rendered = json.dumps(evaluation.model_dump(mode="json"), ensure_ascii=False, indent=2)
        if output is not None:
            output.write_text(rendered + "\n", encoding="utf-8")
        typer.echo(rendered)

    @app.command("experiment-scorecard")
    def experiment_scorecard(
        artifact_id: Annotated[UUID, typer.Argument(help="Model artifact UUID")],
        registry_dir: Annotated[
            Path, typer.Option(help="Experiment registry directory")
        ] = Path("experiment_registry"),
    ) -> None:
        """Aggregate real-world forecast accuracy across experiments for one model."""
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
        typer.echo(
            json.dumps(
                {
                    "scorecard": scorecard.model_dump(mode="json"),
                    "evaluations": [item.model_dump(mode="json") for item in evaluations],
                    "pending_experiments": pending,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("experiments")
    def experiments(
        registry_dir: Annotated[
            Path, typer.Option(help="Experiment registry directory")
        ] = Path("experiment_registry"),
    ) -> None:
        """List experiments with prediction-lock and observation state."""
        registry = FileExperimentRegistry(registry_dir)
        payload = []
        for definition in registry.list_experiments():
            prediction = registry.get_prediction(definition.experiment_id)
            observations = registry.list_observations(definition.experiment_id)
            payload.append(
                {
                    "definition": definition.model_dump(mode="json"),
                    "prediction_locked": prediction is not None,
                    "prediction_id": str(prediction.prediction_id) if prediction else None,
                    "observations": len(observations),
                    "trials": sum(item.trials for item in observations),
                }
            )
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
