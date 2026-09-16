from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.domain.events import CanonicalEvent


class AuditModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoverageMetric(AuditModel):
    present: int = Field(ge=0)
    denominator: int = Field(ge=0)
    rate: float = Field(ge=0, le=1)


class ReadinessCheck(AuditModel):
    name: str
    status: str
    evidence_count: int = Field(ge=0)
    notes: tuple[str, ...] = ()


class LAADataAudit(AuditModel):
    total_events: int = Field(ge=0)
    households: int = Field(ge=0)
    qualified_households: int = Field(ge=0)
    verified_outcomes: int = Field(ge=0)
    site_tours: int = Field(ge=0)
    trainable_choice_events: int = Field(ge=0)
    event_types: dict[str, int]
    sources: dict[str, int]
    coverage: dict[str, CoverageMetric]
    readiness: dict[str, ReadinessCheck]
    training_ready: bool
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _coverage(values: set[str], denominator: set[str]) -> CoverageMetric:
    count = len(values & denominator)
    total = len(denominator)
    return CoverageMetric(
        present=count,
        denominator=total,
        rate=(count / total if total else 0.0),
    )


def _status(evidence_count: int, *, minimum: int = 1) -> str:
    return "ready" if evidence_count >= minimum else "missing"


def audit_laa_events(events: Iterable[CanonicalEvent]) -> LAADataAudit:
    materialized = tuple(events)
    event_types = Counter(event.event_type for event in materialized)
    sources = Counter(event.source_id for event in materialized)

    household_events = [event for event in materialized if event.entity_type == "household"]
    households = {event.entity_id for event in household_events}
    qualification = [
        event for event in household_events if event.event_type == "qualification_observed"
    ]
    qualified_households = {event.entity_id for event in qualification}

    field_households: dict[str, set[str]] = defaultdict(set)
    for event in qualification:
        for field in (
            "purchase_purpose",
            "household_size_band",
            "children_band",
            "household_income_band",
            "liquid_capital_band",
            "max_monthly_payment_band",
            "purchase_horizon",
            "workplace_zone",
            "stated_max_travel_min",
            "preferred_product_type",
            "shortlisted_unit_code",
            "competitor_mentioned",
            "outside_option",
        ):
            value = event.payload.get(field)
            if value not in (None, "", "unknown"):
                field_households[field].add(event.entity_id)

    reason_households = {
        event.entity_id
        for event in household_events
        if event.event_type == "reason_observed"
    }
    outcome_events = [
        event
        for event in household_events
        if event.event_type in {"decision_outcome_observed", "decision_outcome_verified"}
    ]
    verified_outcomes = [
        event
        for event in outcome_events
        if event.payload.get("verified", True) not in {False, "false", "False", "0"}
    ]
    outside_households = set(field_households["outside_option"])
    outside_households.update(
        event.entity_id
        for event in outcome_events
        if event.payload.get("outside_option") not in (None, "", "unknown")
    )

    site_tour_events = [
        event
        for event in household_events
        if event.event_type in {"tour_attended", "site_tour_attended", "site_tour_observed"}
    ]

    offer_events = [
        event
        for event in materialized
        if event.event_type in {"offer_observed", "offer_version_observed"}
    ]
    inventory_events = [
        event
        for event in materialized
        if event.event_type in {"unit_inventory_observed", "unit_version_observed"}
    ]
    price_evidence = sum(
        1
        for event in offer_events
        if event.payload.get("list_price_vnd") not in (None, "")
        or event.payload.get("list_price") not in (None, "")
    )
    payment_evidence = sum(
        1
        for event in offer_events
        if any(
            event.payload.get(key) not in (None, "")
            for key in (
                "payment_plan_code",
                "monthly_payment_est",
                "down_payment_pct",
            )
        )
    )
    commute_evidence = len(field_households["workplace_zone"])
    product_evidence = len(inventory_events) + len(field_households["shortlisted_unit_code"])
    outside_evidence = len(outside_households)

    trainable_choice_events = sum(
        1
        for event in verified_outcomes
        if (
            event.payload.get("unit_code") not in (None, "")
            or event.payload.get("outside_option") not in (None, "")
        )
    )

    readiness = {
        "price": ReadinessCheck(
            name="price",
            status=_status(price_evidence),
            evidence_count=price_evidence,
            notes=("Requires time-versioned offer/price evidence.",),
        ),
        "payment": ReadinessCheck(
            name="payment",
            status=_status(payment_evidence),
            evidence_count=payment_evidence,
            notes=("Requires payment-plan or modeled cash-flow evidence.",),
        ),
        "commute": ReadinessCheck(
            name="commute",
            status=_status(commute_evidence),
            evidence_count=commute_evidence,
            notes=("Workplace-zone coverage is the minimum; routing evidence is still recommended.",),
        ),
        "product": ReadinessCheck(
            name="product",
            status=_status(product_evidence),
            evidence_count=product_evidence,
            notes=("Requires inventory/product evidence and preferably buyer shortlist evidence.",),
        ),
        "outside_options": ReadinessCheck(
            name="outside_options",
            status=_status(outside_evidence),
            evidence_count=outside_evidence,
            notes=("Lost/postponed decisions should record the real outside option.",),
        ),
    }

    coverage = {
        field: _coverage(values, qualified_households)
        for field, values in field_households.items()
    }
    coverage["reason"] = _coverage(reason_households, qualified_households)
    coverage["outside_option"] = _coverage(outside_households, qualified_households)

    blockers: list[str] = []
    if not qualified_households:
        blockers.append("no_structured_qualification_history")
    if not verified_outcomes:
        blockers.append("no_verified_decision_outcomes")
    if not inventory_events:
        blockers.append("no_temporal_inventory_evidence")
    if not offer_events:
        blockers.append("no_temporal_offer_evidence")
    for key, check in readiness.items():
        if check.status != "ready":
            blockers.append(f"readiness_missing:{key}")

    warnings: list[str] = []
    if qualified_households and coverage["outside_option"].rate < 0.5:
        warnings.append("outside_option_coverage_below_50_percent")
    if qualified_households and coverage["workplace_zone"].rate < 0.5:
        warnings.append("workplace_zone_coverage_below_50_percent")
    if qualified_households and coverage["reason"].rate < 0.5:
        warnings.append("reason_coverage_below_50_percent")
    if trainable_choice_events < 30:
        warnings.append("fewer_than_30_trainable_choice_events")

    return LAADataAudit(
        total_events=len(materialized),
        households=len(households),
        qualified_households=len(qualified_households),
        verified_outcomes=len(verified_outcomes),
        site_tours=len(site_tour_events),
        trainable_choice_events=trainable_choice_events,
        event_types=dict(sorted(event_types.items())),
        sources=dict(sorted(sources.items())),
        coverage=coverage,
        readiness=readiness,
        training_ready=not blockers and trainable_choice_events >= 30,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )
