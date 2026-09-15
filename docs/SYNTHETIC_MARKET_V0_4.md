# Synapse Real-World Platform — Synthetic Market v0.4

v0.4 turns the calibrated Decision Twin into the first empirical **Synthetic Market**.

The two major changes are:

1. synthetic households are fitted from time-correct qualification evidence instead of hard-coded demo distributions;
2. scenario outputs include uncertainty ranges across bootstrap model fits instead of presenting one simulated share as certain.

## End-to-end flow

```text
CRM / Sales qualification events
              │
              ▼
     Time-correct household snapshots
              │
              ▼
      EmpiricalPopulationProfile
        (no historical IDs)
              │
              ├── joint feature prototypes
              ├── deterministic content hash
              ├── source/synthetic diagnostics
              └── synthetic UUID generation
              │
              ▼
       5k–10k synthetic households
              │
              ├────────────────────────────┐
              │                            │
              ▼                            ▼
     Approved ModelArtifact        Temporal market state
  central weights + bootstrap      units · offers · commute
       parameter vectors                    │
              │                            │
              └──────────────┬─────────────┘
                             ▼
                   Scenario ensemble
              price · payment · commute · product
                             │
                             ▼
                 point estimate + uncertainty
               p05 · p50 · p95 · min · max
```

## Empirical population fitting

`fit-population` reads structured qualification observations from the canonical event store.

It does **not** require a household to have booked, purchased, or even reached a final outcome. This avoids fitting the population only on buyers or lost deals.

For every household, the fitter reconstructs the latest feature value observed at or before the optional `as_of` cutoff. It then builds a structured `Household` snapshot.

Typical fields include:

- purchase purpose;
- household size / children band;
- income band midpoint;
- liquid-capital band midpoint;
- maximum monthly payment;
- purchase horizon;
- workplace zone;
- commute tolerance;
- preferred product type;
- structured-profile confidence.

A minimum profile-confidence threshold excludes records that do not contain enough structured evidence.

## No historical identifiers in the population profile

Historical analytics `household_id` values are used only to deduplicate source households before fitting.

The persisted population profile contains **feature prototypes only**. It contains no historical analytics household identifier.

When Synapse generates a synthetic household, it creates a deterministic synthetic UUID from:

- population version;
- simulation seed;
- synthetic row index.

This keeps reproducibility without reusing source identities.

## Joint bootstrap rather than independent marginals

v0.4 resamples complete household feature prototypes.

This preserves observed joint relationships such as:

```text
purchase purpose
      ↕
liquid capital
      ↕
monthly payment tolerance
      ↕
workplace
      ↕
product preference
```

Sampling every attribute independently would destroy these relationships and can create unrealistic households that never existed in the observed market.

Future versions can add IPF/raking or probabilistic population synthesis when reliable external marginal constraints are available.

## Stable population identity

`population_version` is derived from a canonical feature-only content hash.

Changing or reordering historical household IDs does not change the profile hash if the feature multiset is unchanged.

This is important for reproducibility and privacy: the population artifact is identified by the behavioral distribution it represents, not the identity keys used to assemble it.

## Population diagnostics

The fitter generates a validation population and compares it to source prototypes.

Categorical checks currently include:

- purchase purpose;
- household-size band;
- children band;
- workplace zone;
- preferred product type.

For each categorical feature Synapse reports total variation distance (TVD).

Numeric checks compare source vs synthetic mean for:

- income;
- liquid capital;
- maximum monthly payment;
- purchase horizon;
- commute tolerance.

Warnings are emitted for:

- fewer than 100 source households;
- fewer than 30 source households (exploratory only);
- categorical TV distance greater than 0.10.

These are diagnostics, not claims that the source CRM is representative of the entire regional market.

## Bootstrap parameter ensemble

v0.3 already estimated coefficient intervals. v0.4 additionally retains the **full parameter vector from each bootstrap fit**.

That matters because model coefficients are correlated. Sampling each coefficient independently from its interval would discard that covariance structure.

A v0.4 model artifact therefore contains:

```text
central parameter vector
bootstrap vector 001
bootstrap vector 002
...
bootstrap vector N
```

The uncertainty simulator runs the requested scenario through those parameter vectors.

## Common random numbers

For a given Monte Carlo replication, every bootstrap parameter vector uses the same:

- synthetic population seed;
- household sample;
- random-choice stream.

This common-random-number design reduces simulation noise when comparing parameter vectors. Variation in the resulting scenario distribution therefore reflects model uncertainty more cleanly.

## Scenario uncertainty output

For LAA share, outside-option share and every alternative, Synapse reports:

- mean;
- p05;
- p50;
- p95;
- minimum;
- maximum;
- number of ensemble runs.

It also reports LAA share uncertainty by available purchase-purpose segment.

The central fitted model is still run separately and exposed as `point_estimate`.

## Governance boundary

By default `simulate-uncertainty` refuses to run from a model that is not `approved` in the model registry.

Exploratory use can explicitly pass `--allow-unapproved`, and the resulting output is marked with an unapproved-model warning.

Approval still means only that a human governance decision was recorded for a bounded decision-support scope. It is not proof of market truth.

## CLI

Fit a population from the event store:

```bash
synapse-realworld fit-population \
  --db synapse.duckdb \
  --profile-name laa-market-2026-09 \
  --minimum-profile-confidence 0.5 \
  --diagnostic-population-size 5000 \
  --output population_profile.json
```

Calibrate a model with enough bootstrap samples to support scenario uncertainty:

```bash
synapse-realworld calibrate \
  --units-csv unit_versions.csv \
  --offers-csv offers.csv \
  --travel-times-csv travel_times.csv \
  --project-anchor-id LAA \
  --db synapse.duckdb \
  --registry-dir model_registry \
  --model-version v0.4 \
  --code-commit-sha "$(git rev-parse HEAD)" \
  --bootstrap-samples 100 \
  --output calibration.json
```

After human validation and approval, run a scenario ensemble:

```bash
synapse-realworld simulate-uncertainty <ARTIFACT_UUID> \
  --population-profile population_profile.json \
  --units-csv unit_versions.csv \
  --offers-csv offers.csv \
  --travel-times-csv travel_times.csv \
  --project-anchor-id LAA \
  --as-of 2026-09-15T08:00:00+07:00 \
  --registry-dir model_registry \
  --scenario-id price-plus-5 \
  --price-change 0.05 \
  --population-size 10000 \
  --output scenario_price_plus_5.json
```

## What v0.4 does not claim

v0.4 does not claim that CRM leads are automatically representative of the total addressable market.

It does not yet correct for:

- campaign acquisition bias;
- missing offline buyers;
- channel-specific lead quality;
- regional demographic marginal constraints;
- competitor exposure bias;
- survey/nonresponse bias;
- macroeconomic regime shifts.

The empirical population should therefore be described as a synthetic market calibrated to the **observed evidence base**, with explicit warnings when that evidence is sparse.

## Next engineering slice

1. real LAA source mappings and 60–90 day backfill;
2. external demographic/workforce marginal constraints and raking/IPF;
3. acquisition-bias weighting by channel/campaign;
4. competitor inventory/offer alternatives in the same temporal choice set;
5. champion/challenger models and model-selection criteria;
6. scenario comparison and elasticity curves;
7. prediction registry linked to real-world A/B experiments;
8. automated recalibration triggers after meaningful data drift.
