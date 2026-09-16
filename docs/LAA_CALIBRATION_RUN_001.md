# LAA Calibration Run #001

## Purpose

Calibration Run #001 is the first scientific checkpoint where Synapse is trained and evaluated against real Lan Anh Avenue evidence rather than synthetic fixtures.

This document is a runbook scaffold only. It must not be executed with fabricated production data.

## Required inputs

A frozen evidence window containing, where available:

- structured household qualification events;
- time-versioned inventory snapshots;
- time-versioned offers/payment plans;
- workplace-zone / commute evidence;
- product shortlist evidence;
- verified site tours;
- verified booking/contract/cancel/lost/postpone outcomes;
- reasons and outside options;
- source snapshots and provenance.

## Pre-run gate

Run:

```bash
synapse-realworld data-audit --db synapse.duckdb --output data_audit.json
```

Calibration Run #001 must not be promoted to a business decision model if:

- `training_ready=false`;
- temporal inventory or offer evidence is missing;
- verified outcome labels are unavailable;
- future-leakage checks fail;
- outside-option evidence is absent for most lost/postponed records;
- dataset provenance cannot be reconstructed.

## Snapshot naming

Recommended immutable dataset label:

```text
LAA_REAL_<START_YYYYMMDD>_<END_YYYYMMDD>_<CONTENT_HASH>
```

Record:

- extraction timestamp;
- included source IDs;
- source snapshot hashes;
- code commit SHA;
- schema/profile versions;
- excluded records and reasons.

## Temporal split

Do not randomly split the historical events.

Preferred first run:

```text
TRAIN  = earliest ~80% of the decision timeline
HOLDOUT = latest ~20%
```

If a clean monthly boundary exists, prefer an explicit calendar split.

Example only:

```text
Train:   2026-06-01 -> 2026-08-31
Holdout: 2026-09-01 -> 2026-09-30
```

The actual dates must be chosen from the available production evidence.

## Calibration command

After source verification and audit:

```bash
synapse-realworld calibrate \
  --units-csv <verified-temporal-units.csv> \
  --offers-csv <verified-temporal-offers.csv> \
  --travel-times-csv <verified-travel-times.csv> \
  --project-anchor-id LAA \
  --db synapse.duckdb \
  --registry-dir model_registry \
  --model-name laa-buyer-choice \
  --model-version real-run-001 \
  --code-commit-sha <git-sha> \
  --holdout-fraction 0.2 \
  --bootstrap-samples 100 \
  --output calibration_run_001.json
```

Training registers a `candidate`, never an approved model.

## Evaluation checklist

Review at minimum:

- temporal holdout log loss;
- calibration / probability reliability;
- comparison with uniform/simple baselines;
- coefficient directions and plausible magnitudes;
- segment stability;
- choice ranking / selected alternative behavior;
- price sensitivity;
- payment-plan sensitivity;
- commute sensitivity;
- outside-option migration;
- bootstrap uncertainty;
- data-quality warnings.

## Decision gate

A human data reviewer may move the artifact to `validated` only after verifying:

1. dataset audit and provenance;
2. no material future leakage;
3. holdout performance is better than the agreed naive baseline;
4. model behavior remains economically defensible;
5. sparse segments and uncertainty are clearly disclosed.

A separate business owner may move a validated artifact to `approved` for a bounded decision-support use case.

Approval is not proof of market truth and does not authorize autonomous pricing, financing, legal, or individual-customer actions.

## First prospective test

After an approved Run #001 model exists, prefer a lower-risk information-framing experiment before testing sensitive price changes.

Recommended first candidate:

```text
Commute Perception Experiment
```

Control: standard location message.

Treatment: measured travel-time framing for eligible workplace segments.

The model prediction must be prospectively locked before assignment/exposure evidence arrives.

## Deliverables

Calibration Run #001 should produce:

- immutable data-audit JSON;
- dataset/source manifest;
- candidate model artifact;
- holdout diagnostics;
- bootstrap parameter vectors;
- population profile diagnostics;
- reviewer decision record;
- approved/rejected status with reason;
- proposed first prospective experiment if approved.
