from synapse_realworld.projects.laa import build_laa_demo_world
from synapse_realworld.simulation import Scenario


def test_simulation_is_reproducible_for_same_seed() -> None:
    world = build_laa_demo_world(seed=42)
    scenario = Scenario(scenario_id="baseline")
    first = world.simulate(scenario, population_size=250, seed=42)
    second = world.simulate(scenario, population_size=250, seed=42)
    assert first.choice_share == second.choice_share
    assert first.laa_share == second.laa_share


def test_price_increase_does_not_raise_laa_share_in_demo_model() -> None:
    world = build_laa_demo_world(seed=42)
    baseline = world.simulate(Scenario(scenario_id="base"), population_size=2500, seed=7)
    higher = world.simulate(
        Scenario(scenario_id="plus-10", price_change_pct=0.10),
        population_size=2500,
        seed=7,
    )
    assert higher.laa_share <= baseline.laa_share
