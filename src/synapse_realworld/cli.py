from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer

from synapse_realworld.adapters import (
    iter_sales_capture_rows,
    load_events_jsonl,
    load_offers_csv,
    load_outcomes_csv,
    load_sales_capture_csv,
    load_unit_versions_csv,
    offer_to_event,
    unit_version_to_event,
)
from synapse_realworld.behaviour import MultinomialLogitCalibrator
from synapse_realworld.data.choice_set import TemporalChoiceSetBuilder
from synapse_realworld.data.dataset import DecisionDatasetBuilder
from synapse_realworld.data.decision_assembler import HistoricalDecisionAssembler
from synapse_realworld.data.projection import project_feature_observations
from synapse_realworld.data.training import build_calibration_examples, temporal_holdout
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


@app.command("ingest-outcomes")
def ingest_outcomes(
    csv_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    db: Annotated[Path, typer.Option(help="DuckDB database path")] = Path("synapse.duckdb"),
    source_id: Annotated[str, typer.Option(help="Stable outcome source identifier")] = (
        "laa-decision-outcomes"
    ),
) -> None:
    """Ingest verified booking/lost/postpone/contract outcomes."""
    events = load_outcomes_csv(csv_path, source_id=source_id)
    snapshot = build_snapshot(
        source_id=source_id,
        content=csv_path.read_bytes(),
        record_count=len(events),
        metadata={"path": csv_path.name, "adapter": "decision-outcomes-v0.2"},
    )
    with DuckDBStore(db) as store:
        result = EventIngestor(store, store).ingest(
            source_id=source_id,
            events=events,
            snapshot=snapshot,
        )
    typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command("ingest-inventory")
def ingest_inventory(
    units_csv: Annotated[Path, typer.Option(exists=True, readable=True)],
    offers_csv: Annotated[Path, typer.Option(exists=True, readable=True)],
    db: Annotated[Path, typer.Option(help="DuckDB database path")] = Path("synapse.duckdb"),
) -> None:
    """Ingest time-versioned unit inventory and offers from canonical CSV exports."""
    unit_versions = load_unit_versions_csv(units_csv)
    offers = load_offers_csv(offers_csv)
    events = tuple(unit_version_to_event(version) for version in unit_versions) + tuple(
        offer_to_event(offer) for offer in offers
    )
    unit_snapshot = build_snapshot(
        source_id=f"file:{units_csv.name}",
        content=units_csv.read_bytes(),
        record_count=len(unit_versions),
        metadata={"path": units_csv.name, "adapter": "unit-version-csv-v0.2"},
    )
    offer_snapshot = build_snapshot(
        source_id=f"file:{offers_csv.name}",
        content=offers_csv.read_bytes(),
        record_count=len(offers),
        metadata={"path": offers_csv.name, "adapter": "offer-csv-v0.2"},
    )
    with DuckDBStore(db) as store:
        inserted, duplicates = store.append_events(events)
        unit_recorded = store.record_snapshot(unit_snapshot)
        offer_recorded = store.record_snapshot(offer_snapshot)
    payload = {
        "received": len(events),
        "inserted": inserted,
        "duplicates": duplicates,
        "unit_snapshot_recorded": unit_recorded,
        "offer_snapshot_recorded": offer_recorded,
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


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


@app.command("calibrate")
def calibrate(
    units_csv: Annotated[Path, typer.Option(exists=True, readable=True)],
    offers_csv: Annotated[Path, typer.Option(exists=True, readable=True)],
    db: Annotated[Path, typer.Option(help="DuckDB database path")] = Path("synapse.duckdb"),
    holdout_fraction: Annotated[
        float, typer.Option(min=0.05, max=0.5, help="Latest fraction reserved for validation")
    ] = 0.2,
    output: Annotated[Path | None, typer.Option(help="Optional calibration JSON output")] = None,
) -> None:
    """Build a leakage-safe historical dataset and fit the v0.2 choice model."""
    unit_versions = load_unit_versions_csv(units_csv)
    offers = load_offers_csv(offers_csv)
    choice_builder = TemporalChoiceSetBuilder(unit_versions=unit_versions, offers=offers)
    with DuckDBStore(db) as store:
        events = tuple(store.list_events())

    decisions = HistoricalDecisionAssembler(choice_builder).assemble(events)
    observations = project_feature_observations(events)
    rows = DecisionDatasetBuilder().build(events=decisions, observations=observations)
    timed_examples = build_calibration_examples(rows)
    if len(timed_examples) < 2:
        raise typer.BadParameter("at least two verified historical choices are required")

    train, holdout = temporal_holdout(
        timed_examples,
        holdout_fraction=holdout_fraction,
    )
    calibrator = MultinomialLogitCalibrator()
    result = calibrator.fit(train)
    holdout_metrics = calibrator.evaluate(holdout, weights=result.weights)
    payload = {
        "model_version": result.model_version,
        "historical_choices": len(timed_examples),
        "train_examples": len(train),
        "holdout_examples": len(holdout),
        "weights": result.weights,
        "epochs": result.epochs,
        "converged": result.converged,
        "train_metrics": result.metrics.model_dump(mode="json"),
        "holdout_metrics": holdout_metrics.model_dump(mode="json"),
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if output is not None:
        output.write_text(rendered + "\n", encoding="utf-8")
    typer.echo(rendered)


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
