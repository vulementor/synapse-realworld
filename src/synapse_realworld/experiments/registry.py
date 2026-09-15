from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from synapse_realworld.experiments.models import (
    ExperimentAssignmentReceipt,
    ExperimentDefinition,
    ExperimentObservation,
    ExperimentPrediction,
)


class FileExperimentRegistry:
    """Append-only local experiment registry.

    Predictions are locked before assignments/observations. Assignment receipts
    and observations are idempotent by source keys, and a pseudonymous subject
    cannot be assigned to conflicting variants in the same experiment.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _directory(self, experiment_id: UUID) -> Path:
        return self.root / str(experiment_id)

    def _definition_path(self, experiment_id: UUID) -> Path:
        return self._directory(experiment_id) / "definition.json"

    def _prediction_path(self, experiment_id: UUID) -> Path:
        return self._directory(experiment_id) / "prediction.json"

    def _assignments_path(self, experiment_id: UUID) -> Path:
        return self._directory(experiment_id) / "assignments.jsonl"

    def _observations_path(self, experiment_id: UUID) -> Path:
        return self._directory(experiment_id) / "observations.jsonl"

    def create(self, definition: ExperimentDefinition) -> bool:
        directory = self._directory(definition.experiment_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = self._definition_path(definition.experiment_id)
        if path.exists():
            existing = ExperimentDefinition.model_validate_json(path.read_text(encoding="utf-8"))
            if existing != definition:
                raise ValueError("experiment_id already exists with a different definition")
            return False
        path.write_text(
            json.dumps(definition.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return True

    def get_definition(self, experiment_id: UUID) -> ExperimentDefinition | None:
        path = self._definition_path(experiment_id)
        if not path.exists():
            return None
        return ExperimentDefinition.model_validate_json(path.read_text(encoding="utf-8"))

    def lock_prediction(self, prediction: ExperimentPrediction) -> bool:
        definition = self.get_definition(prediction.experiment_id)
        if definition is None:
            raise ValueError("cannot lock prediction for an unknown experiment")
        if prediction.metric_name != definition.metric_name:
            raise ValueError("prediction metric_name must match experiment metric_name")
        if self.list_assignments(prediction.experiment_id) or self.list_observations(
            prediction.experiment_id
        ):
            raise ValueError("prediction must be locked before assignments and observations")
        path = self._prediction_path(prediction.experiment_id)
        if path.exists():
            existing = ExperimentPrediction.model_validate_json(path.read_text(encoding="utf-8"))
            if existing != prediction:
                raise ValueError("experiment prediction is already locked and immutable")
            return False
        path.write_text(
            json.dumps(prediction.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return True

    def get_prediction(self, experiment_id: UUID) -> ExperimentPrediction | None:
        path = self._prediction_path(experiment_id)
        if not path.exists():
            return None
        return ExperimentPrediction.model_validate_json(path.read_text(encoding="utf-8"))

    def append_assignment(self, assignment: ExperimentAssignmentReceipt) -> bool:
        definition = self.get_definition(assignment.experiment_id)
        if definition is None:
            raise ValueError("cannot assign an unknown experiment")
        prediction = self.get_prediction(assignment.experiment_id)
        if prediction is None:
            raise ValueError("a locked prediction is required before assignments")
        if assignment.assigned_at < prediction.created_at:
            raise ValueError("assignment timestamp predates the locked prediction")
        if assignment.variant not in {
            definition.control_variant,
            definition.treatment_variant,
        }:
            raise ValueError("assignment variant is not part of the experiment")
        if definition.planned_start_at and assignment.assigned_at < definition.planned_start_at:
            raise ValueError("assignment occurred before planned experiment start")
        if definition.planned_end_at and assignment.assigned_at >= definition.planned_end_at:
            raise ValueError("assignment occurred after planned experiment end")

        assignments = self.list_assignments(assignment.experiment_id)
        source_key = (assignment.source_id, assignment.source_event_key)
        if any((item.source_id, item.source_event_key) == source_key for item in assignments):
            return False

        prior_subject = [item for item in assignments if item.subject_key == assignment.subject_key]
        if prior_subject:
            variants = {item.variant for item in prior_subject}
            if variants != {assignment.variant}:
                raise ValueError("subject_key is already assigned to a conflicting variant")
            return False

        path = self._assignments_path(assignment.experiment_id)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(assignment.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")
        return True

    def list_assignments(self, experiment_id: UUID) -> tuple[ExperimentAssignmentReceipt, ...]:
        path = self._assignments_path(experiment_id)
        if not path.exists():
            return ()
        assignments: list[ExperimentAssignmentReceipt] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    assignments.append(ExperimentAssignmentReceipt.model_validate_json(line))
        return tuple(
            sorted(
                assignments,
                key=lambda item: (item.assigned_at, str(item.assignment_id)),
            )
        )

    def append_observation(self, observation: ExperimentObservation) -> bool:
        definition = self.get_definition(observation.experiment_id)
        if definition is None:
            raise ValueError("cannot observe an unknown experiment")
        prediction = self.get_prediction(observation.experiment_id)
        if prediction is None:
            raise ValueError("a locked prediction is required before observations")
        if observation.observed_at < prediction.created_at:
            raise ValueError("observation timestamp predates the locked prediction")
        if observation.metric_name != definition.metric_name:
            raise ValueError("observation metric_name must match experiment metric_name")
        if observation.variant not in {
            definition.control_variant,
            definition.treatment_variant,
        }:
            raise ValueError("observation variant is not part of the experiment")
        if definition.planned_start_at and observation.observed_at < definition.planned_start_at:
            raise ValueError("observation occurred before planned experiment start")

        observations = self.list_observations(observation.experiment_id)
        source_key = (observation.source_id, observation.source_event_key)
        if any((item.source_id, item.source_event_key) == source_key for item in observations):
            return False

        path = self._observations_path(observation.experiment_id)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(observation.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")
        return True

    def list_observations(self, experiment_id: UUID) -> tuple[ExperimentObservation, ...]:
        path = self._observations_path(experiment_id)
        if not path.exists():
            return ()
        observations: list[ExperimentObservation] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    observations.append(ExperimentObservation.model_validate_json(line))
        return tuple(
            sorted(
                observations,
                key=lambda item: (item.observed_at, str(item.observation_id)),
            )
        )

    def list_experiments(self) -> tuple[ExperimentDefinition, ...]:
        definitions: list[ExperimentDefinition] = []
        for path in sorted(self.root.glob("*/definition.json")):
            definitions.append(ExperimentDefinition.model_validate_json(path.read_text("utf-8")))
        return tuple(
            sorted(
                definitions,
                key=lambda item: (item.created_at, str(item.experiment_id)),
            )
        )
