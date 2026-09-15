from datetime import datetime, timezone
from uuid import UUID

from synapse_realworld.data.dataset import DecisionDatasetBuilder
from synapse_realworld.domain.enums import DecisionStage, OutsideOption
from synapse_realworld.domain.models import ChoiceAlternative, ChoiceEvent
from synapse_realworld.domain.temporal import FeatureObservation


def test_decision_dataset_ignores_future_feature_observations() -> None:
    household_id = UUID("33333333-3333-3333-3333-333333333333")
    event_time = datetime(2026, 9, 10, tzinfo=timezone.utc)
    outside = ChoiceAlternative(
        alternative_id="OUT-RENT",
        alternative_type="continue_renting",
        outside_option=OutsideOption.CONTINUE_RENTING,
    )
    event = ChoiceEvent(
        household_id=household_id,
        occurred_at=event_time,
        stage=DecisionStage.QUALIFIED,
        alternatives=(outside,),
        source_id="crm:event-1",
    )
    observations = [
        FeatureObservation(
            household_id=household_id,
            feature_name="workplace_zone",
            value="VSIP III",
            observed_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
            source_id="crm:note-1",
        ),
        FeatureObservation(
            household_id=household_id,
            feature_name="max_monthly_payment_million",
            value=25,
            observed_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
            source_id="crm:note-future",
        ),
    ]

    row = DecisionDatasetBuilder().build(events=[event], observations=observations)[0]
    assert row.features == {"workplace_zone": "VSIP III"}
    assert "max_monthly_payment_million" not in row.features
