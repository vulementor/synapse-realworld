# Synapse Real-World Platform

**Synapse Real-World Platform** is a library-first platform for reconstructing, simulating, validating and prospectively testing real-world decisions with versioned evidence, calibrated behavioural models, empirical synthetic populations and human-governed model operations.

The first reference implementation is the **Lan Anh Avenue (LAA) Decision Twin / Synthetic Market**.

> The goal is not to build another CRM, chatbot or 3D showroom. The goal is to build a reproducible decision layer that can answer counterfactual questions, quantify uncertainty and learn from predicted-vs-actual outcomes.

## Current status — v0.8

The current release line implements:

- canonical append-only evidence contracts;
- DuckDB local persistence and a PostgreSQL production seam;
- temporal inventory / offer reconstruction;
- leakage-safe historical choice datasets;
- multinomial-logit calibration with bootstrap uncertainty;
- empirical ID-free synthetic population fitting;
- governed model lifecycle: `candidate → validated → approved/rejected → archived`;
- scenario uncertainty with p05 / p50 / p95;
- prospective experiment prediction lock;
- assignment receipts and experiment QA;
- predicted-vs-actual evaluation and model scorecards;
- LAA production connector profiles and `data-audit` readiness gates;
- immutable **LAA Real Dataset Snapshot #001** workflow;
- governed **LAA Calibration Run #001** workflow;
- governed **LAA Prospective Experiment #001 — Commute Perception** workflow.

The three LAA milestone workflows are implemented, but the repository does **not** claim that the real production Snapshot #001, Calibration Run #001 or Experiment #001 have been completed merely because synthetic CI fixtures pass.

See [`docs/CURRENT_STATUS_V0_8.md`](docs/CURRENT_STATUS_V0_8.md) for the implementation source of truth.

## Install on Windows

Requirements:

- Git
- Python 3.11
- Windows PowerShell 5.1+ or PowerShell 7+

Clone and install:

```powershell
git clone https://github.com/vulementor/synapse-realworld.git
cd synapse-realworld
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

The setup helper creates `.venv`, installs `.[dev]`, verifies package version and checks the CLI.

Activate manually when needed:

```powershell
.\.venv\Scripts\Activate.ps1
```

Full installation and troubleshooting guide:

[`docs/INSTALL_AND_TEST.md`](docs/INSTALL_AND_TEST.md)

## Run tests on Windows

Fast smoke test:

```powershell
.\scripts\test.ps1 -Mode quick
```

Core lint + full pytest:

```powershell
.\scripts\test.ps1 -Mode unit
```

LAA v0.8 milestone contracts:

```powershell
.\scripts\test.ps1 -Mode milestones
```

LAA connector / productionization contracts:

```powershell
.\scripts\test.ps1 -Mode productionization
```

Everything:

```powershell
.\scripts\test.ps1 -Mode full
```

GitHub also runs the same setup/test path on a Windows runner through the **Windows Local Runbook** workflow.

## Manual install

Windows:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
synapse-realworld --help
pytest
```

Linux / macOS:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
ruff check .
pytest
synapse-realworld demo --population 50 --seed 42
```

Optional PostgreSQL dependency:

```bash
python -m pip install -e ".[dev,postgres]"
```

## Quick CLI smoke

```powershell
synapse-realworld demo --population 1000 --seed 42
synapse-realworld schema household
synapse-realworld laa-connectors
```

The files under `examples/data/` are **synthetic fixtures** and contain no real customer data.

## Platform flow

```text
CRM / SAP / Inventory / Offers / Ads / Sales / GIS
                    │
                    ▼
       Source connectors + provenance
                    │
                    ▼
       Append-only Canonical Event Store
                    │
                    ▼
      Time-correct Decision Dataset
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
Behaviour calibration     Population fitting
        │                       │
        └───────────┬───────────┘
                    ▼
             Synthetic Market
                    │
                    ▼
        Scenario uncertainty ensemble
                    │
                    ▼
       Locked prospective prediction
                    │
                    ▼
 Assignment / exposure / real outcomes
                    │
                    ▼
      Predicted-vs-actual evaluation
                    │
                    ▼
      Model scorecard / review trigger
```

## LAA production execution order

With verified real evidence, the governed sequence is:

```text
1. Verify source schemas and semantics
2. Backfill 60–90+ days idempotently
3. Run data-audit
4. Close blockers / document residual warnings
5. Freeze LAA Real Dataset Snapshot #001
6. Verify Snapshot #001 hashes
7. Run LAA Calibration Run #001
8. Review temporal holdout + uncertainty
9. Human validate / approve or reject model
10. Pre-register Experiment #001
11. Lock forecast before assignments
12. Run hash-randomized eligible cohort
13. Capture assignment + exposure evidence
14. Append real outcomes
15. Evaluate predicted vs actual
16. Update model scorecard / recalibration assessment
```

Do not bypass readiness or human approval by substituting synthetic fixtures for production evidence.

## v0.8 milestone commands

Snapshot:

```text
laa-snapshot-001-create
laa-snapshot-001-verify
```

Calibration:

```text
laa-calibration-001-run
```

Prospective experiment:

```text
laa-experiment-001-create
laa-experiment-001-lock
```

Detailed runbooks:

- [`docs/LAA_REAL_DATASET_SNAPSHOT_001.md`](docs/LAA_REAL_DATASET_SNAPSHOT_001.md)
- [`docs/LAA_CALIBRATION_RUN_001.md`](docs/LAA_CALIBRATION_RUN_001.md)
- [`docs/LAA_PROSPECTIVE_EXPERIMENT_001.md`](docs/LAA_PROSPECTIVE_EXPERIMENT_001.md)

## Core design rules

- **Library-first** — Python SDK is the source of truth; CLI/API layers are adapters.
- **Evidence first** — source observations carry provenance and deterministic dedupe keys.
- **Time-correct** — historical decisions may only see inventory/offers/features available at that time.
- **Outside options are mandatory** — competitor, land/house, rent, postpone or no purchase.
- **LLM is not the probability engine** — calibrated statistical/ML models produce core probabilities.
- **Uncertainty is explicit** — scenario results carry intervals, not fake precision.
- **Privacy by design** — PII stays outside the analytical domain; IDs are pseudonymous.
- **Human-governed models** — training creates candidates; approval is explicit and append-only.
- **Prospective validation** — predictions are locked before assignment/outcomes.
- **No autonomous sensitive actions** — v0.x is decision support, not autonomous pricing, financing, legal or customer execution.

## Repository layout

```text
src/synapse_realworld/
  adapters/          CSV / JSONL / temporal evidence adapters
  audit/             LAA evidence coverage and readiness
  behaviour/         utility, calibration, diagnostics
  connectors/        governed LAA production mapping profiles
  data/              choice sets, projections, training datasets
  datasets/          immutable dataset snapshot contracts
  domain/            canonical events, identity, temporal contracts
  experiments/       definitions, predictions, assignments, evaluation
  ingestion/         idempotent ingestion pipeline
  milestones/        LAA Snapshot / Calibration / Experiment orchestration
  persistence/       DuckDB + PostgreSQL seams
  population/        empirical population fitting / diagnostics
  registry/          immutable model artifacts + governance decisions
  simulation/        scenario engine / uncertainty / comparison
  spatial/           temporal anchors and commute evidence
  projects/laa/      LAA reference implementation
scripts/
  setup.ps1          Windows one-command development setup
  test.ps1           Windows quick/unit/milestone/full test runner
examples/data/       synthetic fixtures only
sql/postgres/        production migrations
tests/               unit + integration + governance tests
docs/                architecture, runbooks, current status
```

## CI gates

Current workflow families:

- **CI** — Ruff, full pytest, deterministic demo and Model Operations closed-loop.
- **LAA Productionization** — connector profiles, pseudonymous ingest, idempotency and readiness audit.
- **LAA Milestones** — Snapshot #001, Calibration #001 and Experiment #001 contract tests.
- **Windows Local Runbook** — executes the documented `setup.ps1` and `test.ps1 -Mode full` path on Windows.

## Roadmap

- **v0.1 — Foundation** ✅
- **v0.2 — Real Data Pipeline** ✅
- **v0.3 — Calibrated Decision Twin** ✅
- **v0.4 — Synthetic Market** ✅
- **v0.5 — Experiment Loop** ✅
- **v0.6 — Model Operations + assignment evidence** ✅
- **v0.7 — LAA Productionization + connector/readiness layer** ✅
- **v0.8 — Immutable LAA milestone orchestration** ✅
- **next — real LAA evidence normalization + Outcome Connector + Snapshot #001 execution**
- **later — market-bias correction, richer competitor world, exposure reconciliation, champion/challenger, decision dashboard**
- **v1.x — richer GIS/BIM/3D/IoT / Spatial Real-World layers**

## Production boundary

The public repository must not contain raw customer PII or private production datasets. Verified LAA evidence should be ingested through pseudonymous connectors and stored in approved private/local production storage.

Passing CI proves software contracts, not market truth. A model approval is a governance record, not proof that a model is universally valid.

## License

License policy will be finalized before external production use. Until then, treat the repository as source-available for project development and review only.
