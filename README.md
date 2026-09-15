# Synapse Real-World Platform

**Synapse Real-World Platform** is a library-first platform for modeling, simulating, and validating real-world decisions with calibrated behavioral models, synthetic populations, versioned evidence, and agentic interfaces.

The first reference implementation is **Lan Anh Avenue (LAA) Decision Twin**: a real-estate synthetic market that reconstructs historical buyer choice sets and estimates how demand changes when **price × payment plan × commute × product type** changes.

> The goal is not to build another CRM, chatbot, or 3D showroom. The goal is to build a reproducible decision layer that can answer counterfactual questions and validate them against real-world outcomes.

## Core principles

- **Library-first**: Python SDK is the source of truth; CLI and future APIs are adapters.
- **Append-only evidence**: source observations are preserved with provenance and deterministic dedupe keys.
- **Time-correct decisions**: every historical choice set must reflect inventory and offers actually available at decision time.
- **Outside options are mandatory**: competitor, land/house, rent, postpone, or no purchase.
- **Behavior before spectacle**: prove calibrated decision models before investing in Spatial/3D World layers.
- **LLM is not the probability engine**: LLMs may extract reasons, summarize context, and explain outputs; calibrated statistical/ML models produce core choice probabilities.
- **Reproducibility**: simulations and source snapshots carry model/input/version metadata.
- **Privacy by design**: PII stays outside the analytical domain; analytics use pseudonymous identifiers and coarse bands.
- **Human-governed actions**: v0.x provides decision support, not autonomous pricing or legally binding execution.

## Platform layers

```text
Data Sources
CRM · SAP · Inventory · Offers · Ads · Sales interactions · GIS · Market
      │
      ▼
Source adapters / canonical JSONL
      │
      ▼
Append-only Canonical Event Store
DuckDB local · PostgreSQL production · source snapshots · provenance
      │
      ▼
Canonical Decision Model
Households · Units · Offers · Reasons · Choice Sets · Outcomes
      │
      ▼
Decision Dataset
Time-correct snapshots · future-leakage guard · temporal holdout
      │
      ├──────────────► Behaviour Engine
      │                multinomial logit · calibration · validation
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

## Current scope: v0.2 real-data pipeline

The codebase now provides:

- immutable canonical domain models with Pydantic;
- `CanonicalEvent` and `SourceSnapshot` append-only evidence contracts;
- deterministic idempotency and SHA-256 source snapshot fingerprints;
- DuckDB local event/snapshot persistence;
- PostgreSQL production event/snapshot persistence adapter + SQL migration;
- Sales Capture v0.2 adapter;
- inventory and offer temporal adapters;
- verified outcome adapter;
- declarative record-to-event mapping contract;
- canonical JSONL integration seam for external connectors/agent harnesses;
- deterministic pseudonymous analytics identity mapping;
- temporal choice-set reconstruction;
- feature/reason projections from canonical events;
- leakage-safe historical Decision Dataset builder;
- household snapshot conversion from operational bands;
- temporal train/holdout split;
- trainable multinomial-logit baseline;
- synthetic household generation and scenario engine from v0.1;
- CLI workflows and GitHub Actions end-to-end smoke tests.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\Activate.ps1  # Windows PowerShell

pip install -e ".[dev]"

synapse-realworld demo --population 1000 --seed 42
synapse-realworld schema household
pytest
```

## Real-data pipeline quick start

The files in `examples/data/` are synthetic and contain no real customer information.

```bash
DB=./synapse.duckdb

synapse-realworld init-store --db "$DB"

synapse-realworld ingest-sales \
  examples/data/laa_sales_capture_sample.csv \
  --db "$DB"

synapse-realworld ingest-outcomes \
  examples/data/laa_outcomes_sample.csv \
  --db "$DB"

synapse-realworld ingest-inventory \
  --units-csv examples/data/laa_unit_versions_sample.csv \
  --offers-csv examples/data/laa_offers_sample.csv \
  --db "$DB"

synapse-realworld store-stats --db "$DB"

synapse-realworld calibrate \
  --units-csv examples/data/laa_unit_versions_sample.csv \
  --offers-csv examples/data/laa_offers_sample.csv \
  --db "$DB" \
  --holdout-fraction 0.5 \
  --output calibration.json
```

For an external connector or agent harness, emit canonical events as JSONL:

```bash
synapse-realworld ingest-jsonl events.jsonl \
  --source-id crm-production \
  --db synapse.duckdb
```

## Python SDK

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
  adapters/        # CSV/JSONL/source mapping adapters
  behaviour/       # utility + trainable choice models
  data/            # choice sets, projection, datasets, quality/training
  domain/          # canonical contracts, events, temporal identity
  ingestion/       # idempotent ingestion pipeline
  persistence/     # DuckDB local + PostgreSQL production stores
  population/      # synthetic population generation
  simulation/      # scenario runner + results
  projects/laa/    # Lan Anh Avenue reference implementation
  cli.py           # CLI adapter
examples/data/      # synthetic pipeline fixtures
sql/postgres/       # production migrations
tests/              # unit/integration tests
docs/               # architecture and implementation notes
```

## LAA MVP decision questions

1. What happens to choice share when effective price changes ±3–5%?
2. What happens when net price stays constant but near-term cash-flow burden changes?
3. How does measured commute vs perceived commute affect preference and campaign response?
4. How do households substitute between townhouse / garden townhouse / villa / shophouse and outside options?

## Roadmap

- **v0.1 — Foundation:** contracts, quality gates, deterministic demo simulation. ✅
- **v0.2 — Real data pipeline:** event store, source snapshots, adapters, historical assembly, trainable logit baseline. 🚧
- **v0.3 — Calibrated Decision Twin:** real LAA backfill, richer validation, confidence intervals, model registry.
- **v0.4 — Synthetic Market:** 5k–10k calibrated households, uncertainty, scenario stress tests.
- **v0.5 — Experiment loop:** predicted-vs-actual campaign and offer validation.
- **v1.x — Spatial Real-World:** GIS/BIM/3D/IoT layers and autonomous-asset intelligence.

See [`docs/REAL_DATA_PIPELINE_V0_2.md`](docs/REAL_DATA_PIPELINE_V0_2.md) for the current operational flow.

## Important boundary

The reference values and coefficients in the LAA demo world remain **synthetic placeholders**. They are not production facts and must not be used for actual pricing, sales, investment, or customer decisions until calibrated and validated against versioned real LAA data.

## License

License policy will be finalized before external production use. Until then, treat the repository as source-available for project development and review only.
