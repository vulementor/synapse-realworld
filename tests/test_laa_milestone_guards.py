from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from synapse_realworld.datasets import FileFingerprint, create_laa_real_dataset_snapshot
from synapse_realworld.milestones import (
    LAACalibrationRun001Manifest,
    ensure_laa_prospective_experiment_001,
    lock_laa_prospective_experiment_001_prediction,
    run_laa_calibration_001,
)
from synapse_realworld.registry import FileModelRegistry, ModelArtifact


ARTIFACT_ID = UUID("99999999-9999-9999-9999-999999999999")


def _dummy_inputs(root: Path) -> tuple[Path, Path]:
    units = root / "units.csv"
    offers = root / "offers.csv"
    units.write_text("unit_id\n", encoding="utf-8")
    offers.write_text("unit_id\n", encoding="utf-8")
    return units, offers


def _empty_snapshot(root: Path) -> Path:
    units, offers = _dummy_inputs(root)
    snapshot_dir = root / "snapshot"
    create_laa_real_dataset_snapshot(
        events=(),
        source_snapshots=(),
        output_dir=snapshot_dir,
        units_csv=units,
        offers_csv=offers,
    )
    return snapshot_dir


def test_calibration_001_rejects_non_ready_snapshot(tmp_path: Path) -> None:
    snapshot_dir = _empty_snapshot(tmp_path)
    with pytest.raises(ValueError, match="snapshot is not training-ready"):
        run_laa_calibration_001(
            snapshot_dir=snapshot_dir,
            output_dir=tmp_path / "calibration",
            model_registry_dir=tmp_path / "models",
            code_commit_sha="test-sha",
            minimum_historical_choices=2,
        )


def test_experiment_001_rejects_candidate_model(tmp_path: Path) -> None:
    snapshot_dir = _empty_snapshot(tmp_path)
    snapshot_payload = json.loads(
        (snapshot_dir / "manifest.json").read_text(encoding="utf-8")
    )
    snapshot_id = snapshot_payload["dataset_snapshot_id"]

    model_registry_dir = tmp_path / "models"
    registry = FileModelRegistry(model_registry_dir)
    artifact = ModelArtifact(
        artifact_id=ARTIFACT_ID,
        model_name="laa-buyer-choice",
        model_version="candidate-test",
        model_family="multinomial_logit",
        code_commit_sha="test-sha",
        dataset_snapshot_id=snapshot_id,
        feature_schema_version="decision-features-v0.3",
        parameters={},
        train_metrics={},
        holdout_metrics={},
    )
    registry.register(artifact)

    run_dir = tmp_path / "calibration-run"
    run_dir.mkdir()
    placeholder = FileFingerprint(
        role="placeholder",
        filename="placeholder.json",
        sha256="0" * 64,
        size_bytes=0,
    )
    run = LAACalibrationRun001Manifest(
        run_id="sha256:" + "1" * 64,
        dataset_snapshot_id=snapshot_id,
        code_commit_sha="test-sha",
        model_artifact_id=ARTIFACT_ID,
        model_content_hash=artifact.content_hash,
        model_status="candidate",
        population_version="empirical:test:1234",
        population_content_hash="2" * 64,
        historical_choices=30,
        train_examples=24,
        holdout_examples=6,
        train_metrics={},
        holdout_metrics={},
        holdout_fraction=0.2,
        bootstrap_samples=3,
        seed=42,
        population_file=placeholder.model_copy(
            update={"role": "population_profile", "filename": "population.json"}
        ),
        calibration_file=placeholder.model_copy(
            update={"role": "calibration_result", "filename": "calibration.json"}
        ),
    )
    (run_dir / "run_manifest.json").write_text(
        json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    experiment_registry_dir = tmp_path / "experiments"
    ensure_laa_prospective_experiment_001(
        registry_dir=experiment_registry_dir,
        created_by="test",
    )
    with pytest.raises(ValueError, match="requires an approved model"):
        lock_laa_prospective_experiment_001_prediction(
            snapshot_dir=snapshot_dir,
            calibration_run_dir=run_dir,
            model_registry_dir=model_registry_dir,
            experiment_registry_dir=experiment_registry_dir,
            as_of=datetime(2026, 9, 16, tzinfo=timezone.utc),
            population_size=10,
        )
