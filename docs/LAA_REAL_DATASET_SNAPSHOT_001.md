# LAA Real Dataset Snapshot #001

## Status

**Workflow implemented in Synapse Real-World Platform v0.8.**

This document does **not** claim that the real production Snapshot #001 has already been created. The actual artifact must be created from verified Linkgroup/Lan Anh Avenue production evidence after source mapping and data-audit blockers are closed.

CI uses synthetic fixtures only to validate the workflow contract.

## Purpose

Snapshot #001 is the immutable evidence boundary for the first real Lan Anh Avenue calibration.

It answers:

> Exactly which customer, inventory, offer and mobility evidence did Calibration Run #001 use?

A calibration run must never silently read newer inventory, prices or customer events after this snapshot is frozen.

## Artifact layout

The snapshot is a self-contained directory:

```text
laa_real_dataset_snapshot_001/
  manifest.json
  events.jsonl
  source_snapshots.json
  evidence/
    unit_versions__<source-file>.csv
    offers__<source-file>.csv
    travel_times__<source-file>.csv   # when supplied
```

`manifest.json` records:

- dataset snapshot ID;
- snapshot version;
- evidence window;
- event count;
- semantic event SHA-256;
- semantic source-snapshot SHA-256;
- frozen input file fingerprints;
- event/source distributions;
- full LAA data-readiness audit;
- `training_ready`;
- blockers and warnings.

## Semantic identity

Dataset identity intentionally excludes random ingestion UUIDs and ingestion timestamps.

The event semantic hash uses:

```text
event_type
entity_type
entity_id
occurred_at
source_id
source_event_key
payload
schema_version
```

Therefore the same upstream evidence re-ingested into a new local database can resolve to the same semantic dataset identity.

Any material change to source record content, timestamp, source key, schema or frozen unit/offer/travel file changes the snapshot identity.

## Create Snapshot #001

First ingest the verified production exports through the v0.7 connector layer and inspect readiness:

```bash
synapse-realworld data-audit \
  --db synapse.duckdb \
  --output data_audit.json
```

Then freeze the chosen evidence window:

```bash
synapse-realworld laa-snapshot-001-create \
  --db synapse.duckdb \
  --units-csv <verified-temporal-unit-versions.csv> \
  --offers-csv <verified-temporal-offers.csv> \
  --travel-times-csv <verified-temporal-travel-times.csv> \
  --window-from <timezone-aware-start> \
  --window-to <timezone-aware-exclusive-end> \
  --output-dir artifacts/laa_real_dataset_snapshot_001
```

Dates must be chosen from actual production evidence. Do not reuse example dates merely because they appear in documentation.

## Verify Snapshot #001

Before every downstream run:

```bash
synapse-realworld laa-snapshot-001-verify \
  artifacts/laa_real_dataset_snapshot_001
```

Verification checks:

1. physical file SHA-256 hashes;
2. semantic event hash;
3. semantic source-snapshot hash;
4. frozen evidence-file hashes;
5. recomputed dataset snapshot identity.

Any mismatch fails closed.

## Immutability

Snapshot creation refuses a non-empty output directory.

To create a later evidence snapshot, use a new directory/version. Do not mutate Snapshot #001 after it has been referenced by a model artifact or experiment.

## Training-readiness boundary

Snapshot creation is allowed even when evidence is incomplete so the state can be inspected and archived.

However, the manifest contains the conservative `data-audit` gate. Calibration Run #001 refuses to execute if `training_ready=false`.

Current readiness dimensions include:

- price;
- payment/cash-flow evidence;
- commute/workplace evidence;
- product/inventory evidence;
- outside options;
- verified decision outcomes;
- temporal offers and inventory;
- minimum trainable choice history.

## Privacy

Snapshot analytical events should contain pseudonymous IDs, not raw phone numbers, email addresses or national-ID data.

PII remains outside the analytical domain. If an upstream export contains raw customer identifiers, the connector/pseudonymization layer must transform them before snapshot creation.

## Production gate

The real `LAA Real Dataset Snapshot #001` may be declared created only when:

1. real source samples have been verified against connector profiles;
2. timezone/effective-date semantics are documented;
3. backfill is idempotent;
4. source provenance is present;
5. PII treatment is approved;
6. evidence window is explicitly frozen;
7. snapshot verification succeeds.

Until then, CI artifacts are test fixtures and must never be presented as real LAA evidence.
