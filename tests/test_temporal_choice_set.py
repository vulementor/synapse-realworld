from datetime import datetime, timezone
from uuid import UUID

from synapse_realworld.data.choice_set import TemporalChoiceSetBuilder
from synapse_realworld.domain.enums import InventoryState, ProductType
from synapse_realworld.domain.models import Offer, Unit
from synapse_realworld.domain.temporal import UnitVersion


PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")
UNIT_ID = UUID("22222222-2222-2222-2222-222222222222")


def test_temporal_choice_set_uses_state_and_offer_active_at_event_time() -> None:
    available = Unit(
        unit_id=UNIT_ID,
        project_id=PROJECT_ID,
        unit_code="LAA-1",
        product_type=ProductType.TOWNHOUSE,
        inventory_state=InventoryState.AVAILABLE,
    )
    sold = available.model_copy(update={"inventory_state": InventoryState.SOLD})
    versions = [
        UnitVersion(
            unit=available,
            effective_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
            effective_to=datetime(2026, 9, 10, tzinfo=timezone.utc),
            source_id="inventory:v1",
        ),
        UnitVersion(
            unit=sold,
            effective_from=datetime(2026, 9, 10, tzinfo=timezone.utc),
            source_id="inventory:v2",
        ),
    ]
    offers = [
        Offer(
            unit_id=UNIT_ID,
            product_type=ProductType.TOWNHOUSE,
            list_price=2_500_000_000,
            payment_plan_code="P1",
            effective_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
            effective_to=datetime(2026, 9, 10, tzinfo=timezone.utc),
            source_id="price:v1",
        )
    ]
    builder = TemporalChoiceSetBuilder(unit_versions=versions, offers=offers)

    before_sale = builder.build(as_of=datetime(2026, 9, 5, tzinfo=timezone.utc))
    after_sale = builder.build(as_of=datetime(2026, 9, 12, tzinfo=timezone.utc))

    assert any(item.alternative_id == "LAA-1" for item in before_sale)
    assert not any(item.alternative_id == "LAA-1" for item in after_sale)
    assert any(item.outside_option is not None for item in after_sale)
