from __future__ import annotations

from synapse_realworld.domain.events import CanonicalEvent
from synapse_realworld.domain.models import Offer
from synapse_realworld.domain.temporal import UnitVersion


def unit_version_to_event(version: UnitVersion) -> CanonicalEvent:
    unit = version.unit
    payload = {
        "version_id": str(version.version_id),
        "project_id": str(unit.project_id),
        "unit_id": str(unit.unit_id),
        "unit_code": unit.unit_code,
        "product_type": unit.product_type.value,
        "inventory_state": unit.inventory_state.value,
        "lot_area_m2": unit.lot_area_m2,
        "built_area_m2": unit.built_area_m2,
        "corner_flag": unit.corner_flag,
        "orientation": unit.orientation,
        "park_distance_m": unit.park_distance_m,
        "gate_distance_m": unit.gate_distance_m,
        "effective_from": version.effective_from.isoformat(),
        "effective_to": version.effective_to.isoformat() if version.effective_to else None,
    }
    return CanonicalEvent(
        event_type="unit_version_observed",
        entity_type="unit",
        entity_id=str(unit.unit_id),
        occurred_at=version.effective_from,
        source_id=version.source_id,
        source_event_key=f"unit-version:{version.version_id}",
        payload=payload,
    )


def offer_to_event(offer: Offer) -> CanonicalEvent:
    entity_id = str(offer.unit_id) if offer.unit_id is not None else offer.product_type.value
    return CanonicalEvent(
        event_type="offer_observed",
        entity_type="unit" if offer.unit_id is not None else "product_type",
        entity_id=entity_id,
        occurred_at=offer.effective_from,
        source_id=offer.source_id,
        source_event_key=f"offer:{offer.offer_id}",
        payload=offer.model_dump(mode="json"),
    )
