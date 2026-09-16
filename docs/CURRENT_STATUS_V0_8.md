# Synapse Real-World Platform — Current Status v0.8

## Source of truth

This document is the current implementation-status reference for **Synapse Real-World Platform v0.8**.

Older milestone documents remain useful historical design/runbook records, but where wording conflicts with this file, this file reflects the newer code state.

## What is implemented

### v0.1–v0.7 foundation

Implemented and merged before v0.8:

- canonical real-world domain contracts;
- append-only event/source-snapshot evidence;
- DuckDB local store and PostgreSQL production seam;
- temporal inventory/offer reconstruction;
- leakage-safe decision datasets;
- multinomial-logit buyer-choice calibration;
- bootstrap parameter uncertainty;
- human-governed model registry;
- empirical ID-free synthetic population fitting;
- scenario uncertainty p05/p50/p95;
- prospective experiment definitions and locked predictions;
- predicted-vs-actual evaluation and model scorecards;
- experiment QA and governed recalibration assessment;
- pseudonymous assignment receipts and date/channel/cohort allocation QA;
- LAA production connector profiles;
- LAA `data-audit` / model-readiness gate.

### v0.8 milestone orchestration

Implemented on the v0.8 release line:

#### LAA Real Dataset Snapshot #001 workflow

- self-contained immutable snapshot directory;
- canonical `events.jsonl` freeze;
- source-snapshot metadata freeze;
- frozen unit/offer/travel evidence copies;
- semantic event hash independent of random ingest UUIDs;
- semantic source hash independent of local snapshot UUID/capture time;
- dataset snapshot SHA-256 identity;
- embedded data-readiness audit;
- physical and semantic tamper verification;
- immutable-output guard.

CLI:

```text
laa-snapshot-001-create
laa-snapshot-001-verify
```

#### LAA Calibration Run #001 workflow

- requires verified Snapshot #001;
- fails closed if `training_ready=false`;
- fits empirical population from snapshot events;
- freezes population artifact with dataset snapshot ID;
- reconstructs historical choices with temporal units/offers;
- optionally uses temporal commute evidence;
- chronological train/holdout split;
- bootstrap diagnostics;
- governed minimum historical-choice gate;
- immutable calibration-run output;
- registers model as `candidate`, never approved automatically;
- deterministic run identity from dataset/code/policy parameters.

CLI:

```text
laa-calibration-001-run
```

#### LAA Prospective Experiment #001 workflow

- deterministic/idempotent reserved experiment identity;
- commute-perception information-framing experiment;
- `hash_randomized` assignment design;
- no price or payment-policy change in Experiment #001;
- target: qualified prospects with known workplace zone;
- requires assignment receipts;
- requires pre-registration before forecast/outcomes;
- forecast lock requires a human-approved model;
- calibration/model/population snapshot IDs must match Snapshot #001;
- treatment forecast uses an explicit perceived-commute utility proxy;
- proxy is documented as a hypothesis input, not a proven advertising-message effect.

CLI:

```text
laa-experiment-001-create
laa-experiment-001-lock
```

## CI guarantees

Three workflow families protect the current codebase:

### Core CI

Checks:

- Ruff;
- full pytest suite;
- deterministic demo simulation;
- Model Operations closed-loop smoke test.

### LAA Productionization

Checks:

- connector profiles;
- pseudonymous CRM-style ingestion;
- idempotency;
- data audit/readiness workflow.

### LAA Milestones

Uses **synthetic fixtures only** to check:

- Snapshot #001 semantic identity and tamper detection;
- snapshot/run immutability;
- Calibration #001 fail-closed readiness gate;
- Calibration #001 synthetic contract happy path;
- candidate-model governance;
- approved-model requirement for Experiment #001;
- Experiment #001 definition and forecast lock;
- milestone CLI surface.

Passing CI proves implementation contracts, not real LAA market validity.

## What has NOT happened yet

As of this v0.8 code status, unless separate real production artifacts have subsequently been supplied and executed:

- a real Linkgroup/LAA production `LAA Real Dataset Snapshot #001` has not been declared created;
- real Calibration Run #001 has not been declared scientifically complete;
- no real Run #001 model has been declared approved merely because CI passes;
- LAA Prospective Experiment #001 has not been declared launched;
- no real-world treatment outcome has been evaluated against its locked forecast;
- the current empirical population has not automatically been corrected for total-market acquisition bias;
- participant exposure receipts are not yet fully reconciled with assignment/outcome evidence;
- competitor alternatives remain less detailed than a full temporal competitor world;
- no autonomous pricing, financing, legal or individual-customer action is authorized.

## Real production gate

The next non-code dependency is **verified real LAA evidence**.

Minimum source families:

```text
CRM leads / contacts / stages
structured qualification or sales evidence
historical inventory versions
historical price / offer / payment-plan versions
verified booking / contract / cancel / lost / postpone outcomes
site-tour evidence when available
workplace / commute evidence when available
campaign / creative / assignment evidence for Experiment #001
```

Raw PII is not required for the analytical platform. Customer-linked exports should be pseudonymized before becoming analytical entity IDs.

## Execution order with real evidence

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
13. Capture assignment + campaign/exposure evidence
14. Append real outcomes
15. Evaluate predicted vs actual
16. Update model scorecard / recalibration assessment
```

## Architectural rule

The governing rule remains:

> **Evidence first, immutable snapshot second, calibration third, prospective experiment fourth. Never manufacture a successful milestone from synthetic production claims.**
