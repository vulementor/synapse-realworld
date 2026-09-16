# LAA Prospective Experiment #001 — Commute Perception

## Status

**Experiment contract and forecast-lock workflow implemented in Synapse Real-World Platform v0.8.**

The actual production experiment has not started merely because the definition exists in code. A real forecast cannot be locked until:

1. LAA Real Dataset Snapshot #001 exists and verifies;
2. LAA Calibration Run #001 has produced a model artifact;
3. that artifact has been human-validated and human-approved;
4. the population profile, model and snapshot all share the same dataset snapshot ID.

CI uses synthetic fixtures only.

## Why Experiment #001 is not a price test

The first prospective validation should avoid changing price or payment policy.

Experiment #001 tests an information-framing hypothesis:

> For qualified LAA prospects with a known workplace zone, showing measured workplace-to-LAA travel time improves LAA choice rate versus the standard location message.

The purpose is to test whether a modeled commute/perception signal survives contact with the real market before Synapse is used to evaluate more sensitive commercial interventions.

## Fixed identity

Experiment #001 uses a deterministic reserved UUID derived from:

```text
LAA-PROSPECTIVE-EXPERIMENT-001
```

Repeated pre-registration is idempotent. A conflicting experiment cannot silently occupy this identity.

## Definition

```text
Name:
LAA Prospective Experiment #001 — Commute Perception

Metric:
laa_choice_rate

Target segment:
qualified_prospects_with_known_workplace_zone

Assignment:
hash_randomized

Control:
standard_location_message

Treatment:
measured_travel_time_framing

Default minimum trials:
100 per variant
```

Assignment receipts are required and remain pseudonymous.

## Pre-register before outcomes

```bash
synapse-realworld laa-experiment-001-create \
  --created-by <growth/data owner> \
  --experiment-registry-dir experiment_registry \
  --minimum-trials-per-variant 100
```

Optionally pre-register a planned start/end window. Do not retroactively change the experiment after outcomes are known.

## Forecast proxy boundary

The current buyer-choice model does not directly know an advertising-message causal effect.

Therefore the pre-experiment forecast uses a **perceived-commute utility proxy**:

```text
control commute multiplier   = 1.00
treatment commute multiplier = 0.85 by default
```

This means:

> “If measured travel-time framing causes buyer perception/utility to behave approximately like a 15% reduction in perceived commute burden, what treatment effect does the approved model imply?”

It does **not** mean Synapse already knows that the message itself will cause a 15% perception shift.

That causal link is exactly what the prospective experiment must validate.

## Lock prediction

After the model is approved:

```bash
synapse-realworld laa-experiment-001-lock \
  --snapshot-dir artifacts/laa_real_dataset_snapshot_001 \
  --calibration-run-dir artifacts/laa_calibration_run_001 \
  --model-registry-dir model_registry \
  --experiment-registry-dir experiment_registry \
  --as-of <timezone-aware-scenario-time> \
  --treatment-perceived-commute-multiplier 0.85 \
  --population-size 5000 \
  --replications-per-parameter 1 \
  --seed 42 \
  --output experiment_001_locked_prediction.json
```

The lock command fails when:

- the model is not `approved`;
- model snapshot ID differs from Snapshot #001;
- Calibration Run #001 differs from Snapshot #001;
- population profile differs from Snapshot #001;
- experiment has not been pre-registered;
- a different immutable prediction is already locked;
- assignments/observations arrived before the prediction.

## Assignment

Only eligible qualified prospects with a known workplace zone should enter the experiment.

Use a stable pseudonymous subject key and record the assignment:

```bash
synapse-realworld experiment-assign <EXPERIMENT_ID> \
  --subject-key <approved-pseudonymous-key> \
  --variant standard_location_message \
  --source-id <crm-or-campaign-source> \
  --source-event-key <stable-assignment-key> \
  --channel <channel> \
  --cohort <cohort> \
  --registry-dir experiment_registry
```

The existing v0.6 registry rejects the same subject being assigned to conflicting variants.

## Outcomes and evaluation

After real observations arrive, append aggregate outcome observations and evaluate using the existing experiment loop:

```bash
synapse-realworld experiment-evaluate <EXPERIMENT_ID> \
  --registry-dir experiment_registry \
  --output evaluation.json

synapse-realworld experiment-qa <EXPERIMENT_ID> \
  --registry-dir experiment_registry
```

Review:

- actual control/treatment rates;
- observed treatment effect;
- predicted p05/p50/p95 effect;
- absolute prediction error;
- direction correctness;
- predicted interval hit/miss;
- minimum sample gate;
- sample-ratio mismatch overall and by date/channel/cohort;
- declared causal eligibility.

## Exposure boundary

Assignment is not the same as exposure.

Current v0.8 experiment infrastructure has assignment receipts but does **not** yet fully reconcile every participant through:

```text
assigned -> exposed -> engaged -> qualified -> outcome
```

Therefore the first real execution should preserve campaign/CRM evidence needed to add exposure receipts and diagnose treatment contamination or non-exposure.

## No autonomous business action

Experiment #001 does not authorize Synapse to autonomously alter:

- sale price;
- discounts;
- financing;
- legal terms;
- customer eligibility;
- individual sales decisions.

The experiment is a bounded, human-governed validation of one modeled behavioral mechanism.

## Completion definition

LAA Prospective Experiment #001 is complete only after:

1. definition is pre-registered;
2. approved-model prediction is locked before assignments;
3. assignment evidence is captured;
4. minimum sample and QA gates are reviewed;
5. real outcomes are evaluated against the locked forecast;
6. result is added to the approved model's prospective scorecard;
7. model recalibration assessment is updated without automatic retraining.
