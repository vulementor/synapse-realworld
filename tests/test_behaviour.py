from synapse_realworld.behaviour import BaselineUtilityModel
from synapse_realworld.domain.enums import PurchasePurpose
from synapse_realworld.domain.models import Household
from synapse_realworld.projects.laa.world import _laa_alternatives


def test_choice_probabilities_sum_to_one() -> None:
    household = Household(purchase_purpose=PurchasePurpose.OWN_STAY)
    probabilities = BaselineUtilityModel().probabilities(household, _laa_alternatives())
    assert abs(sum(probabilities.values()) - 1.0) < 1e-12
    assert all(value > 0 for value in probabilities.values())
