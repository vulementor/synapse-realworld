from __future__ import annotations

import json
from typing import Annotated

import typer

from synapse_realworld.domain.models import Household, Offer, Unit
from synapse_realworld.projects.laa import build_laa_demo_world
from synapse_realworld.simulation import Scenario

app = typer.Typer(
    name="synapse-realworld",
    help="Synapse Real-World Platform CLI",
    no_args_is_help=True,
)


@app.command()
def demo(
    population: Annotated[int, typer.Option(min=1, help="Synthetic household count")] = 1000,
    seed: Annotated[int, typer.Option(help="Reproducible random seed")] = 42,
    price_change: Annotated[
        float, typer.Option(help="Relative LAA price change, e.g. 0.05 = +5%")
    ] = 0.0,
    payment_multiplier: Annotated[
        float, typer.Option(min=0.01, help="Multiplier applied to modeled monthly payment")
    ] = 1.0,
    commute_multiplier: Annotated[
        float, typer.Option(min=0.01, help="Multiplier applied to modeled commute")
    ] = 1.0,
) -> None:
    """Run the deterministic LAA reference simulation."""
    world = build_laa_demo_world(seed=seed)
    result = world.simulate(
        Scenario(
            scenario_id="cli-demo",
            price_change_pct=price_change,
            payment_multiplier=payment_multiplier,
            commute_multiplier=commute_multiplier,
        ),
        population_size=population,
        seed=seed,
    )
    typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command("schema")
def schema_command(
    entity: Annotated[str, typer.Argument(help="household | unit | offer")],
) -> None:
    """Print the JSON schema for a canonical domain entity."""
    registry = {"household": Household, "unit": Unit, "offer": Offer}
    try:
        model = registry[entity.lower()]
    except KeyError as exc:
        raise typer.BadParameter(f"unknown entity: {entity}") from exc
    typer.echo(json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
