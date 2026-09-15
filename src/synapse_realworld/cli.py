from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Annotated
from uuid import UUID

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
from synapse_realworld.behaviour.workflow import calibrate_historical_choices
from synapse_realworld.domain.models import Household, Offer, Unit
from synapse_realworld.ingestion import EventIngestor, build_snapshot
from synapse_realworld.persistence import DuckDBStore
from synapse_realworld.projects.laa import build_laa_demo_world
from synapse_realworld.registry import (
    FileModelRegistry,
    ModelDecision,
    ModelStatus,
)
from synapse_realworld.simulation import Scenario

app = typer.Typer(
    name="synapse-realworld",
    help="Synapse Real-World Platform CLI",
    no_args_is_help=True,
)


def _combined_dataset_snapshot_id(
    *,
    units_csv: Path,
    offers_csv: Path,
    source_hashes: list[str],
) -> str:
    digest = hashlib.sha256()
    digest.update(hashlib.sha256(units_csv.read_bytes()).digest())
    digest.update(hashlib.sha256(offers_csv.read_bytes()).digest())
    for source_hash in sorted(source_hashes):
        digest.update(source_hash.encode("utf-8"))
    return f"sha256:{digest.hexdigest()}"


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
    source_id: Annotated[str, typer.Option(help="Source ID expected on every event")],
    db: Annotated[Path, typer.Option(help="DuckDB database path")] = Path("synapse.duckdb"),
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
    registry_dir: Annotated[
        Path, typer.Option(help="Append-only model registry directory")
    ] = Path("model_registry"),
    model_name: Annotated[str, typer.Option(help="Logical model name")] = "laa-buyer-choice",
    model_version: Annotated[str, typer.Option(help="Human-readable model version")] = "v0.3",
    code_commit_sha: Annotated[
        str, typer.Option(help="Git commit SHA for reproducibility")
    ] = "local-untracked",
    holdout_fraction: Annotated[
        float, typer.Option(min=0.05, max=0.5, help="Latest fraction reserved for validation")
    ] = 0.2,
    bootstrap_samples: Annotated[
        int, typer.Option(min=1, help="Bootstrap fits for coefficient intervals")
    ] = 50,
    seed: Annotated[int, typer.Option(help="Reproducible bootstrap seed")] = 42,
    output: Annotated[Path | None, typer.Option(help="Optional calibration JSON output")] = None,
) -> None:
    """Calibrate, diagnose and register a governed buyer-choice model candidate."""
    unit_versions = load_unit_versions_csv(units_csv)
    offers = load_offers_csv(offers_csv)
    with DuckDBStore(db) as store:
        events = tuple(store.list_events())
        snapshots = tuple(store.list_snapshots())

    dataset_snapshot_id = _combined_dataset_snapshot_id(
        units_csv=units_csv,
        offers_csv=offers_csv,
        source_hashes=[snapshot.content_hash for snapshot in snapshots],
    )
    result = calibrate_historical_choices(
        unit_versions=unit_versions,
        offers=offers,
        events=events,
        model_name=model_name,
        model_version=model_version,
        code_commit_sha=code_commit_sha,
        dataset_snapshot_id=dataset_snapshot_id,
        holdout_fraction=holdout_fraction,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
    )
    registry = FileModelRegistry(registry_dir)
    registered = registry.register(result.artifact)
    payload = {
        **result.model_dump(mode="json"),
        "registered": registered,
        "registry_dir": str(registry_dir),
        "status": ModelStatus.CANDIDATE.value,
        "content_hash": result.artifact.content_hash,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if output is not None:
        output.write_text(rendered + "\n", encoding="utf-8")
    typer.echo(rendered)


@app.command("model-decide")
def model_decide(
    artifact_id: Annotated[UUID, typer.Argument(help="Registered model artifact UUID")],
    status: Annotated[ModelStatus, typer.Option(help="New governance status")],
    decided_by: Annotated[str, typer.Option(help="Human/role recording the decision")],
    reason: Annotated[str, typer.Option(help="Decision rationale")],
    registry_dir: Annotated[
        Path, typer.Option(help="Append-only model registry directory")
    ] = Path("model_registry"),
) -> None:
    """Append a governed model validation/approval/rejection/archive decision."""
    registry = FileModelRegistry(registry_dir)
    decision = ModelDecision(
        artifact_id=artifact_id,
        status=status,
        decided_by=decided_by,
        reason=reason,
    )
    registry.decide(decision)
    registered = registry.get(artifact_id)
    assert registered is not None
    typer.echo(json.dumps(registered.model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command("models")
def models(
    registry_dir: Annotated[
        Path, typer.Option(help="Append-only model registry directory")
    ] = Path("model_registry"),
    model_name: Annotated[str | None, typer.Option(help="Optional logical model filter")] = None,
) -> None:
    """List registered model artifacts and their current governance status."""
    registry = FileModelRegistry(registry_dir)
    registered = registry.list_models(model_name=model_name)
    typer.echo(
        json.dumps(
            [item.model_dump(mode="json") for item in registered],
            ensure_ascii=False,
            indent=2,
        )
    )


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
