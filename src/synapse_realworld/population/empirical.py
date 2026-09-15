from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.domain.models import Household

SYNTHETIC_POPULATION_NAMESPACE = UUID("a2da2908-6a0c-4e3d-ad26-a5b12ccf82d5")


class PopulationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EmpiricalPopulationProfile(PopulationModel):
    name: str
    prototypes: tuple[Household, ...]
    source_households: int = Field(gt=0)
    warnings: tuple[str, ...] = ()

    @property
    def content_hash(self) -> str:
        payload = [
            household.model_dump(mode="json", exclude={"household_id"})
            for household in self.prototypes
        ]
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @property
    def population_version(self) -> str:
        return f"empirical:{self.name}:{self.content_hash[:16]}"


class MarginalComparison(PopulationModel):
    source: dict[str, float]
    synthetic: dict[str, float]
    total_variation_distance: float = Field(ge=0, le=1)


class NumericComparison(PopulationModel):
    source_mean: float | None
    synthetic_mean: float | None
    absolute_mean_delta: float | None = Field(default=None, ge=0)


class PopulationDiagnostics(PopulationModel):
    source_households: int = Field(gt=0)
    synthetic_households: int = Field(gt=0)
    marginal_comparisons: dict[str, MarginalComparison]
    numeric_comparisons: dict[str, NumericComparison]
    max_total_variation_distance: float = Field(ge=0, le=1)
    warnings: tuple[str, ...] = ()


def _latest_unique_households(households: Iterable[Household]) -> tuple[Household, ...]:
    # Callers should supply time-correct snapshots. We dedupe by analytics household id
    # so customers with more interactions do not receive extra population weight.
    by_id: dict[UUID, Household] = {}
    for household in households:
        by_id[household.household_id] = household
    return tuple(by_id[key] for key in sorted(by_id, key=str))


def fit_empirical_population_profile(
    households: Iterable[Household],
    *,
    name: str = "laa-empirical-v0.4",
) -> EmpiricalPopulationProfile:
    prototypes = _latest_unique_households(households)
    if not prototypes:
        raise ValueError("empirical population fitting requires at least one household")
    warnings: list[str] = []
    if len(prototypes) < 100:
        warnings.append("small_population_sample: fewer than 100 unique households")
    if len(prototypes) < 30:
        warnings.append("very_small_population_sample: synthetic market is exploratory only")
    return EmpiricalPopulationProfile(
        name=name,
        prototypes=prototypes,
        source_households=len(prototypes),
        warnings=tuple(warnings),
    )


class EmpiricalPopulationGenerator:
    def __init__(self, profile: EmpiricalPopulationProfile) -> None:
        self.profile = profile

    @property
    def population_version(self) -> str:
        return self.profile.population_version

    def generate(self, size: int, *, seed: int) -> list[Household]:
        if size <= 0:
            raise ValueError("size must be positive")
        rng = random.Random(seed)
        generated: list[Household] = []
        for index in range(size):
            prototype = rng.choice(self.profile.prototypes)
            synthetic_id = uuid5(
                SYNTHETIC_POPULATION_NAMESPACE,
                f"{self.population_version}:{seed}:{index}",
            )
            generated.append(prototype.model_copy(update={"household_id": synthetic_id}))
        return generated


def _categorical_distribution(
    households: Sequence[Household],
    attribute: str,
) -> dict[str, float]:
    counts: Counter[str] = Counter()
    for household in households:
        value = getattr(household, attribute)
        if hasattr(value, "value"):
            value = value.value
        normalized = "unknown" if value is None or value == "" else str(value)
        counts[normalized] += 1
    total = len(households)
    return {key: count / total for key, count in sorted(counts.items())}


def _total_variation(first: dict[str, float], second: dict[str, float]) -> float:
    keys = set(first) | set(second)
    return 0.5 * sum(abs(first.get(key, 0.0) - second.get(key, 0.0)) for key in keys)


def _numeric_mean(households: Sequence[Household], attribute: str) -> float | None:
    values = [float(value) for household in households if (value := getattr(household, attribute)) is not None]
    return sum(values) / len(values) if values else None


def diagnose_population(
    *,
    profile: EmpiricalPopulationProfile,
    synthetic: Iterable[Household],
) -> PopulationDiagnostics:
    generated = tuple(synthetic)
    if not generated:
        raise ValueError("population diagnostics require synthetic households")

    categorical_fields = (
        "purchase_purpose",
        "household_size_band",
        "children_band",
        "workplace_zone",
        "preferred_product_type",
    )
    marginal_comparisons: dict[str, MarginalComparison] = {}
    for field_name in categorical_fields:
        source = _categorical_distribution(profile.prototypes, field_name)
        synthetic_distribution = _categorical_distribution(generated, field_name)
        marginal_comparisons[field_name] = MarginalComparison(
            source=source,
            synthetic=synthetic_distribution,
            total_variation_distance=_total_variation(source, synthetic_distribution),
        )

    numeric_fields = (
        "income_midpoint_million",
        "liquid_capital_million",
        "max_monthly_payment_million",
        "purchase_horizon_days",
        "commute_tolerance_min",
    )
    numeric_comparisons: dict[str, NumericComparison] = {}
    for field_name in numeric_fields:
        source_mean = _numeric_mean(profile.prototypes, field_name)
        synthetic_mean = _numeric_mean(generated, field_name)
        delta = (
            abs(source_mean - synthetic_mean)
            if source_mean is not None and synthetic_mean is not None
            else None
        )
        numeric_comparisons[field_name] = NumericComparison(
            source_mean=source_mean,
            synthetic_mean=synthetic_mean,
            absolute_mean_delta=delta,
        )

    max_tvd = max(item.total_variation_distance for item in marginal_comparisons.values())
    warnings = list(profile.warnings)
    if max_tvd > 0.10:
        warnings.append("population_mismatch: a categorical marginal has TV distance > 0.10")

    return PopulationDiagnostics(
        source_households=profile.source_households,
        synthetic_households=len(generated),
        marginal_comparisons=marginal_comparisons,
        numeric_comparisons=numeric_comparisons,
        max_total_variation_distance=max_tvd,
        warnings=tuple(dict.fromkeys(warnings)),
    )
