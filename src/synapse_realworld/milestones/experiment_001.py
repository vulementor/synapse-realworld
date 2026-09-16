from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict

from synapse_realworld.adapters import (
    load_offers_csv,
    load_travel_times_csv,
    load_unit_versions_csv,
)
from synapse_realworld.datasets import (
    LAARealDatasetSnapshotManifest,
    verify_laa_snapshot_directory,
)
from synapse_realworld.experiments import (
    AssignmentMethod,
    ExperimentDefinition,
    ExperimentPrediction,
    FileExperimentRegistry,
    prediction_from_scenario_comparison,
)
from synapse_realworld.milestones.calibration_001 import LAACalibrationRun001Manifest
from synapse_realworld.population import EmpiricalPopulationGenerator, EmpiricalPopulationProfile
from synapse_realworld.registry import FileModelRegistry, ModelStatus
from synapse_realworld.simulation import (
    Scenario,
    ScenarioComparisonResult,
    build_real_data_simulator,
    compare_registered_model_scenarios,
)

EXPERIMENT_NAMESPACE = UUID("74272e49-7cd3-4df4-b135-d205647971be")
LAA_PROSPECTIVE_EXPERIMENT_001_ID = uuid5(
    EXPERIMENT_NAMESPACE,
    "LAA-PROSPECTIVE-EXPERIMENT-001",
)


class ExperimentMilestoneModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LAAProspectiveExperiment001LockResult(ExperimentMilestoneModel):
    experiment_id: UUID
    locked: bool
    definition: ExperimentDefinition
    prediction: ExperimentPrediction
    comparison: ScenarioComparisonResult
    dataset_snapshot_id: str
    calibration_run_id: str
    model_artifact_id: UUID


def _load_population_profile(path: Path) -> tuple[EmpiricalPopulationProfile, str | None]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    snapshot_id = payload.get("dataset_snapshot_id") if isinstance(payload, dict) else None
    if isinstance(payload, dict) and "profile" in payload:
        payload = payload["profile"]
    return EmpiricalPopulationProfile.model_validate(payload), snapshot_id


def _snapshot_input(
    root: Path,
    manifest: LAARealDatasetSnapshotManifest,
    role: str,
) -> Path | None:
    for item in manifest.input_files:
        if item.role == role:
            return root / "evidence" / item.filename
    return None


def ensure_laa_prospective_experiment_001(
    *,
    registry_dir: str | Path,
    created_by: str,
    minimum_trials_per_variant: int = 100,
    planned_start_at: datetime | None = None,
    planned_end_at: datetime | None = None,
) -> tuple[ExperimentDefinition, bool]:
    registry = FileExperimentRegistry(registry_dir)
    existing = registry.get_definition(LAA_PROSPECTIVE_EXPERIMENT_001_ID)
    if existing is not None:
        if existing.metadata.get("experiment_code") != "LAA-PROSPECTIVE-001":
            raise ValueError("reserved experiment ID is occupied by another definition")
        return existing, False

    definition = ExperimentDefinition(
        experiment_id=LAA_PROSPECTIVE_EXPERIMENT_001_ID,
        name="LAA Prospective Experiment #001 — Commute Perception",
        hypothesis=(
            "For qualified Lan Anh Avenue prospects with a known workplace zone, "
            "measured travel-time framing increases LAA choice rate versus the standard "
            "location message."
        ),
        metric_name="laa_choice_rate",
        control_variant="standard_location_message",
        treatment_variant="measured_travel_time_framing",
        target_segment="qualified_prospects_with_known_workplace_zone",
        assignment_method=AssignmentMethod.HASH_RANDOMIZED,
        planned_start_at=planned_start_at,
        planned_end_at=planned_end_at,
        minimum_trials_per_variant=minimum_trials_per_variant,
        created_by=created_by,
        metadata={
            "experiment_code": "LAA-PROSPECTIVE-001",
            "decision_dimension": "commute_perception",
            "control": "current standard location communication",
            "treatment": "measured workplace-to-LAA travel-time framing",
            "eligibility": "qualified prospect with known workplace zone",
            "price_change": False,
            "payment_plan_change": False,
            "assignment_receipt_required": True,
            "prediction_must_be_locked_before_assignment": True,
            "model_intervention_proxy": (
                "treatment scenario uses a perceived-commute multiplier; this is a "
                "decision-model proxy, not a proven advertising-message effect"
            ),
        },
    )
    return definition, registry.create(definition)


def lock_laa_prospective_experiment_001_prediction(
    *,
    snapshot_dir: str | Path,
    calibration_run_dir: str | Path,
    model_registry_dir: str | Path,
    experiment_registry_dir: str | Path,
    as_of: datetime,
    treatment_perceived_commute_multiplier: float = 0.85,
    project_anchor_id: str = "LAA",
    population_size: int = 5000,
    replications_per_parameter: int = 1,
    seed: int = 42,
) -> LAAProspectiveExperiment001LockResult:
    if not 0 < treatment_perceived_commute_multiplier <= 1:
        raise ValueError("treatment_perceived_commute_multiplier must be in (0, 1]")

    snapshot_root = Path(snapshot_dir)
    snapshot = verify_laa_snapshot_directory(snapshot_root)
    run_root = Path(calibration_run_dir)
    run_manifest = LAACalibrationRun001Manifest.model_validate_json(
        (run_root / "run_manifest.json").read_text(encoding="utf-8")
    )
    if run_manifest.dataset_snapshot_id != snapshot.dataset_snapshot_id:
        raise ValueError("calibration run and dataset snapshot do not match")

    model_registry = FileModelRegistry(model_registry_dir)
    registered = model_registry.get(run_manifest.model_artifact_id)
    if registered is None:
        raise ValueError("calibration model artifact is not present in the model registry")
    if registered.status != ModelStatus.APPROVED:
        raise ValueError("LAA Prospective Experiment #001 requires an approved model")
    if registered.artifact.dataset_snapshot_id != snapshot.dataset_snapshot_id:
        raise ValueError("approved model was calibrated on a different dataset snapshot")

    experiment_registry = FileExperimentRegistry(experiment_registry_dir)
    definition = experiment_registry.get_definition(LAA_PROSPECTIVE_EXPERIMENT_001_ID)
    if definition is None:
        raise ValueError("create LAA Prospective Experiment #001 before locking prediction")

    population_path = run_root / run_manifest.population_file.filename
    profile, population_snapshot_id = _load_population_profile(population_path)
    if population_snapshot_id != snapshot.dataset_snapshot_id:
        raise ValueError("population profile was fitted from a different dataset snapshot")
    if profile.population_version != run_manifest.population_version:
        raise ValueError("population profile does not match calibration run manifest")

    units_path = _snapshot_input(snapshot_root, snapshot, "unit_versions")
    offers_path = _snapshot_input(snapshot_root, snapshot, "offers")
    travel_path = _snapshot_input(snapshot_root, snapshot, "travel_times")
    if units_path is None or offers_path is None:
        raise ValueError("snapshot requires frozen unit_versions and offers evidence")

    unit_versions = load_unit_versions_csv(units_path)
    offers = load_offers_csv(offers_path)
    travel_times = load_travel_times_csv(travel_path) if travel_path is not None else ()
    population_generator = EmpiricalPopulationGenerator(profile)
    base = build_real_data_simulator(
        unit_versions=unit_versions,
        offers=offers,
        as_of=as_of,
        population_generator=population_generator,
        input_snapshot_id=snapshot.dataset_snapshot_id,
        travel_times=travel_times,
        project_anchor_id=project_anchor_id,
        code_commit_sha=registered.artifact.code_commit_sha,
    )
    control = Scenario(
        scenario_id="LAA-PROSPECTIVE-001:control",
        price_change_pct=0.0,
        payment_multiplier=1.0,
        commute_multiplier=1.0,
    )
    treatment = Scenario(
        scenario_id="LAA-PROSPECTIVE-001:treatment",
        price_change_pct=0.0,
        payment_multiplier=1.0,
        commute_multiplier=treatment_perceived_commute_multiplier,
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
        allow_unapproved=False,
    )
    base_prediction = prediction_from_scenario_comparison(
        definition=definition,
        registered_model=registered,
        comparison=comparison,
    )
    prediction = base_prediction.model_copy(
        update={
            "metadata": {
                **base_prediction.metadata,
                "experiment_code": "LAA-PROSPECTIVE-001",
                "intervention": "measured_travel_time_framing",
                "perceived_commute_multiplier": treatment_perceived_commute_multiplier,
                "proxy_boundary": (
                    "The commute multiplier models a change in perceived commute utility. "
                    "The prospective experiment must validate whether the message causes "
                    "that behavioral shift in the real market."
                ),
            }
        }
    )
    locked = experiment_registry.lock_prediction(prediction)
    return LAAProspectiveExperiment001LockResult(
        experiment_id=definition.experiment_id,
        locked=locked,
        definition=definition,
        prediction=prediction,
        comparison=comparison,
        dataset_snapshot_id=snapshot.dataset_snapshot_id,
        calibration_run_id=run_manifest.run_id,
        model_artifact_id=registered.artifact.artifact_id,
    )
