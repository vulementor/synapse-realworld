from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer

from synapse_realworld.adapters import (
    iter_sales_capture_rows,
    load_events_jsonl,
    load_sales_capture_csv,
)
from synapse_realworld.domain.models import Household, Offer, Unit
from synapse_realworld.ingestion import EventIngestor, build_snapshot
from synapse_realworld.persistence import DuckDBStore
from synapse_realworld.projects.laa import build_laa_demo_world
from synapse_realworld.simulation import Scenario

app = typer.Typer(
    name="synapse-realworld",
    help="Synapse Real-World Platform CLI",
    no_args_is_help=True,
)


@app.command()
def demo(
    population: Annotated[int, typer.Option(min=1, help="Synthetic household count")] = 1000,
    seed: Annotated[int, typer.Option(help="Reproducible random seed")] = 42,
    price_change: Annotated[
        float, typer.Option(help="Relative LAA price change, e.g. 0.05 = +5%")
    ] = 0.0,
    payment_multiplier: Annotated[
        float, typer.Option(min=0.01, help="Multiplier applied to modeled monthly payment")
    ] = 1.0,
    commute_multiplier: Annotated[
        float, typer.Option(min=0.01, help="Multiplier applied to modeled commute")
    ] = 1.0,
) -> None:
    """Run the deterministic LAA reference simulation."""
    world = build_laa_demo_world(seed=seed)
    result = world.simulate(
        Scenario(
            scenario_id="cli-demo",
            price_change_pct=price_change,
            payment_multiplier=payment_multiplier,
            commute_multiplier=commute_multiplier,
        ),
        population_size=population,
        seed=seed,
    )
    typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command("schema")
def schema_command(
    entity: Annotated[str, typer.Argument(help="household | unit | offer")],
) -> None:
    """Print the JSON schema for a canonical domain entity."""
    registry = {"household": Household, "unit": Unit, "offer": Offer}
    try:
        model = registry[entity.lower()]
    except KeyError as exc:
        raise typer.BadParameter(f"unknown entity: {entity}") from exc
    typer.echo(json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2))


@app.command("init-store")
def init_store(
    db: Annotated[Path, typer.Option(help="DuckDB database path")] = Path("synapse.duckdb"),
) -> None:
    """Initialize the local append-only event/snapshot store."""
    with DuckDBStore(db):
        pass
    typer.echo(json.dumps({"db": str(db), "initialized": True}, indent=2))


@app.command("ingest-sales")
def ingest_sales(
    csv_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    db: Annotated[Path, typer.Option(help="DuckDB database path")] = Path("synapse.duckdb"),
    source_id: Annotated[str, typer.Option(help="Stable source identifier")] = "laa-sales-capture",
) -> None:
    """Map the v0.2 Sales Capture CSV into canonical events and persist it."""
    content = csv_path.read_bytes()
    row_count = sum(1 for _ in iter_sales_capture_rows(csv_path))
    events = load_sales_capture_csv(csv_path, source_id=source_id)
    snapshot = build_snapshot(
        source_id=source_id,
        content=content,
        record_count=row_count,
        metadata={"path": csv_path.name, "adapter": "sales-capture-v0.2"},
    )
    with DuckDBStore(db) as store:
        result = EventIngestor(store, store).ingest(
            source_id=source_id,
            events=events,
            snapshot=snapshot,
        )
    typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command("ingest-jsonl")
def ingest_jsonl(
    jsonl_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    db: Annotated[Path, typer.Option(help="DuckDB database path")] = Path("synapse.duckdb"),
    source_id: Annotated[str, typer.Option(help="Source ID expected on every event")],
) -> None:
    """Ingest canonical events emitted by an external connector or agent harness."""
    content = jsonl_path.read_bytes()
    events = load_events_jsonl(jsonl_path)
    snapshot = build_snapshot(
        source_id=source_id,
        content=content,
        record_count=len(events),
        metadata={"path": jsonl_path.name, "adapter": "canonical-jsonl-v1"},
    )
    with DuckDBStore(db) as store:
        result = EventIngestor(store, store).ingest(
            source_id=source_id,
            events=events,
            snapshot=snapshot,
        )
    typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command("store-stats")
def store_stats(
    db: Annotated[Path, typer.Option(help="DuckDB database path")] = Path("synapse.duckdb"),
) -> None:
    """Show local ingestion state without exposing event payloads."""
    with DuckDBStore(db) as store:
        events = store.list_events()
        snapshots = store.list_snapshots()
    payload = {
        "db": str(db),
        "events": len(events),
        "snapshots": len(snapshots),
        "event_types": dict(sorted(Counter(event.event_type for event in events).items())),
        "sources": dict(sorted(Counter(event.source_id for event in events).items())),
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
