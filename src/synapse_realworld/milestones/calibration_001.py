from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.adapters import (
    load_events_jsonl,
    load_offers_csv,
    load_travel_times_csv,
    load_unit_versions_csv,
)
from synapse_realworld.behaviour.workflow import (
    CalibrationWorkflowResult,
    calibrate_historical_choices,
)
from synapse_realworld.datasets import (
    FileFingerprint,
    LAARealDatasetSnapshotManifest,
    verify_laa_snapshot_directory,
)
from synapse_realworld.population import fit_population_from_events
from synapse_realworld.registry import FileModelRegistry, ModelStatus
from synapse_realworld.spatial import build_project_commute_provider


class MilestoneModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LAACalibrationRun001Manifest(MilestoneModel):
    run_name: str = "LAA Calibration Run #001"
    run_version: str = "001"
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dataset_snapshot_id: str
    code_commit_sha: str
    model_artifact_id: UUID
    model_content_hash: str
    model_status: str
    population_version: str
    population_content_hash: str
    historical_choices: int = Field(ge=0)
    train_examples: int = Field(ge=0)
    holdout_examples: int = Field(ge=0)
    train_metrics: dict[str, float]
    holdout_metrics: dict[str, float]
    holdout_fraction: float = Field(gt=0, lt=1)
    bootstrap_samples: int = Field(gt=0)
    seed: int
    population_file: FileFingerprint
    calibration_file: FileFingerprint
    warnings: tuple[str, ...] = ()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fingerprint(path: Path, *, role: str) -> FileFingerprint:
    return FileFingerprint(
        role=role,
        filename=path.name,
        sha256=_sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def _snapshot_input(
    root: Path,
    manifest: LAARealDatasetSnapshotManifest,
    role: str,
) -> Path | None:
    for item in manifest.input_files:
        if item.role == role:
            return root / "evidence" / item.filename
    return None


def _run_id(
    *,
    dataset_snapshot_id: str,
    code_commit_sha: str,
    holdout_fraction: float,
    bootstrap_samples: int,
    seed: int,
    minimum_profile_confidence: float,
) -> str:
    payload = {
        "dataset_snapshot_id": dataset_snapshot_id,
        "code_commit_sha": code_commit_sha,
        "holdout_fraction": holdout_fraction,
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,
        "minimum_profile_confidence": minimum_profile_confidence,
        "run_version": "001",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def run_laa_calibration_001(
    *,
    snapshot_dir: str | Path,
    output_dir: str | Path,
    model_registry_dir: str | Path,
    code_commit_sha: str,
    model_name: str = "laa-buyer-choice",
    model_version: str = "laa-calibration-001",
    project_anchor_id: str = "LAA",
    holdout_fraction: float = 0.2,
    bootstrap_samples: int = 100,
    seed: int = 42,
    minimum_profile_confidence: float = 0.3,
    diagnostic_population_size: int = 5000,
    minimum_historical_choices: int = 30,
) -> LAACalibrationRun001Manifest:
    snapshot_root = Path(snapshot_dir)
    snapshot = verify_laa_snapshot_directory(snapshot_root)
    if not snapshot.training_ready:
        blockers = ", ".join(snapshot.blockers) or "unknown blockers"
        raise ValueError(f"snapshot is not training-ready: {blockers}")
    if not code_commit_sha.strip():
        raise ValueError("code_commit_sha is required")

    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError("calibration output directory must be empty; runs are immutable")
    output.mkdir(parents=True, exist_ok=True)

    events_path = snapshot_root / snapshot.events_file.filename
    units_path = _snapshot_input(snapshot_root, snapshot, "unit_versions")
    offers_path = _snapshot_input(snapshot_root, snapshot, "offers")
    travel_path = _snapshot_input(snapshot_root, snapshot, "travel_times")
    if units_path is None or offers_path is None:
        raise ValueError("snapshot requires frozen unit_versions and offers evidence")

    events = load_events_jsonl(events_path)
    unit_versions = load_unit_versions_csv(units_path)
    offers = load_offers_csv(offers_path)
    travel_times = load_travel_times_csv(travel_path) if travel_path is not None else ()

    population_fit = fit_population_from_events(
        events,
        profile_name=f"laa-real-snapshot-{snapshot.snapshot_version}",
        as_of=snapshot.window_to,
        minimum_profile_confidence=minimum_profile_confidence,
        diagnostic_population_size=diagnostic_population_size,
        seed=seed,
    )
    population_path = output / "population_profile.json"
    population_payload = {
        **population_fit.model_dump(mode="json"),
        "dataset_snapshot_id": snapshot.dataset_snapshot_id,
        "population_version": population_fit.profile.population_version,
        "content_hash": population_fit.profile.content_hash,
    }
    population_path.write_text(
        json.dumps(population_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    commute_provider = None
    if travel_times:
        commute_provider = build_project_commute_provider(
            events=events,
            unit_versions=unit_versions,
            travel_times=travel_times,
            destination_anchor_id=project_anchor_id,
        )

    calibration: CalibrationWorkflowResult = calibrate_historical_choices(
        unit_versions=unit_versions,
        offers=offers,
        events=events,
        model_name=model_name,
        model_version=model_version,
        code_commit_sha=code_commit_sha,
        dataset_snapshot_id=snapshot.dataset_snapshot_id,
        commute_provider=commute_provider,
        holdout_fraction=holdout_fraction,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
    )
    if calibration.historical_choices < minimum_historical_choices:
        raise ValueError(
            "calibration produced fewer historical choices than the governed minimum: "
            f"{calibration.historical_choices} < {minimum_historical_choices}"
        )

    registry = FileModelRegistry(model_registry_dir)
    registry.register(calibration.artifact)

    calibration_path = output / "calibration.json"
    calibration_payload = {
        **calibration.model_dump(mode="json"),
        "dataset_snapshot_id": snapshot.dataset_snapshot_id,
        "status": ModelStatus.CANDIDATE.value,
        "content_hash": calibration.artifact.content_hash,
    }
    calibration_path.write_text(
        json.dumps(calibration_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    run_manifest = LAACalibrationRun001Manifest(
        run_id=_run_id(
            dataset_snapshot_id=snapshot.dataset_snapshot_id,
            code_commit_sha=code_commit_sha,
            holdout_fraction=holdout_fraction,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
            minimum_profile_confidence=minimum_profile_confidence,
        ),
        dataset_snapshot_id=snapshot.dataset_snapshot_id,
        code_commit_sha=code_commit_sha,
        model_artifact_id=calibration.artifact.artifact_id,
        model_content_hash=calibration.artifact.content_hash,
        model_status=ModelStatus.CANDIDATE.value,
        population_version=population_fit.profile.population_version,
        population_content_hash=population_fit.profile.content_hash,
        historical_choices=calibration.historical_choices,
        train_examples=calibration.train_examples,
        holdout_examples=calibration.holdout_examples,
        train_metrics=calibration.artifact.train_metrics,
        holdout_metrics=calibration.artifact.holdout_metrics,
        holdout_fraction=holdout_fraction,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
        population_file=_fingerprint(population_path, role="population_profile"),
        calibration_file=_fingerprint(calibration_path, role="calibration_result"),
        warnings=tuple(population_fit.profile.warnings),
    )
    (output / "run_manifest.json").write_text(
        json.dumps(run_manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return run_manifest
