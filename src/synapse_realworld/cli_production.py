from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from synapse_realworld.audit import audit_laa_events
from synapse_realworld.connectors import GenericCsvConnector, LAA_CONNECTOR_PROFILES, get_laa_profile
from synapse_realworld.ingestion import EventIngestor
from synapse_realworld.persistence import DuckDBStore


def register_production_commands(app: typer.Typer) -> None:
    @app.command("laa-connectors")
    def laa_connectors() -> None:
        """List built-in Lan Anh Avenue production connector profiles."""
        payload = {
            name: {
                "profile": profile.name,
                "event_type": profile.event_type,
                "entity_type": profile.entity_type,
                "required_columns": sorted(
                    {
                        profile.entity_id_column,
                        profile.occurred_at_column,
                        *profile.required_columns,
                        *(
                            (profile.source_event_key_column,)
                            if profile.source_event_key_column
                            else ()
                        ),
                    }
                ),
                "payload_columns": list(profile.payload_columns),
                "pseudonymize_entity_id": profile.pseudonymize_entity_id,
            }
            for name, profile in sorted(LAA_CONNECTOR_PROFILES.items())
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))

    @app.command("laa-ingest-csv")
    def laa_ingest_csv(
        profile_name: Annotated[str, typer.Argument(help="LAA connector profile name")],
        csv_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
        source_id: Annotated[str, typer.Option(help="Stable source identifier")],
        db: Annotated[Path, typer.Option(help="DuckDB database path")] = Path(
            "synapse.duckdb"
        ),
    ) -> None:
        """Ingest a real LAA CSV export through a governed mapping profile."""
        try:
            profile = get_laa_profile(profile_name)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        batch = GenericCsvConnector(
            csv_path,
            source_id=source_id,
            profile=profile,
        ).extract()
        with DuckDBStore(db) as store:
            result = EventIngestor(store, store).ingest(
                source_id=source_id,
                events=batch.events,
                snapshot=batch.snapshot,
            )
        payload = {
            "profile": profile_name,
            "connector": batch.connector_name,
            "warnings": list(batch.warnings),
            "ingestion": result.model_dump(mode="json"),
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))

    @app.command("data-audit")
    def data_audit(
        db: Annotated[Path, typer.Option(help="DuckDB database path")] = Path(
            "synapse.duckdb"
        ),
        output: Annotated[
            Path | None, typer.Option(help="Optional audit JSON output")
        ] = None,
    ) -> None:
        """Audit LAA evidence coverage and model-training readiness."""
        with DuckDBStore(db) as store:
            events = tuple(store.list_events())
        audit = audit_laa_events(events)
        rendered = json.dumps(audit.model_dump(mode="json"), ensure_ascii=False, indent=2)
        if output is not None:
            output.write_text(rendered + "\n", encoding="utf-8")
        typer.echo(rendered)
