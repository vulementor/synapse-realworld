from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    price_change_pct: float = Field(default=0.0, ge=-0.95, le=5.0)
    payment_multiplier: float = Field(default=1.0, gt=0)
    payment_plan_code: str | None = None
    commute_multiplier: float = Field(default=1.0, gt=0)
    eligible_product_types: tuple[str, ...] | None = None


class SimulationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    model_version: str
    population_version: str
    random_seed: int
    population_size: int
    input_snapshot_id: str
    code_commit_sha: str
    run_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SimulationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: SimulationMetadata
    choice_share: dict[str, float]
    laa_share: float
    outside_option_share: float
    segment_choice_share: dict[str, dict[str, float]]
    diagnostics: dict[str, Any] = Field(default_factory=dict)
