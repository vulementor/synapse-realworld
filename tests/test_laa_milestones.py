from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from synapse_realworld.adapters import (
    load_offers_csv,
    load_unit_versions_csv,
    offer_to_event,
    unit_version_to_event,
)
from synapse_realworld.datasets import (
    create_laa_real_dataset_snapshot,
    verify_laa_snapshot_directory,
)
from synapse_realworld.domain.events import CanonicalEvent, SourceSnapshot
from synapse_realworld.milestones import (
    ensure_laa_prospective_experiment_001,
    lock_laa_prospective_experiment_001_prediction,
    run_laa_calibration_001,
)
from synapse_realworld.registry import (
    FileModelRegistry,
    ModelDecision,
    ModelStatus,
)

BASE = datetime(2026, 9, 5, 8, 0, tzinfo=timezone.utc)


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _write_inputs(root: Path) -> tuple[Path, Path, Path]:
    units = root / "units.csv"
    offers = root / "offers.csv"
    travel = root / "travel.csv"
    _write_csv(
        units,
        [
            "unit_id",
            "project_id",
            "unit_code",
            "product_type",
            "inventory_state",
            "lot_area_m2",
            "built_area_m2",
            "effective_from",
            "effective_to",
            "source_id",
        ],
        [
            [
                "22222222-2222-2222-2222-222222222222",
                "11111111-1111-1111-1111-111111111111",
                "LK4-42",
                "townhouse",
                "available",
                80,
                180,
                "2026-09-01T00:00:00+00:00",
                "",
                "inventory:test",
            ],
            [
                "33333333-3333-3333-3333-333333333333",
                "11111111-1111-1111-1111-111111111111",
                "LK5-04",
                "townhouse",
                "available",
                90,
                200,
                "2026-09-01T00:00:00+00:00",
                "",
                "inventory:test",
            ],
        ],
    )
    _write_csv(
        offers,
        [
            "unit_id",
            "product_type",
            "list_price",
            "net_price",
            "discount_pct",
            "incentive_cash",
            "payment_plan_code",
            "down_payment_pct",
            "monthly_payment_est",
            "effective_from",
            "effective_to",
            "source_id",
        ],
        [
            [
                "22222222-2222-2222-2222-222222222222",
                "townhouse",
                2_000_000_000,
                1_950_000_000,
                0,
                0,
                "PLAN-A",
                0.3,
                18_000_000,
                "2026-09-01T00:00:00+00:00",
                "",
                "offer:test",
            ],
            [
                "33333333-3333-3333-3333-333333333333",
                "townhouse",
                2_500_000_000,
                2_450_000_000,
                0,
                0,
                "PLAN-A",
                0.3,
                22_000_000,
                "2026-09-01T00:00:00+00:00",
                "",
                "offer:test",
            ],
        ],
    )
    _write_csv(
        travel,
        [
            "origin_anchor_id",
            "destination_anchor_id",
            "mode",
            "departure_bucket",
            "travel_time_min",
            "distance_km",
            "reliability_p90_min",
            "observed_at",
            "valid_from",
            "valid_to",
            "source_id",
        ],
        [
            [
                "VSIP III",
                "LAA",
                "motorbike",
                "am_peak",
                28,
                18.4,
                36,
                "2026-09-01T00:00:00+00:00",
                "2026-09-01T00:00:00+00:00",
                "",
                "routing:test",
            ],
            [
                "Nam Tan Uyen",
                "LAA",
                "motorbike",
                "am_peak",
                34,
                22.1,
                43,
                "2026-09-01T00:00:00+00:00",
                "2026-09-01T00:00:00+00:00",
                "",
                "routing:test",
            ],
        ],
    )
    return units, offers, travel


def _qualification(entity_id: str, index: int) -> CanonicalEvent:
    workplace = "VSIP III" if index % 2 == 0 else "Nam Tan Uyen"
    return CanonicalEvent(
        event_type="qualification_observed",
        entity_type="household",
        entity_id=entity_id,
        occurred_at=BASE + timedelta(minutes=index),
        source_id="crm:test",
        source_event_key=f"qualification:{index}",
        payload={
            "purchase_purpose": "own_stay" if index % 3 else "investment",
            "household_size_band": "3-4",
            "children_band": "1",
            "household_income_band": "50-80m",
            "liquid_capital_band": "1-2b",
            "max_monthly_payment_band": "20-30m",
            "purchase_horizon": "90d",
            "workplace_zone": workplace,
            "stated_max_travel_min": "40",
            "preferred_product_type": "townhouse",
            "shortlisted_unit_code": "LK4-42" if index % 2 == 0 else "LK5-04",
        },
    )


def _outcome(entity_id: str, index: int) -> CanonicalEvent:
    outside = index % 4 == 0
    payload = {
        "outcome_type": "lost" if outside else "booking",
        "verified": True,
        "unit_code": None if outside else ("LK4-42" if index % 2 == 0 else "LK5-04"),
        "outside_option": "no_purchase" if outside else None,
    }
    return CanonicalEvent(
        event_type="decision_outcome_observed",
        entity_type="household",
        entity_id=entity_id,
        occurred_at=BASE + timedelta(days=1, minutes=index),
        source_id="crm:test",
        source_event_key=f"outcome:{index}",
        payload=payload,
    )


def _training_events(units_path: Path, offers_path: Path) -> tuple[CanonicalEvent, ...]:
    unit_events = tuple(
        unit_version_to_event(item) for item in load_unit_versions_csv(units_path)
    )
    offer_events = tuple(offer_to_event(item) for item in load_offers_csv(offers_path))
    households = []
    for index in range(40):
        entity_id = f"household-{index:03d}"
        households.extend((_qualification(entity_id, index), _outcome(entity_id, index)))
    return unit_events + offer_events + tuple(households)


def _source_snapshots() -> tuple[SourceSnapshot, ...]:
    return (
        SourceSnapshot(
            source_id="crm:test",
            captured_at=BASE,
            content_hash="a" * 64,
            record_count=80,
        ),
        SourceSnapshot(
            source_id="inventory:test",
            captured_at=BASE,
            content_hash="b" * 64,
            record_count=2,
        ),
        SourceSnapshot(
            source_id="offer:test",
            captured_at=BASE,
            content_hash="c" * 64,
            record_count=2,
        ),
    )


def test_snapshot_semantic_identity_ignores_ingest_ids(tmp_path: Path) -> None:
    units, offers, travel = _write_inputs(tmp_path)
    first = CanonicalEvent(
        event_id=uuid4(),
        event_type="qualification_observed",
        entity_type="household",
        entity_id="household-1",
        occurred_at=BASE,
        source_id="crm:test",
        source_event_key="q1",
        payload={"workplace_zone": "VSIP III"},
    )
    second = first.model_copy(update={"event_id": uuid4()})
    source_a = SourceSnapshot(
        snapshot_id=uuid4(),
        source_id="crm:test",
        captured_at=BASE,
        content_hash="d" * 64,
        record_count=1,
    )
    source_b = source_a.model_copy(
        update={"snapshot_id": uuid4(), "captured_at": BASE + timedelta(hours=1)}
    )

    manifest_a = create_laa_real_dataset_snapshot(
        events=(first,),
        source_snapshots=(source_a,),
        output_dir=tmp_path / "snapshot-a",
        units_csv=units,
        offers_csv=offers,
        travel_times_csv=travel,
    )
    manifest_b = create_laa_real_dataset_snapshot(
        events=(second,),
        source_snapshots=(source_b,),
        output_dir=tmp_path / "snapshot-b",
        units_csv=units,
        offers_csv=offers,
        travel_times_csv=travel,
    )
    assert manifest_a.dataset_snapshot_id == manifest_b.dataset_snapshot_id
    assert verify_laa_snapshot_directory(tmp_path / "snapshot-a") == manifest_a

    events_path = tmp_path / "snapshot-a" / "events.jsonl"
    events_path.write_text(
        events_path.read_text(encoding="utf-8") + "{}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="events file hash"):
        verify_laa_snapshot_directory(tmp_path / "snapshot-a")


def test_snapshot_is_immutable(tmp_path: Path) -> None:
    units, offers, _ = _write_inputs(tmp_path)
    output = tmp_path / "snapshot"
    output.mkdir()
    (output / "unexpected.txt").write_text("occupied", encoding="utf-8")
    with pytest.raises(ValueError, match="must be empty"):
        create_laa_real_dataset_snapshot(
            events=(),
            source_snapshots=(),
            output_dir=output,
            units_csv=units,
            offers_csv=offers,
        )


def test_calibration_and_prospective_experiment_001_end_to_end(tmp_path: Path) -> None:
    units, offers, travel = _write_inputs(tmp_path)
    events = _training_events(units, offers)
    snapshot_dir = tmp_path / "snapshot-001"
    snapshot = create_laa_real_dataset_snapshot(
        events=events,
        source_snapshots=_source_snapshots(),
        output_dir=snapshot_dir,
        units_csv=units,
        offers_csv=offers,
        travel_times_csv=travel,
        window_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
        window_to=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    assert snapshot.training_ready is True
    assert snapshot.audit.trainable_choice_events == 40

    model_registry_dir = tmp_path / "models"
    run_dir = tmp_path / "calibration-001"
    run = run_laa_calibration_001(
        snapshot_dir=snapshot_dir,
        output_dir=run_dir,
        model_registry_dir=model_registry_dir,
        code_commit_sha="test-commit-sha",
        bootstrap_samples=3,
        diagnostic_population_size=100,
        minimum_historical_choices=30,
        seed=7,
    )
    assert run.dataset_snapshot_id == snapshot.dataset_snapshot_id
    assert run.historical_choices == 40
    assert run.model_status == "candidate"

    registry = FileModelRegistry(model_registry_dir)
    registry.decide(
        ModelDecision(
            artifact_id=run.model_artifact_id,
            status=ModelStatus.VALIDATED,
            decided_by="test-data-review",
            reason="fixture diagnostics reviewed",
        )
    )
    registry.decide(
        ModelDecision(
            artifact_id=run.model_artifact_id,
            status=ModelStatus.APPROVED,
            decided_by="test-business-review",
            reason="fixture approved for E2E contract validation",
        )
    )

    experiment_registry = tmp_path / "experiments"
    definition, created = ensure_laa_prospective_experiment_001(
        registry_dir=experiment_registry,
        created_by="test-growth-lead",
        minimum_trials_per_variant=100,
    )
    assert created is True
    assert definition.assignment_method.value == "hash_randomized"
    assert definition.metadata["experiment_code"] == "LAA-PROSPECTIVE-001"

    locked = lock_laa_prospective_experiment_001_prediction(
        snapshot_dir=snapshot_dir,
        calibration_run_dir=run_dir,
        model_registry_dir=model_registry_dir,
        experiment_registry_dir=experiment_registry,
        as_of=datetime(2026, 11, 2, tzinfo=timezone.utc),
        treatment_perceived_commute_multiplier=0.85,
        population_size=100,
        replications_per_parameter=1,
        seed=11,
    )
    assert locked.locked is True
    assert locked.dataset_snapshot_id == snapshot.dataset_snapshot_id
    assert locked.model_artifact_id == run.model_artifact_id
    assert locked.prediction.metadata["experiment_code"] == "LAA-PROSPECTIVE-001"
