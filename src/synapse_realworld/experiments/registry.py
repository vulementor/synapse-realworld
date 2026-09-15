from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from synapse_realworld.experiments.models import (
    ExperimentDefinition,
    ExperimentObservation,
    ExperimentPrediction,
)


class FileExperimentRegistry:
    """Append-only local experiment registry.

    Predictions are locked before the first observation. Observations are deduped
    by `(source_id, source_event_key)` so repeated imports are safe.
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
        if self.list_observations(prediction.experiment_id):
            raise ValueError("prediction must be locked before the first observation")
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
