# Synapse Real-World Platform

**Synapse Real-World Platform** is a library-first platform for modeling, simulating, and validating real-world decisions with calibrated behavioral models, synthetic populations, versioned evidence, and agentic interfaces.

The first reference implementation is **Lan Anh Avenue (LAA) Decision Twin**: a real-estate synthetic market that reconstructs historical buyer choice sets and estimates how demand changes when **price × payment plan × commute × product type** changes.

> The goal is not to build another CRM, chatbot, or 3D showroom. The goal is to build a reproducible decision layer that can answer counterfactual questions and validate them against real-world outcomes.

## Core principles

- **Library-first**: Python SDK is the source of truth; CLI and future APIs are adapters.
- **Time-correct decisions**: every historical choice set must reflect inventory and offers actually available at decision time.
- **Outside options are mandatory**: competitor, land/house, rent, postpone, or no purchase.
- **Behavior before spectacle**: prove calibrated decision models before investing in Spatial/3D World layers.
- **LLM is not the probability engine**: LLMs may extract reasons, summarize context, and explain model outputs; calibrated statistical/ML models produce core choice probabilities.
- **Reproducibility**: every simulation records model version, population version, random seed, code commit, and input snapshot.
- **Privacy by design**: PII stays outside the analytical domain; analytics use pseudonymous identifiers and coarse bands.
- **Human-governed actions**: v0.x provides decision support, not autonomous pricing or legally binding execution.

## Platform layers

```text
Data Sources
CRM · SAP · Inventory · Offers · Ads · Sales interactions · GIS · Market
      │
      ▼
Canonical Event + Decision Model
Households · Units · Offers · Reasons · Choice Sets · Outcomes
      │
      ▼
Decision Dataset
Time-correct snapshots · provenance · quality gates
      │
      ├──────────────► Behaviour Engine
      │                choice model · calibration · uncertainty
      │
      └──────────────► Synthetic Population
                       empirical/IPF/probabilistic generation
                               │
                               ▼
                         Scenario Engine
                  price · payment · commute · product
                               │
                               ▼
                      Simulation + Backtest
                               │
                               ▼
                 Real-world experiment feedback
```

Future layers can add Spatial World, Digital Twin, IoT, construction, facility and autonomous-asset intelligence without changing the core decision contracts.

## Current scope: v0.1 foundation

The initial codebase provides:

- canonical domain models with Pydantic;
- event and reason taxonomies;
- scenario contracts and reproducible simulation metadata;
- in-memory reference repositories for local development/testing;
- a baseline utility/softmax choice engine;
- synthetic household generation;
- LAA reference project fixtures;
- CLI commands for demo simulation and schema inspection;
- data quality checks that fail closed on critical leakage/provenance problems;
- tests and CI scaffolding.

## Quick start

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -e ".[dev]"

synapse-realworld demo --population 1000 --seed 42
synapse-realworld schema household
pytest
```

Python SDK:

```python
from synapse_realworld.projects.laa import build_laa_demo_world
from synapse_realworld.simulation import Scenario

world = build_laa_demo_world(seed=42)
result = world.simulate(
    Scenario(
        scenario_id="laa-price-plus-5",
        price_change_pct=0.05,
        payment_plan_code="PLAN_A",
        commute_multiplier=1.0,
    ),
    population_size=1000,
    seed=42,
)

print(result.choice_share)
```

## Repository layout

```text
src/synapse_realworld/
  domain/          # canonical contracts
  data/            # repositories, snapshots, quality gates
  behaviour/       # utility + choice probability models
  population/      # synthetic population generation
  simulation/      # scenario runner + results
  projects/laa/    # Lan Anh Avenue reference implementation
  cli.py            # CLI adapter

tests/              # unit/integration tests
docs/               # architecture, schemas, implementation notes
```

## LAA MVP decision questions

1. What happens to choice share when effective price changes ±3–5%?
2. What happens when net price stays constant but near-term cash-flow burden changes?
3. How does measured commute vs perceived commute affect preference and campaign response?
4. How do households substitute between townhouse / garden townhouse / villa / shophouse and outside options?

## Roadmap

- **v0.1 — Foundation:** contracts, quality gates, deterministic demo simulation.
- **v0.2 — Real data adapters:** CRM/SAP/Ads/Inventory mappings, DuckDB/Postgres persistence, historical backfill.
- **v0.3 — Calibrated Decision Twin:** multinomial/mixed logit baseline, temporal holdout, calibration report.
- **v0.4 — Synthetic Market:** 5k–10k household population, uncertainty, scenario stress tests.
- **v0.5 — Experiment loop:** predicted-vs-actual campaign and offer validation.
- **v1.x — Spatial Real-World:** GIS/BIM/3D/IoT layers and autonomous-asset intelligence.

## Status

Early foundation. Interfaces will evolve quickly until the first LAA historical decision dataset is calibrated.

## License

License policy will be finalized before external production use. Until then, treat the repository as source-available for project development and review only.
