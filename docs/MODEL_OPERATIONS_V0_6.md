# Model Operations v0.6

## Purpose

v0.6 begins the Model Operations layer for Synapse Real-World Platform.

v0.5 created a prospective validation loop:

```text
model forecast -> locked experiment prediction -> real observations -> evaluation -> scorecard
```

v0.6 adds two operational questions before any model is considered for recalibration:

1. Was the experiment itself healthy enough to trust?
2. Is there enough prospective evidence to recommend a human recalibration review?

The first v0.6 slice intentionally does **not** retrain, replace, or promote models automatically.

## Experiment quality assessment

`assess_experiment_quality()` evaluates basic experiment-operability signals from the immutable experiment definition plus append-only observations.

Current checks:

- control and treatment sample totals;
- minimum planned sample per variant;
- declared assignment method;
- expected vs observed treatment allocation share;
- sample-ratio mismatch (SRM) z-score;
- explicit warnings for non-randomized assignment.

### Sample-ratio mismatch

For a two-arm experiment with expected treatment share `p`, total trials `N`, and observed treatment count `T`, v0.6 computes:

```text
z = (T - N*p) / sqrt(N*p*(1-p))
```

The default warning threshold is `|z| >= 3.29`, roughly corresponding to a two-sided 0.1% normal-tail threshold.

This is a pragmatic smoke check, not proof that randomization worked correctly.

A clean SRM check does not rule out:

- exposure logging bugs;
- treatment contamination;
- attrition after assignment;
- bot/duplicate traffic;
- interference between subjects;
- incorrect eligibility filters;
- bucketing bugs that preserve the aggregate ratio;
- repeated/sequential peeking.

Conversely, SRM may indicate implementation or logging problems and should block casual causal interpretation until investigated.

## CLI: experiment QA

```bash
synapse-realworld experiment-qa <EXPERIMENT_ID> \
  --registry-dir experiment_registry \
  --expected-treatment-share 0.5 \
  --sample-ratio-z-threshold 3.29
```

Example output fields:

```text
control
  successes / trials / rate

treatment
  successes / trials / rate

total_trials
expected_treatment_share
observed_treatment_share
sample_ratio_zscore
sample_ratio_mismatch
minimum_sample_reached
causal_design_declared
warnings
```

`causal_design_declared=true` only means the experiment definition uses `randomized` or `hash_randomized`. It is not a substitute for implementation-fidelity review.

## Governed recalibration assessment

A model experiment scorecard aggregates forecast quality across prospective experiments. v0.6 adds `assess_recalibration_need()` to turn that history into a governed review state.

States:

- `insufficient_evidence`
- `monitor`
- `review_recalibration`

### Default policy

```text
minimum_evaluated_experiments = 5
minimum_causal_experiments = 3
maximum_mean_absolute_effect_error = 0.05
minimum_interval_coverage_rate = 0.80
minimum_direction_accuracy = 0.70
```

These are initial operational defaults, not universal statistical truth. Production owners should version and approve thresholds appropriate to the decision risk, metric, sample sizes and experiment cadence.

### State logic

If the model has too few evaluated or randomized experiments:

```text
state = insufficient_evidence
```

This takes precedence even if the few existing experiments look excellent. Synapse must not infer model health from an undersized validation history.

Once the evidence floor is met, the model is flagged for review if one or more forecast-quality thresholds fail:

```text
MAE too high
OR prediction interval coverage too low
OR effect-direction accuracy too low
    -> review_recalibration
```

Otherwise:

```text
state = monitor
```

Every state still has:

```text
human_review_required = true
automatic_retraining_allowed = false
```

This is deliberate. A warning can trigger investigation or a controlled recalibration workflow, but must not silently replace a production model.

## CLI: recalibration assessment

```bash
synapse-realworld model-recalibration-assess <MODEL_ARTIFACT_ID> \
  --registry-dir experiment_registry \
  --minimum-evaluated-experiments 5 \
  --minimum-causal-experiments 3 \
  --maximum-mean-absolute-effect-error 0.05 \
  --minimum-interval-coverage-rate 0.80 \
  --minimum-direction-accuracy 0.70
```

The command rebuilds evaluations from immutable definitions, locked predictions and append-only observations, then builds the model experiment scorecard and applies the policy.

Experiments that do not yet have enough observations for evaluation are returned as pending rather than silently counted.

## End-to-end CI guarantee

The v0.6 Actions smoke path executes:

```text
ingest real-data fixtures
-> fit empirical population
-> calibrate bootstrap model
-> validate model
-> approve model
-> uncertainty simulation
-> create randomized experiment
-> lock paired prediction
-> append balanced control/treatment outcomes
-> evaluate prediction vs actual
-> build model scorecard
-> experiment QA
-> recalibration assessment
```

CI asserts:

- approved model is used;
- uncertainty quantiles remain ordered;
- prospective experiment remains causal-eligible by declared design;
- experiment reaches minimum sample;
- balanced 100/100 allocation does not trigger SRM;
- one experiment produces `insufficient_evidence`, not a false model-health conclusion;
- `automatic_retraining_allowed` remains false.

## What v0.6 first slice does not do

Not yet implemented:

- participant-level assignment receipts;
- exact binomial SRM p-values or multi-arm SRM tests;
- exposure/eligibility reconciliation;
- sample-ratio checks by segment/time bucket;
- contamination and interference detection;
- sequential-testing alpha spending;
- multiple challenger predictions locked against one experiment;
- automatic drift declaration;
- automatic recalibration job creation;
- automatic model retraining;
- automatic model promotion.

## Recommended next slice

The next Model Operations slice should add:

1. participant/cohort assignment receipts from CRM/ads systems;
2. experiment-fidelity checks by date, segment and channel;
3. multiple pre-registered model predictions per experiment;
4. champion/challenger scorecard comparison;
5. versioned Model Ops policy artifacts;
6. governed recalibration work items that require human approval;
7. richer statistical estimators where the experiment design requires them.

The architectural rule remains: **measure first, recommend second, automate only after explicit governance and sufficient evidence.**
