# Experiment Loop v0.5

## Purpose

v0.5 closes the first real-world validation loop for Synapse Real-World Platform.

The platform already has:

1. versioned evidence and historical decision reconstruction;
2. a calibrated buyer-choice model;
3. governed model artifacts;
4. an empirical synthetic population;
5. scenario uncertainty with bootstrap parameter vectors.

v0.5 adds the missing question:

> When Synapse predicts that a treatment will change buyer choice, what actually happened in a prospective real-world experiment?

The answer is stored as append-only evidence and becomes a measurable forecast-accuracy history for the model.

## Closed-loop architecture

```text
Approved model + empirical population
              │
              ▼
      Paired scenario comparison
      same population / same seeds
              │
              ▼
   Pre-registered ExperimentPrediction
   control · treatment · p05/p50/p95
              │
              ▼
         Prediction lock
       before observations
              │
              ▼
       Real experiment runs
 randomized / hash-randomized preferred
              │
              ▼
 Append-only ExperimentObservation
 successes · trials · source key · time
              │
              ▼
      ExperimentEvaluation
 predicted vs actual effect
              │
              ▼
    ModelExperimentScorecard
 MAE · interval coverage · direction accuracy
              │
              ▼
 human review / future recalibration logic
```

## Anti-peeking guarantees

The experiment registry is intentionally strict.

- The experiment definition is immutable after creation.
- A prediction must be locked before the first observation is accepted.
- An observation timestamp cannot predate the locked prediction timestamp.
- Once any observation exists, the locked prediction cannot be replaced.
- Observations are append-only and deduped by `(source_id, source_event_key)`.

This prevents retrospective rewriting of a forecast after outcomes are already known.

## Causal boundary

`AssignmentMethod` distinguishes the experiment design.

- `randomized`
- `hash_randomized`
- `quasi_experimental`
- `manual`
- `observational`

Only randomized and hash-randomized assignment are automatically marked as supporting causal interpretation.

For manual, observational or quasi-experimental assignment, Synapse still reports the observed association and forecast error, but adds an explicit warning that the treatment effect must not be described as causal.

This does not replace experiment-design review. Randomization quality, interference, attrition, sample-ratio mismatch, contamination and implementation fidelity still need operational controls.

## Prediction generation

Predictions are produced by a paired scenario comparison using an approved model artifact and empirical population profile.

For each retained bootstrap parameter vector:

1. generate the same synthetic population for control and treatment;
2. use the same random-choice stream;
3. run the control scenario;
4. run the treatment scenario;
5. record `treatment_laa_share - control_laa_share`.

Using common random numbers reduces Monte Carlo noise in the estimated treatment effect.

The locked prediction records:

- governed model artifact ID and status;
- population version;
- dataset snapshot ID;
- control and treatment scenario IDs;
- central control/treatment estimates;
- effect mean;
- effect p05 / p50 / p95;
- ensemble sample count;
- simulation metadata and warnings.

## Observations

Each observation is an aggregate binary-outcome batch:

```text
experiment_id
variant
metric_name
successes
trials
observed_at
source_id
source_event_key
```

A production connector can emit one record per campaign batch, sales cohort, randomized bucket or reporting interval. Re-importing the same source event is safe.

The v0.5 reference metric is `laa_choice_rate`. Other binary metrics can use the same contracts, but model-generated scenario predictions currently map to LAA choice rate.

## Evaluation

For control and treatment, Synapse aggregates successes and trials and calculates:

- observed control rate;
- observed treatment rate;
- observed treatment effect;
- approximate 95% confidence interval for the observed effect;
- absolute error versus predicted p50 effect;
- whether actual effect falls inside predicted p05–p95;
- whether predicted and observed effect directions agree;
- whether minimum planned sample was reached;
- whether causal interpretation is allowed by the assignment method.

Important: the current observed-effect confidence interval is a simple normal approximation for a difference in proportions. Production experimentation may need Wilson/Newcombe intervals, sequential-testing controls, covariate adjustment or other estimators depending on the design.

## Model experiment scorecard

`experiment-scorecard` aggregates evaluated experiments linked to a model artifact.

It reports:

- evaluated experiment count;
- randomized/causal experiment count;
- minimum-sample experiment count;
- mean absolute effect error;
- predicted interval coverage rate;
- effect-direction accuracy;
- minimum-sample rate;
- causal-experiment rate.

Warnings are emitted for small histories and weak evidence.

A scorecard with only one or two experiments is an early diagnostic, not a statistically reliable drift conclusion. v0.5 intentionally does not auto-retrain or auto-promote a replacement model.

## CLI workflow

Create the experiment before results exist:

```bash
synapse-realworld experiment-create \
  --name "LAA payment-plan experiment" \
  --hypothesis "Lower near-term payment burden increases LAA choice rate" \
  --created-by growth-lead \
  --assignment-method randomized \
  --minimum-trials-per-variant 100 \
  --registry-dir experiment_registry
```

Lock a prediction from an approved model:

```bash
synapse-realworld experiment-predict \
  <EXPERIMENT_ID> <MODEL_ARTIFACT_ID> \
  --population-profile population_profile.json \
  --units-csv units.csv \
  --offers-csv offers.csv \
  --travel-times-csv travel_times.csv \
  --as-of 2026-09-15T08:00:00+07:00 \
  --model-registry-dir model_registry \
  --experiment-registry-dir experiment_registry \
  --control-payment-multiplier 1.0 \
  --treatment-payment-multiplier 0.85 \
  --population-size 10000 \
  --output prediction.json
```

Append actual results:

```bash
synapse-realworld experiment-observe <EXPERIMENT_ID> \
  --variant control \
  --successes 22 \
  --trials 120 \
  --source-id crm-experiment-export \
  --source-event-key control-week-1 \
  --registry-dir experiment_registry

synapse-realworld experiment-observe <EXPERIMENT_ID> \
  --variant treatment \
  --successes 31 \
  --trials 120 \
  --source-id crm-experiment-export \
  --source-event-key treatment-week-1 \
  --registry-dir experiment_registry
```

Evaluate and inspect model history:

```bash
synapse-realworld experiment-evaluate <EXPERIMENT_ID> \
  --registry-dir experiment_registry \
  --output evaluation.json

synapse-realworld experiment-scorecard <MODEL_ARTIFACT_ID> \
  --registry-dir experiment_registry

synapse-realworld experiments --registry-dir experiment_registry
```

## Storage layout

The local reference registry is file-based:

```text
experiment_registry/
  <experiment_id>/
    definition.json
    prediction.json
    observations.jsonl
```

Definitions and predictions are immutable JSON documents. Observations are append-only JSONL.

Production deployments can replace this with PostgreSQL/object storage while preserving the same domain contracts.

## What v0.5 does not claim

v0.5 does not automatically prove that a model is market truth.

It also does not yet provide:

- automatic CRM/Meta randomized assignment;
- sample-ratio-mismatch detection;
- sequential-testing correction;
- CUPED/covariate adjustment;
- multi-arm bandits;
- multiple pre-registered challenger-model predictions for one experiment;
- automatic model retraining or promotion;
- fully automated campaign execution.

Those can be layered on top of the experiment contracts without changing the core anti-peeking rules.

## Production next steps

1. connect CRM/ads assignment and outcome exports to experiment observations;
2. add participant-level pseudonymous assignment receipts where available;
3. add sample-ratio-mismatch and implementation-fidelity checks;
4. support multiple pre-registered model predictions for champion/challenger validation;
5. define recalibration thresholds from a sufficient experiment history;
6. link approved predictions to actual campaign/offer IDs;
7. add monitoring for experiment and model drift;
8. keep all production actions human-governed until validation criteria are explicitly met.
