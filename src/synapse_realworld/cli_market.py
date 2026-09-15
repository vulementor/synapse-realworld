from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from synapse_realworld.adapters import (
    load_offers_csv,
    load_travel_times_csv,
    load_unit_versions_csv,
)
from synapse_realworld.persistence import DuckDBStore
from synapse_realworld.population import (
    EmpiricalPopulationGenerator,
    EmpiricalPopulationProfile,
    diagnose_population,
    fit_population_from_events,
)
from synapse_realworld.registry import FileModelRegistry
from synapse_realworld.simulation import (
    Scenario,
    build_real_data_simulator,
    simulate_registered_model_uncertainty,
)


def _parse_as_of(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise typer.BadParameter("as-of must include a timezone offset")
    return parsed


def _load_population_profile(path: Path) -> EmpiricalPopulationProfile:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "profile" in payload:
        payload = payload["profile"]
    return EmpiricalPopulationProfile.model_validate(payload)


def register_market_commands(app: typer.Typer) -> None:
    @app.command("fit-population")
    def fit_population(
        db: Annotated[Path, typer.Option(help="DuckDB event store path")] = Path(
            "synapse.duckdb"
        ),
        profile_name: Annotated[
            str, typer.Option(help="Logical empirical population name")
        ] = "laa-empirical-v0.4",
        as_of: Annotated[
            str | None,
            typer.Option(help="Optional timezone-aware ISO cutoff for source observations"),
        ] = None,
        minimum_profile_confidence: Annotated[
            float,
            typer.Option(min=0, max=1, help="Minimum structured-profile completeness"),
        ] = 0.3,
        diagnostic_population_size: Annotated[
            int, typer.Option(min=1, help="Synthetic sample used to validate fitted marginals")
        ] = 5000,
        seed: Annotated[int, typer.Option(help="Reproducible population seed")] = 42,
        output: Annotated[
            Path, typer.Option(help="Population profile/result JSON")
        ] = Path("population_profile.json"),
    ) -> None:
        """Fit an ID-free empirical population from qualification evidence."""
        cutoff = _parse_as_of(as_of)
        with DuckDBStore(db) as store:
            events = tuple(store.list_events())
        result = fit_population_from_events(
            events,
            profile_name=profile_name,
            as_of=cutoff,
            minimum_profile_confidence=minimum_profile_confidence,
            diagnostic_population_size=diagnostic_population_size,
            seed=seed,
        )
        payload = {
            **result.model_dump(mode="json"),
            "population_version": result.profile.population_version,
            "content_hash": result.profile.content_hash,
        }
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        output.write_text(rendered + "\n", encoding="utf-8")
        typer.echo(rendered)

    @app.command("simulate-uncertainty")
    def simulate_uncertainty(
        artifact_id: Annotated[UUID, typer.Argument(help="Registered model artifact UUID")],
        population_profile: Annotated[
            Path, typer.Option(exists=True, readable=True, help="Empirical population JSON")
        ],
        units_csv: Annotated[
            Path, typer.Option(exists=True, readable=True, help="Temporal unit versions CSV")
        ],
        offers_csv: Annotated[
            Path, typer.Option(exists=True, readable=True, help="Temporal offers CSV")
        ],
        as_of: Annotated[
            str, typer.Option(help="Timezone-aware ISO timestamp for scenario inventory")
        ],
        registry_dir: Annotated[
            Path, typer.Option(help="Append-only model registry directory")
        ] = Path("model_registry"),
        travel_times_csv: Annotated[
            Path | None,
            typer.Option(exists=True, readable=True, help="Optional temporal travel-time CSV"),
        ] = None,
        project_anchor_id: Annotated[
            str, typer.Option(help="Project destination anchor")
        ] = "LAA",
        scenario_id: Annotated[str, typer.Option(help="Scenario identifier")] = "scenario-v0.4",
        price_change: Annotated[
            float, typer.Option(help="Relative price change, e.g. 0.05 = +5%")
        ] = 0.0,
        payment_multiplier: Annotated[
            float, typer.Option(min=0.01, help="Monthly-payment multiplier")
        ] = 1.0,
        commute_multiplier: Annotated[
            float, typer.Option(min=0.01, help="Commute multiplier")
        ] = 1.0,
        eligible_product_types: Annotated[
            str | None,
            typer.Option(help="Optional comma-separated product types"),
        ] = None,
        population_size: Annotated[
            int, typer.Option(min=1, help="Synthetic households per uncertainty run")
        ] = 5000,
        replications_per_parameter: Annotated[
            int, typer.Option(min=1, help="Monte Carlo replications per bootstrap vector")
        ] = 1,
        seed: Annotated[int, typer.Option(help="Common random-number seed")] = 42,
        allow_unapproved: Annotated[
            bool, typer.Option(help="Allow exploratory simulation with non-approved model")
        ] = False,
        output: Annotated[
            Path | None, typer.Option(help="Optional uncertainty-result JSON")
        ] = None,
    ) -> None:
        """Run p05/p50/p95 scenario uncertainty with a governed model and fitted population."""
        scenario_time = _parse_as_of(as_of)
        assert scenario_time is not None
        registry = FileModelRegistry(registry_dir)
        registered = registry.get(artifact_id)
        if registered is None:
            raise typer.BadParameter(f"unknown model artifact: {artifact_id}")

        profile = _load_population_profile(population_profile)
        population_generator = EmpiricalPopulationGenerator(profile)
        unit_versions = load_unit_versions_csv(units_csv)
        offers = load_offers_csv(offers_csv)
        travel_times = (
            load_travel_times_csv(travel_times_csv) if travel_times_csv is not None else ()
        )
        base = build_real_data_simulator(
            unit_versions=unit_versions,
            offers=offers,
            as_of=scenario_time,
            population_generator=population_generator,
            input_snapshot_id=registered.artifact.dataset_snapshot_id,
            travel_times=travel_times,
            project_anchor_id=project_anchor_id,
            code_commit_sha=registered.artifact.code_commit_sha,
        )
        product_types = (
            tuple(item.strip() for item in eligible_product_types.split(",") if item.strip())
            if eligible_product_types
            else None
        )
        scenario = Scenario(
            scenario_id=scenario_id,
            price_change_pct=price_change,
            payment_multiplier=payment_multiplier,
            commute_multiplier=commute_multiplier,
            eligible_product_types=product_types,
        )
        uncertainty = simulate_registered_model_uncertainty(
            registered_model=registered,
            base_simulator=base,
            scenario=scenario,
            population_generator=population_generator,
            population_size=population_size,
            seed=seed,
            replications_per_parameter=replications_per_parameter,
            allow_unapproved=allow_unapproved,
        )
        diagnostic_size = min(max(population_size, 1000), 5000)
        population_diagnostics = diagnose_population(
            profile=profile,
            synthetic=population_generator.generate(diagnostic_size, seed=seed),
        )
        payload = {
            "uncertainty": uncertainty.model_dump(mode="json"),
            "population_diagnostics": population_diagnostics.model_dump(mode="json"),
        }
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        if output is not None:
            output.write_text(rendered + "\n", encoding="utf-8")
        typer.echo(rendered)
