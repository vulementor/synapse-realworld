from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from synapse_realworld.domain.enums import (
    DecisionStage,
    InventoryState,
    OutsideOption,
    ProductType,
    PurchasePurpose,
    ReasonCode,
    ReasonDirection,
)


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Project(DomainModel):
    project_id: UUID = Field(default_factory=uuid4)
    project_code: str
    project_name: str


class Unit(DomainModel):
    unit_id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    unit_code: str
    product_type: ProductType
    inventory_state: InventoryState = InventoryState.AVAILABLE
    lot_area_m2: float | None = Field(default=None, gt=0)
    built_area_m2: float | None = Field(default=None, gt=0)
    corner_flag: bool = False
    orientation: str | None = None
    park_distance_m: float | None = Field(default=None, ge=0)
    gate_distance_m: float | None = Field(default=None, ge=0)


class Offer(DomainModel):
    offer_id: UUID = Field(default_factory=uuid4)
    unit_id: UUID | None = None
    product_type: ProductType | None = None
    list_price: float = Field(gt=0)
    net_price: float | None = Field(default=None, gt=0)
    discount_pct: float = Field(default=0.0, ge=0, le=1)
    incentive_cash: float = Field(default=0.0, ge=0)
    payment_plan_code: str
    down_payment_pct: float = Field(default=0.3, ge=0, le=1)
    monthly_payment_est: float = Field(default=0.0, ge=0)
    effective_from: datetime
    effective_to: datetime | None = None
    source_id: str

    @model_validator(mode="after")
    def validate_effective_range(self) -> Offer:
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be later than effective_from")
        return self

    @property
    def effective_price(self) -> float:
        if self.net_price is not None:
            return self.net_price
        return self.list_price * (1 - self.discount_pct) - self.incentive_cash


class Household(DomainModel):
    household_id: UUID = Field(default_factory=uuid4)
    purchase_purpose: PurchasePurpose = PurchasePurpose.UNKNOWN
    household_size_band: Literal["1", "2", "3-4", "5+", "unknown"] = "unknown"
    children_band: Literal["0", "1", "2+", "unknown"] = "unknown"
    income_midpoint_million: float | None = Field(default=None, ge=0)
    liquid_capital_million: float | None = Field(default=None, ge=0)
    max_monthly_payment_million: float | None = Field(default=None, ge=0)
    purchase_horizon_days: int | None = Field(default=None, ge=0)
    workplace_zone: str | None = None
    commute_tolerance_min: float | None = Field(default=None, ge=0)
    preferred_product_type: ProductType | None = None
    profile_confidence: float = Field(default=0.5, ge=0, le=1)


class ReasonObservation(DomainModel):
    reason_id: UUID = Field(default_factory=uuid4)
    household_id: UUID
    reason_code: ReasonCode
    direction: ReasonDirection
    confidence: float = Field(ge=0, le=1)
    evidence_type: Literal["explicit", "inferred"]
    observed_at: datetime
    source_ref: str


class ChoiceAlternative(DomainModel):
    alternative_id: str
    alternative_type: Literal[
        "laa_unit",
        "competitor_project",
        "land_house",
        "continue_renting",
        "postponed",
        "no_purchase",
    ]
    unit: Unit | None = None
    offer: Offer | None = None
    commute_min: float | None = Field(default=None, ge=0)
    availability_confirmed: bool = True
    outside_option: OutsideOption | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> ChoiceAlternative:
        if self.alternative_type == "laa_unit":
            if self.unit is None or self.offer is None:
                raise ValueError("laa_unit alternatives require both unit and offer")
            if self.outside_option is not None:
                raise ValueError("laa_unit cannot also be an outside option")
        elif self.outside_option is None:
            raise ValueError("non-LAA alternatives require outside_option")
        return self


class ChoiceEvent(DomainModel):
    choice_event_id: UUID = Field(default_factory=uuid4)
    household_id: UUID
    occurred_at: datetime
    stage: DecisionStage
    alternatives: tuple[ChoiceAlternative, ...]
    selected_alternative_id: str | None = None
    source_id: str

    @model_validator(mode="after")
    def validate_choice_set(self) -> ChoiceEvent:
        if not self.alternatives:
            raise ValueError("choice set cannot be empty")
        if not any(a.outside_option is not None for a in self.alternatives):
            raise ValueError("choice set must include at least one outside option")
        ids = {a.alternative_id for a in self.alternatives}
        if len(ids) != len(self.alternatives):
            raise ValueError("choice alternative ids must be unique")
        if self.selected_alternative_id is not None and self.selected_alternative_id not in ids:
            raise ValueError("selected alternative must exist in the choice set")
        return self
