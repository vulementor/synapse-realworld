from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.data import household_from_features, project_feature_observations
from synapse_realworld.domain.events import CanonicalEvent
from synapse_realworld.domain.models import Household
from synapse_realworld.population.empirical import (
    EmpiricalPopulationGenerator,
    EmpiricalPopulationProfile,
    PopulationDiagnostics,
    diagnose_population,
    fit_empirical_population_profile,
)


class PopulationFitResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: EmpiricalPopulationProfile
    diagnostics: PopulationDiagnostics
    candidate_households: int = Field(ge=0)
    included_households: int = Field(gt=0)
    excluded_low_confidence: int = Field(ge=0)
    as_of: datetime | None = None
    minimum_profile_confidence: float = Field(ge=0, le=1)


def household_snapshots_from_events(
    events: Iterable[CanonicalEvent],
    *,
    as_of: datetime | None = None,
) -> tuple[Household, ...]:
    observations = project_feature_observations(tuple(events))
    latest: dict[UUID, dict[str, tuple[datetime, str, Any]]] = defaultdict(dict)
    for observation in observations:
        if as_of is not None and observation.observed_at > as_of:
            continue
        current = latest[observation.household_id].get(observation.feature_name)
        candidate = (observation.observed_at, observation.source_id, observation.value)
        if current is None or candidate[:2] > current[:2]:
            latest[observation.household_id][observation.feature_name] = candidate

    households: list[Household] = []
    for household_id in sorted(latest, key=str):
        features = {
            feature_name: value
            for feature_name, (_, _, value) in latest[household_id].items()
        }
        households.append(household_from_features(household_id, features))
    return tuple(households)


def fit_population_from_events(
    events: Iterable[CanonicalEvent],
    *,
    profile_name: str = "laa-empirical-v0.4",
    as_of: datetime | None = None,
    minimum_profile_confidence: float = 0.3,
    diagnostic_population_size: int = 5000,
    seed: int = 42,
) -> PopulationFitResult:
    if not 0 <= minimum_profile_confidence <= 1:
        raise ValueError("minimum_profile_confidence must be between 0 and 1")
    if diagnostic_population_size <= 0:
        raise ValueError("diagnostic_population_size must be positive")

    candidates = household_snapshots_from_events(events, as_of=as_of)
    included = tuple(
        household
        for household in candidates
        if household.profile_confidence >= minimum_profile_confidence
    )
    if not included:
        raise ValueError("no households meet the population confidence threshold")

    profile = fit_empirical_population_profile(included, name=profile_name)
    generator = EmpiricalPopulationGenerator(profile)
    synthetic = generator.generate(diagnostic_population_size, seed=seed)
    diagnostics = diagnose_population(profile=profile, synthetic=synthetic)

    return PopulationFitResult(
        profile=profile,
        diagnostics=diagnostics,
        candidate_households=len(candidates),
        included_households=len(included),
        excluded_low_confidence=len(candidates) - len(included),
        as_of=as_of,
        minimum_profile_confidence=minimum_profile_confidence,
    )
