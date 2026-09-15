from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from synapse_realworld.domain.enums import InventoryState, OutsideOption, ProductType
from synapse_realworld.domain.models import ChoiceAlternative, Offer, Project, Unit
from synapse_realworld.simulation.engine import RealWorldSimulator


AS_OF = datetime(2026, 9, 15, tzinfo=timezone.utc)
PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")


def _laa_alternatives() -> tuple[ChoiceAlternative, ...]:
    project = Project(project_id=PROJECT_ID, project_code="LAA", project_name="Lan Anh Avenue")
    del project  # fixture boundary; future adapters load this from source repositories.

    specs = [
        ("LAA-TOWN-01", ProductType.TOWNHOUSE, 2_650_000_000, 17_000_000, 27.0),
        ("LAA-GARDEN-01", ProductType.GARDEN_TOWNHOUSE, 3_050_000_000, 19_000_000, 28.0),
        ("LAA-SHOP-01", ProductType.SHOPHOUSE, 3_650_000_000, 23_000_000, 29.0),
    ]
    alternatives: list[ChoiceAlternative] = []
    for code, product_type, price, monthly_payment, commute in specs:
        unit = Unit(
            project_id=PROJECT_ID,
            unit_code=code,
            product_type=product_type,
            inventory_state=InventoryState.AVAILABLE,
        )
        offer = Offer(
            unit_id=unit.unit_id,
            product_type=product_type,
            list_price=price,
            net_price=price,
            payment_plan_code="PLAN_A",
            down_payment_pct=0.3,
            monthly_payment_est=monthly_payment,
            effective_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
            source_id="demo:laa:offer-snapshot-2026-09-15",
        )
        alternatives.append(
            ChoiceAlternative(
                alternative_id=code,
                alternative_type="laa_unit",
                unit=unit,
                offer=offer,
                commute_min=commute,
                availability_confirmed=True,
            )
        )

    alternatives.extend(
        [
            ChoiceAlternative(
                alternative_id="OUT-COMPETITOR",
                alternative_type="competitor_project",
                outside_option=OutsideOption.COMPETITOR_PROJECT,
            ),
            ChoiceAlternative(
                alternative_id="OUT-RENT",
                alternative_type="continue_renting",
                outside_option=OutsideOption.CONTINUE_RENTING,
            ),
            ChoiceAlternative(
                alternative_id="OUT-POSTPONE",
                alternative_type="postponed",
                outside_option=OutsideOption.POSTPONED,
            ),
            ChoiceAlternative(
                alternative_id="OUT-NO-PURCHASE",
                alternative_type="no_purchase",
                outside_option=OutsideOption.NO_PURCHASE,
            ),
        ]
    )
    return tuple(alternatives)


def build_laa_demo_world(*, seed: int = 42, code_commit_sha: str = "dev") -> RealWorldSimulator:
    del seed  # reserved for future project-fixture randomization.
    choice_set = _laa_alternatives()
    return RealWorldSimulator(
        choice_set_factory=lambda household: choice_set,
        as_of=AS_OF,
        input_snapshot_id="laa-demo-snapshot-2026-09-15",
        code_commit_sha=code_commit_sha,
    )
