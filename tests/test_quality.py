from datetime import datetime, timezone
from uuid import UUID

import pytest

from synapse_realworld.data import DataQualityError, validate_choice_set
from synapse_realworld.domain.enums import InventoryState, OutsideOption, ProductType
from synapse_realworld.domain.models import ChoiceAlternative, Offer, Unit


def test_quality_gate_rejects_unavailable_historical_unit() -> None:
    unit = Unit(
        project_id=UUID("11111111-1111-1111-1111-111111111111"),
        unit_code="TEST-1",
        product_type=ProductType.TOWNHOUSE,
        inventory_state=InventoryState.SOLD,
    )
    offer = Offer(
        unit_id=unit.unit_id,
        product_type=unit.product_type,
        list_price=2_000_000_000,
        payment_plan_code="P1",
        effective_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
        source_id="fixture",
    )
    alternatives = [
        ChoiceAlternative(
            alternative_id="TEST-1",
            alternative_type="laa_unit",
            unit=unit,
            offer=offer,
            availability_confirmed=True,
        ),
        ChoiceAlternative(
            alternative_id="OUT-RENT",
            alternative_type="continue_renting",
            outside_option=OutsideOption.CONTINUE_RENTING,
        ),
    ]

    with pytest.raises(DataQualityError) as exc:
        validate_choice_set(
            alternatives,
            as_of=datetime(2026, 9, 15, tzinfo=timezone.utc),
            fail_closed=True,
        )
    assert "unavailable_unit" in str(exc.value)
