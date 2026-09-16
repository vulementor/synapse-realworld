from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from synapse_realworld.datasets import (
    create_laa_real_dataset_snapshot,
    verify_laa_snapshot_directory,
)
from synapse_realworld.milestones import (
    ensure_laa_prospective_experiment_001,
    lock_laa_prospective_experiment_001_prediction,
    run_laa_calibration_001,
)
from synapse_realworld.persistence import DuckDBStore


def _parse_datetime(value: str | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise typer.BadParameter(f"{field_name} must include a timezone offset")
    return parsed


def register_laa_milestone_commands(app: typer.Typer) -> None:
    @app.command("laa-snapshot-001-create")
    def laa_snapshot_001_create(
        units_csv: Annotated[
            Path, typer.Option(exists=True, readable=True, help="Temporal unit versions CSV")
        ],
        offers_csv: Annotated[
            Path, typer.Option(exists=True, readable=True, help="Temporal offers CSV")
        ],
        db: Annotated[Path, typer.Option(help="DuckDB event store path")] = Path(
            "synapse.duckdb"
        ),
        travel_times_csv: Annotated[
            Path | None,
            typer.Option(exists=True, readable=True, help="Optional temporal travel-time CSV"),
        ] = None,
        output_dir: Annotated[
            Path, typer.Option(help="Immutable snapshot output directory")
        ] = Path("artifacts/laa_real_dataset_snapshot_001"),
        window_from: Annotated[
            str | None, typer.Option(help="Timezone-aware inclusive dataset start")
        ] = None,
        window_to: Annotated[
            str | None, typer.Option(help="Timezone-aware exclusive dataset end")
        ] = None,
    ) -> None:
        """Freeze LAA Real Dataset Snapshot #001 with hashes, evidence and readiness audit."""
        start = _parse_datetime(window_from, field_name="window-from")
        end = _parse_datetime(window_to, field_name="window-to")
        with DuckDBStore(db) as store:
            events = tuple(
                store.list_events(
                    occurred_from=start,
                    occurred_to=end,
                )
            )
            snapshots = tuple(store.list_snapshots())
        manifest = create_laa_real_dataset_snapshot(
            events=events,
            source_snapshots=snapshots,
            output_dir=output_dir,
            units_csv=units_csv,
            offers_csv=offers_csv,
            travel_times_csv=travel_times_csv,
            window_from=start,
            window_to=end,
            snapshot_version="001",
        )
        typer.echo(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2))

    @app.command("laa-snapshot-001-verify")
    def laa_snapshot_001_verify(
        snapshot_dir: Annotated[Path, typer.Argument(exists=True, readable=True)],
    ) -> None:
        """Verify hashes and semantic identity for LAA Real Dataset Snapshot #001."""
        manifest = verify_laa_snapshot_directory(snapshot_dir)
        typer.echo(
            json.dumps(
                {
                    "verified": True,
                    "dataset_snapshot_id": manifest.dataset_snapshot_id,
                    "event_count": manifest.event_count,
                    "training_ready": manifest.training_ready,
                    "blockers": list(manifest.blockers),
                    "warnings": list(manifest.warnings),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("laa-calibration-001-run")
    def laa_calibration_001_run(
        snapshot_dir: Annotated[Path, typer.Option(exists=True, readable=True)],
        code_commit_sha: Annotated[str, typer.Option(help="Git commit SHA for reproducibility")],
        output_dir: Annotated[
            Path, typer.Option(help="Immutable calibration run output directory")
        ] = Path("artifacts/laa_calibration_run_001"),
        model_registry_dir: Annotated[
            Path, typer.Option(help="Append-only model registry directory")
        ] = Path("model_registry"),
        holdout_fraction: Annotated[
            float, typer.Option(min=0.05, max=0.5, help="Latest temporal holdout fraction")
        ] = 0.2,
        bootstrap_samples: Annotated[
            int, typer.Option(min=1, help="Bootstrap parameter fits")
        ] = 100,
        seed: Annotated[int, typer.Option(help="Reproducible calibration seed")] = 42,
        minimum_profile_confidence: Annotated[
            float, typer.Option(min=0, max=1, help="Minimum population profile confidence")
        ] = 0.3,
        diagnostic_population_size: Annotated[
            int, typer.Option(min=1, help="Population diagnostic sample size")
        ] = 5000,
        minimum_historical_choices: Annotated[
            int, typer.Option(min=2, help="Governed minimum historical choices")
        ] = 30,
    ) -> None:
        """Run governed LAA Calibration Run #001 from a verified immutable snapshot."""
        manifest = run_laa_calibration_001(
            snapshot_dir=snapshot_dir,
            output_dir=output_dir,
            model_registry_dir=model_registry_dir,
            code_commit_sha=code_commit_sha,
            holdout_fraction=holdout_fraction,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
            minimum_profile_confidence=minimum_profile_confidence,
            diagnostic_population_size=diagnostic_population_size,
            minimum_historical_choices=minimum_historical_choices,
        )
        typer.echo(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2))

    @app.command("laa-experiment-001-create")
    def laa_experiment_001_create(
        created_by: Annotated[str, typer.Option(help="Human/role pre-registering experiment")],
        experiment_registry_dir: Annotated[
            Path, typer.Option(help="Append-only experiment registry directory")
        ] = Path("experiment_registry"),
        minimum_trials_per_variant: Annotated[
            int, typer.Option(min=1, help="Minimum observed trials per variant")
        ] = 100,
        planned_start_at: Annotated[
            str | None, typer.Option(help="Optional timezone-aware planned start")
        ] = None,
        planned_end_at: Annotated[
            str | None, typer.Option(help="Optional timezone-aware planned end")
        ] = None,
    ) -> None:
        """Pre-register immutable LAA Prospective Experiment #001."""
        definition, created = ensure_laa_prospective_experiment_001(
            registry_dir=experiment_registry_dir,
            created_by=created_by,
            minimum_trials_per_variant=minimum_trials_per_variant,
            planned_start_at=_parse_datetime(
                planned_start_at,
                field_name="planned-start-at",
            ),
            planned_end_at=_parse_datetime(
                planned_end_at,
                field_name="planned-end-at",
            ),
        )
        typer.echo(
            json.dumps(
                {
                    "created": created,
                    "definition": definition.model_dump(mode="json"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("laa-experiment-001-lock")
    def laa_experiment_001_lock(
        snapshot_dir: Annotated[Path, typer.Option(exists=True, readable=True)],
        calibration_run_dir: Annotated[Path, typer.Option(exists=True, readable=True)],
        as_of: Annotated[
            str, typer.Option(help="Timezone-aware inventory/offer scenario timestamp")
        ],
        model_registry_dir: Annotated[
            Path, typer.Option(help="Append-only model registry directory")
        ] = Path("model_registry"),
        experiment_registry_dir: Annotated[
            Path, typer.Option(help="Append-only experiment registry directory")
        ] = Path("experiment_registry"),
        treatment_perceived_commute_multiplier: Annotated[
            float,
            typer.Option(
                min=0.01,
                max=1.0,
                help="Decision-model proxy for treatment perceived commute",
            ),
        ] = 0.85,
        population_size: Annotated[
            int, typer.Option(min=1, help="Synthetic households per paired run")
        ] = 5000,
        replications_per_parameter: Annotated[
            int, typer.Option(min=1, help="Replications per bootstrap parameter vector")
        ] = 1,
        seed: Annotated[int, typer.Option(help="Common random-number seed")] = 42,
        output: Annotated[
            Path | None, typer.Option(help="Optional locked forecast JSON output")
        ] = None,
    ) -> None:
        """Lock Experiment #001 forecast before assignments or real outcomes arrive."""
        scenario_time = _parse_datetime(as_of, field_name="as-of")
        assert scenario_time is not None
        result = lock_laa_prospective_experiment_001_prediction(
            snapshot_dir=snapshot_dir,
            calibration_run_dir=calibration_run_dir,
            model_registry_dir=model_registry_dir,
            experiment_registry_dir=experiment_registry_dir,
            as_of=scenario_time,
            treatment_perceived_commute_multiplier=treatment_perceived_commute_multiplier,
            population_size=population_size,
            replications_per_parameter=replications_per_parameter,
            seed=seed,
        )
        rendered = json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
        if output is not None:
            output.write_text(rendered + "\n", encoding="utf-8")
        typer.echo(rendered)
