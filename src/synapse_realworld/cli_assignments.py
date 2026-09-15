from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from synapse_realworld.experiments import (
    ExperimentAssignmentReceipt,
    FileExperimentRegistry,
)


def _assignment_time(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise typer.BadParameter("assigned-at must include a timezone offset")
    return parsed


def register_assignment_commands(app: typer.Typer) -> None:
    @app.command("experiment-assign")
    def experiment_assign(
        experiment_id: Annotated[UUID, typer.Argument(help="Experiment UUID")],
        subject_key: Annotated[
            str, typer.Option(help="Pseudonymous subject key; never raw PII")
        ],
        variant: Annotated[str, typer.Option(help="Assigned experiment variant")],
        source_id: Annotated[str, typer.Option(help="Stable assignment source")],
        source_event_key: Annotated[
            str, typer.Option(help="Idempotent source assignment key")
        ],
        assigned_at: Annotated[
            str | None, typer.Option(help="Timezone-aware assignment timestamp")
        ] = None,
        channel: Annotated[
            str | None, typer.Option(help="Optional acquisition/exposure channel")
        ] = None,
        cohort: Annotated[
            str | None, typer.Option(help="Optional cohort/segment label")
        ] = None,
        registry_dir: Annotated[
            Path, typer.Option(help="Experiment registry directory")
        ] = Path("experiment_registry"),
    ) -> None:
        """Append a pseudonymous assignment receipt after the prediction is locked."""
        registry = FileExperimentRegistry(registry_dir)
        receipt = ExperimentAssignmentReceipt(
            experiment_id=experiment_id,
            subject_key=subject_key,
            variant=variant,
            assigned_at=_assignment_time(assigned_at),
            source_id=source_id,
            source_event_key=source_event_key,
            channel=channel,
            cohort=cohort,
        )
        inserted = registry.append_assignment(receipt)
        typer.echo(
            json.dumps(
                {
                    "inserted": inserted,
                    "assignment": receipt.model_dump(mode="json"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("experiment-assignments")
    def experiment_assignments(
        experiment_id: Annotated[UUID, typer.Argument(help="Experiment UUID")],
        registry_dir: Annotated[
            Path, typer.Option(help="Experiment registry directory")
        ] = Path("experiment_registry"),
    ) -> None:
        """List pseudonymous assignment receipts for one experiment."""
        registry = FileExperimentRegistry(registry_dir)
        assignments = registry.list_assignments(experiment_id)
        typer.echo(
            json.dumps(
                [item.model_dump(mode="json") for item in assignments],
                ensure_ascii=False,
                indent=2,
            )
        )
