from __future__ import annotations

import random
from collections import Counter, defaultdict
from datetime import datetime
from typing import Callable, Iterable

from synapse_realworld.behaviour import BaselineUtilityModel
from synapse_realworld.data import validate_choice_set
from synapse_realworld.domain.models import ChoiceAlternative, Household, Offer
from synapse_realworld.population import SyntheticPopulationGenerator
from synapse_realworld.simulation.models import Scenario, SimulationMetadata, SimulationResult


ChoiceSetFactory = Callable[[Household], Iterable[ChoiceAlternative]]


class RealWorldSimulator:
    def __init__(
        self,
        *,
        choice_set_factory: ChoiceSetFactory,
        population_generator: SyntheticPopulationGenerator | None = None,
        behaviour_model: BaselineUtilityModel | None = None,
        as_of: datetime,
        input_snapshot_id: str,
        code_commit_sha: str = "dev",
    ):
        self.choice_set_factory = choice_set_factory
        self.population_generator = population_generator or SyntheticPopulationGenerator()
        self.behaviour_model = behaviour_model or BaselineUtilityModel()
        self.as_of = as_of
        self.input_snapshot_id = input_snapshot_id
        self.code_commit_sha = code_commit_sha

    @staticmethod
    def _apply_scenario(
        alternative: ChoiceAlternative,
        scenario: Scenario,
    ) -> ChoiceAlternative | None:
        if alternative.alternative_type != "laa_unit":
            return alternative

        assert alternative.unit is not None and alternative.offer is not None
        if (
            scenario.eligible_product_types is not None
            and alternative.unit.product_type.value not in scenario.eligible_product_types
        ):
            return None

        offer = alternative.offer
        net_price = offer.effective_price * (1 + scenario.price_change_pct)
        payment_plan_code = scenario.payment_plan_code or offer.payment_plan_code
        modified_offer = Offer(
            **{
                **offer.model_dump(),
                "net_price": net_price,
                "payment_plan_code": payment_plan_code,
                "monthly_payment_est": offer.monthly_payment_est * scenario.payment_multiplier,
            }
        )
        return ChoiceAlternative(
            **{
                **alternative.model_dump(exclude={"offer", "commute_min"}),
                "offer": modified_offer,
                "commute_min": (
                    alternative.commute_min * scenario.commute_multiplier
                    if alternative.commute_min is not None
                    else None
                ),
            }
        )

    def simulate(self, scenario: Scenario, *, population_size: int, seed: int) -> SimulationResult:
        households = self.population_generator.generate(population_size, seed=seed)
        rng = random.Random(seed)
        aggregate = Counter()
        segment_counts: dict[str, Counter] = defaultdict(Counter)
        dropped_alternatives = 0

        for household in households:
            original = tuple(self.choice_set_factory(household))
            transformed_list = []
            for alternative in original:
                updated = self._apply_scenario(alternative, scenario)
                if updated is None:
                    dropped_alternatives += 1
                    continue
                transformed_list.append(updated)
            transformed = tuple(transformed_list)
            validate_choice_set(transformed, as_of=self.as_of, fail_closed=True)
            probabilities = self.behaviour_model.probabilities(household, transformed)
            ids = list(probabilities)
            weights = [probabilities[key] for key in ids]
            selected = rng.choices(ids, weights=weights, k=1)[0]
            aggregate[selected] += 1
            segment_counts[household.purchase_purpose.value][selected] += 1

        total = sum(aggregate.values()) or 1
        choice_share = {key: count / total for key, count in sorted(aggregate.items())}

        laa_ids: set[str] = set()
        sample_household = households[0]
        for alt in self.choice_set_factory(sample_household):
            if alt.alternative_type == "laa_unit":
                laa_ids.add(alt.alternative_id)
        laa_share = sum(choice_share.get(key, 0.0) for key in laa_ids)

        segment_share: dict[str, dict[str, float]] = {}
        for segment, counts in sorted(segment_counts.items()):
            subtotal = sum(counts.values()) or 1
            segment_share[segment] = {
                key: count / subtotal for key, count in sorted(counts.items())
            }

        metadata = SimulationMetadata(
            scenario_id=scenario.scenario_id,
            model_version=self.behaviour_model.model_version,
            population_version=self.population_generator.population_version,
            random_seed=seed,
            population_size=population_size,
            input_snapshot_id=self.input_snapshot_id,
            code_commit_sha=self.code_commit_sha,
        )
        return SimulationResult(
            metadata=metadata,
            choice_share=choice_share,
            laa_share=laa_share,
            outside_option_share=1 - laa_share,
            segment_choice_share=segment_share,
            diagnostics={"scenario_dropped_alternatives": dropped_alternatives},
        )
