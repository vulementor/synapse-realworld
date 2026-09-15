# Synapse Real-World Platform — Real Data Pipeline v0.2

This document describes the first production-oriented path from Lan Anh Avenue exports to a calibrated historical choice model.

## Invariants

1. **Append-only evidence** — source events are never silently rewritten.
2. **Idempotent backfill** — the same source record can be imported repeatedly without duplication.
3. **Source snapshots** — imported files/exports are fingerprinted with SHA-256 and record count.
4. **Pseudonymous analytics IDs** — phone/email/identity documents do not belong in the analytical event store.
5. **Time-correct choices** — inventory and offers are reconstructed at the exact historical decision timestamp.
6. **Outside options are mandatory** — competitor, land/house, rent, postpone and no-purchase remain valid choices.
7. **Future leakage is blocked** — features observed after a decision are not available to that historical example.
8. **Temporal holdout** — validation uses the latest decisions, not a random split that mixes future and past.

## Local end-to-end flow

```bash
pip install -e ".[dev]"

DB=./synapse.duckdb
synapse-realworld init-store --db "$DB"

synapse-realworld ingest-sales examples/data/laa_sales_capture_sample.csv --db "$DB"
synapse-realworld ingest-outcomes examples/data/laa_outcomes_sample.csv --db "$DB"
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

The sample files contain synthetic data only. They exist to prove the pipeline contract and CI path.

## Data flow

```text
CRM / Sales Capture / SAP / Inventory / Offer exports / Agent connectors
                         │
                         ▼
                   Source Adapter
                         │
                         ▼
                  CanonicalEvent
             source key · timestamp · hash
                         │
                         ▼
               EventStore + SnapshotStore
               DuckDB local / Postgres prod
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
 FeatureObservation            Outcome events
            │                         │
            │                TemporalChoiceSetBuilder
            │                         │
            └────────────┬────────────┘
                         ▼
                    ChoiceEvent
                         │
                         ▼
                DecisionDatasetBuilder
                (future leakage blocked)
                         │
                         ▼
              Household snapshot builder
                         │
                         ▼
              MultinomialLogitCalibrator
                         │
                         ▼
              Temporal holdout metrics
```

## Canonical event boundary

External systems should emit or map into:

- `event_type`
- `entity_type`
- `entity_id` (pseudonymous source key)
- `occurred_at`
- `source_id`
- `source_event_key` (stable source-record identifier)
- `payload`
- `schema_version`

`dedupe_key` and `payload_hash` are deterministic SHA-256 values derived inside Synapse.

For custom connectors, canonical JSONL is the simplest integration seam:

```bash
synapse-realworld ingest-jsonl events.jsonl \
  --source-id crm-production \
  --db synapse.duckdb
```

## Sales Capture v0.2

The current adapter recognizes the operational fields designed in the LAA collection spec:

- purchase purpose
- household / children band
- income, liquid-capital and monthly-payment bands
- purchase horizon
- workplace zone and commute tolerance
- preferred product / shortlisted unit
- reason 1–2 with motivator/objection direction
- competitor/outside option
- decision stage / next action

The adapter creates structured qualification, stage and reason events. It does not copy raw PII into the event store.

## Inventory and offers

`UnitVersion` and `Offer` are effective-dated. Calibration fails when a selected historical unit is not in the reconstructed choice set at the outcome timestamp.

This is intentional: a model must not use today's inventory or today's policy to explain yesterday's buyer choice.

## Outcomes

The v0.2 outcome adapter accepts verified decision labels such as:

- site tour / revisit / hold
- booking / deposit / contract
- cancel / lost / postponed
- competitor / land-house / continue-renting / no-purchase

For calibration, verified outcomes are assembled into `ChoiceEvent` objects against the historical choice set.

## Calibration

The first trainable behavior model is a transparent multinomial-logit baseline. It learns weights for:

- effective price
- monthly payment burden
- commute
- product match
- affordability breach
- investor × shophouse interaction
- own-stay × garden-product interaction
- outside-option baseline

This is still a baseline, not a production approval engine. The purpose is to establish a reproducible benchmark before mixed logit, hierarchical Bayes, gradient boosting, causal experiments or richer agent simulation.

## Persistence

### Local

`DuckDBStore` is the default local/backfill engine.

### Production

`PostgresStore` implements the same event/snapshot interfaces and can be installed with:

```bash
pip install -e ".[postgres]"
```

The matching SQL migration is in `sql/postgres/001_event_store.sql`.

## Next engineering slice

1. source-specific CRM/SAP/Meta Ads connectors;
2. identity bridge / restricted PII vault integration;
3. normalized temporal materialization jobs from canonical events;
4. commute/GIS feature provider;
5. calibration report with confidence intervals and segment diagnostics;
6. model registry + approved model artifacts;
7. backfill of real LAA 60–90 day history;
8. 5k–10k calibrated synthetic households and scenario stress tests.
