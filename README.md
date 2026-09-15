# Synapse Real-World Platform

**Synapse Real-World Platform** is a library-first platform for modeling, simulating, validating, and governing real-world decisions with calibrated behavioral models, empirical synthetic populations, versioned evidence, spatial features, uncertainty, and agentic interfaces.

The first reference implementation is **Lan Anh Avenue (LAA) Decision Twin / Synthetic Market**: a real-estate market model that reconstructs historical buyer choice sets and estimates how demand changes when **price × payment plan × commute × product type** changes.

> The goal is not to build another CRM, chatbot, or 3D showroom. The goal is to build a reproducible decision layer that can answer counterfactual questions, quantify uncertainty, and validate predictions against real-world outcomes.

## Core principles

- **Library-first**: Python SDK is the source of truth; CLI and future APIs are adapters.
- **Append-only evidence**: source observations are preserved with provenance and deterministic dedupe keys.
- **Time-correct decisions**: historical choice sets reflect inventory, offers and buyer evidence actually available at decision time.
- **Outside options are mandatory**: competitor, land/house, rent, postpone, or no purchase.
- **Behavior before spectacle**: prove calibrated decision models before investing heavily in BIM/3D/Spatial World layers.
- **LLM is not the probability engine**: LLMs may extract reasons, summarize context, and explain outputs; calibrated statistical/ML models produce core choice probabilities.
- **Empirical synthetic population**: synthetic households are fitted from observed qualification evidence and preserve joint feature combinations.
- **Uncertainty is explicit**: scenario results expose point estimates plus ensemble p05/p50/p95 rather than a single false-precision number.
- **Reproducibility**: simulations, source snapshots, population profiles and model artifacts carry input/version/code metadata.
- **Privacy by design**: historical IDs are not persisted into empirical population profiles; PII remains outside the analytical domain.
- **Human-governed models**: training creates a candidate; validation and approval are explicit append-only decisions.
- **Human-governed actions**: v0.x provides decision support, not autonomous pricing, financing, legal, or customer execution.

## Platform layers

```text
Data Sources
CRM · SAP · Inventory · Offers · Ads · Sales · GIS · Market
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
      ├──────────────► Temporal Spatial Evidence
      │                workplace anchors · travel time · reliability
      │
      ▼
Decision Dataset
Time-correct snapshots · future-leakage guard · temporal holdout
      │
      ├──────────────► Behaviour Engine
      │                multinomial logit · bootstrap · diagnostics
      │
      └──────────────► Empirical Population Fitter
                       qualification evidence · joint prototypes
                               │
                               ▼
                     Synthetic Market Population
                         5k–10k+ households
                               │
                               ▼
                         Scenario Ensemble
                  price · payment · commute · product
                               │
                               ▼
                  Point estimate + uncertainty
                     p05 · p50 · p95 · min/max
                               │
                               ▼
                 Real-world experiment feedback

Calibrated model
      │
      ▼
Immutable Model Artifact
code SHA · dataset snapshot · metrics · bootstrap vectors
      │
      ▼
candidate → validated → approved/rejected → archived
```

Future layers can add richer competitor worlds, GIS/BIM/3D, IoT, construction, facility, and autonomous-asset intelligence without changing the core decision contracts.

## Current scope: v0.4 Synthetic Market

The codebase now provides:

- immutable canonical domain models with Pydantic;
- append-only `CanonicalEvent` and `SourceSnapshot` evidence contracts;
- deterministic idempotency and SHA-256 source snapshot fingerprints;
- DuckDB local event/snapshot persistence;
- PostgreSQL production event/snapshot persistence adapter + SQL migration;
- Sales Capture, inventory, offer and verified-outcome adapters;
- declarative source mapping + canonical JSONL integration seam;
- deterministic pseudonymous analytics identity mapping;
- temporal choice-set reconstruction and mandatory outside options;
- leakage-safe historical Decision Dataset builder;
- temporal workplace anchors and travel-time evidence;
- chronological train/holdout split;
- trainable multinomial-logit baseline;
- bootstrap coefficient intervals and retained full bootstrap parameter vectors;
- holdout segment diagnostics and uniform-choice baseline comparison;
- immutable governed model artifacts and append-only approval lifecycle;
- empirical population fitting from qualification events, not only final buyers;
- ID-free household feature prototypes with deterministic population content hash;
- joint household bootstrap preserving observed cross-feature relationships;
- population diagnostics using marginal TV distance and numeric mean comparisons;
- real-data scenario simulator from temporal units/offers/travel evidence;
- uncertainty ensemble using common random numbers across bootstrap parameter vectors;
- mean / p05 / p50 / p95 / min / max for LAA share, outside options and alternatives;
- approved-model requirement for scenario uncertainty by default;
- CLI workflows and GitHub Actions end-to-end Synthetic Market tests.

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

## Real-data → Synthetic Market workflow

The files under `examples/data/` are synthetic fixtures and contain no real customer information.

```bash
DB=./synapse.duckdb
REGISTRY=./model_registry
POPULATION=./population_profile.json

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

synapse-realworld fit-population \
  --db "$DB" \
  --profile-name laa-market-2026-09 \
  --minimum-profile-confidence 0.3 \
  --diagnostic-population-size 5000 \
  --output "$POPULATION"

synapse-realworld calibrate \
  --units-csv examples/data/laa_unit_versions_sample.csv \
  --offers-csv examples/data/laa_offers_sample.csv \
  --travel-times-csv examples/data/laa_travel_times_sample.csv \
  --project-anchor-id LAA \
  --db "$DB" \
  --registry-dir "$REGISTRY" \
  --model-version v0.4 \
  --code-commit-sha "$(git rev-parse HEAD)" \
  --bootstrap-samples 100 \
  --output calibration.json
```

Calibration registers a **candidate**. It does not auto-approve it.

```bash
ARTIFACT_ID=<uuid-from-calibration-output>

synapse-realworld model-decide "$ARTIFACT_ID" \
  --status validated \
  --decided-by data-lead \
  --reason "Temporal holdout and diagnostics reviewed" \
  --registry-dir "$REGISTRY"

synapse-realworld model-decide "$ARTIFACT_ID" \
  --status approved \
  --decided-by business-owner \
  --reason "Approved for bounded decision support" \
  --registry-dir "$REGISTRY"
```

Then run a scenario with uncertainty:

```bash
synapse-realworld simulate-uncertainty "$ARTIFACT_ID" \
  --population-profile "$POPULATION" \
  --units-csv examples/data/laa_unit_versions_sample.csv \
  --offers-csv examples/data/laa_offers_sample.csv \
  --travel-times-csv examples/data/laa_travel_times_sample.csv \
  --project-anchor-id LAA \
  --as-of 2026-09-15T08:00:00+07:00 \
  --registry-dir "$REGISTRY" \
  --scenario-id laa-price-plus-5 \
  --price-change 0.05 \
  --population-size 10000 \
  --output scenario_price_plus_5.json
```

The result includes a central point estimate plus uncertainty summaries for LAA share, outside-option share, individual alternatives and segment LAA share.

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

The library also exposes empirical population fitting, real-data simulator factories, governed model registry APIs, and registered-model uncertainty simulation for integration into other harnesses.

## Repository layout

```text
src/synapse_realworld/
  adapters/        # CSV/JSONL/source/spatial mapping adapters
  behaviour/       # utility, calibration, bootstrap diagnostics, workflow
  data/            # choice sets, projection, datasets, quality/training
  domain/          # canonical contracts, events, temporal identity
  ingestion/       # idempotent ingestion pipeline
  persistence/     # DuckDB local + PostgreSQL production stores
  population/      # empirical fitting, ID-free prototypes, generators, diagnostics
  registry/        # immutable model artifacts + governance decisions
  simulation/      # scenario engine, real-data factory, uncertainty ensemble
  spatial/         # temporal location anchors and travel-time features
  projects/laa/    # Lan Anh Avenue reference implementation
  cli.py           # core CLI commands
  cli_market.py    # Synthetic Market CLI extension
  cli_entry.py     # composed CLI entrypoint
examples/data/      # synthetic pipeline fixtures
sql/postgres/       # production migrations
tests/              # unit/integration/E2E-support tests
docs/               # architecture and implementation notes
```

## LAA decision questions

1. What happens to LAA choice share when effective price changes ±3–5%, and what is the p05–p95 uncertainty range?
2. What happens when net price stays constant but near-term monthly cash-flow burden changes?
3. How does measured commute vs perceived commute affect preference and campaign response?
4. How do households substitute between townhouse / garden townhouse / villa / shophouse and outside options?
5. Which segments are most sensitive to each scenario, and is the conclusion stable across bootstrap model fits?

## Roadmap

- **v0.1 — Foundation:** contracts, quality gates, deterministic demo simulation. ✅
- **v0.2 — Real data pipeline:** event store, snapshots, adapters, historical assembly, trainable logit baseline. ✅
- **v0.3 — Calibrated Decision Twin:** uncertainty diagnostics, temporal commute, governed model registry. ✅
- **v0.4 — Synthetic Market:** empirical population fitting, approved-model scenario ensembles, p05/p50/p95 uncertainty. 🚧
- **v0.5 — Experiment loop:** prediction registry, real A/B outcomes, champion/challenger and recalibration triggers.
- **v1.x — Spatial Real-World:** richer GIS/BIM/3D/IoT layers and autonomous-asset intelligence.

See:

- [`docs/REAL_DATA_PIPELINE_V0_2.md`](docs/REAL_DATA_PIPELINE_V0_2.md)
- [`docs/CALIBRATED_DECISION_TWIN_V0_3.md`](docs/CALIBRATED_DECISION_TWIN_V0_3.md)
- [`docs/SYNTHETIC_MARKET_V0_4.md`](docs/SYNTHETIC_MARKET_V0_4.md)

## Important boundary

The repository fixtures and LAA demo values remain **synthetic placeholders**. An empirical population fitted from CRM/Sales qualification evidence represents the **observed evidence base**, not automatically the total addressable market or all households around LAA.

Real production use must account for evidence quality and potential biases such as campaign/channel acquisition bias, missing offline buyers, nonresponse, competitor exposure, changing macro conditions, and external demographic/workforce constraints. Model approval is a governance record, not proof of market truth.

The platform must not be used to make autonomous legally binding pricing, financing, credit, legal, or individual-customer decisions without the appropriate human controls and validation.

## License

License policy will be finalized before external production use. Until then, treat the repository as source-available for project development and review only.
