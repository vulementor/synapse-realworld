# LAA Productionization v0.7

## Objective

Phase 3 moves Synapse Real-World Platform from a production-capable engine with synthetic fixtures to a Lan Anh Avenue Decision Twin backed by real operational evidence.

The first v0.7 slice provides:

1. configurable production CSV connector contracts;
2. built-in LAA mapping profiles for CRM, qualification, SAP outcomes, inventory, offers, ads and website events;
3. pseudonymous entity keys for customer-linked exports;
4. append-only ingestion through existing `CanonicalEvent` / `SourceSnapshot` contracts;
5. a model-readiness `data-audit` command;
6. a separate productionization CI smoke test.

## Connector profiles

```bash
synapse-realworld laa-connectors
```

Built-in profiles:

- `crm_leads`
- `crm_qualification`
- `sap_outcomes`
- `inventory`
- `offers`
- `ads`
- `website`

These profiles define a canonical contract. They do **not** assume that the current CRM/SAP vendor uses these exact column names. Production onboarding should either export into these contracts or add a vendor-specific adapter that emits the same `CanonicalEvent` semantics.

## Generic production ingest

```bash
synapse-realworld laa-ingest-csv crm_leads leads.csv \
  --source-id crm-production \
  --db synapse.duckdb
```

Customer-linked profiles pseudonymize source identifiers before using them as analytical entity keys. Raw names, phone numbers and email addresses are not required by the connector contract.

Repeated imports are idempotent because source event keys and source snapshots are stable.

## Data audit

```bash
synapse-realworld data-audit \
  --db synapse.duckdb \
  --output data_audit.json
```

The audit reports:

- total events and sources;
- household count;
- structured qualification count;
- verified outcomes;
- site-tour evidence;
- trainable choice-event count;
- field coverage for purpose, affordability, commute, product interest, reasons and outside options;
- readiness for price / payment / commute / product / outside options;
- blockers and warnings;
- final `training_ready` flag.

`training_ready=true` is deliberately conservative. The current gate requires:

- structured qualification history;
- verified decision outcomes;
- temporal inventory evidence;
- temporal offer evidence;
- evidence for all five core decision dimensions;
- at least 30 choice outcomes carrying either a selected unit or a recorded outside option.

This flag means the minimum data contract is present. It is **not** a declaration that the dataset is unbiased, representative or sufficient for production deployment.

## Production source ownership

Recommended source ownership:

| Domain | Initial source | Owner |
|---|---|---|
| Leads / stages | CRM | Sales Admin + IT |
| Qualification / reasons | CRM / Sales Capture | Sales + Sales Admin |
| Booking / contract / cancel | SAP / transaction system | Sales Admin + Finance |
| Inventory | inventory / SAP export | Sales Admin |
| Offers / payment plans | price-policy system | Sales Admin + Finance |
| Ads / creatives | Meta / media exports | Marketing |
| Website events | web analytics / forms | Marketing + IT |
| Travel time | routing/GIS source | Data |

## Source verification procedure

Before importing a new production source:

1. obtain a small redacted sample export;
2. map vendor fields to the canonical profile;
3. verify timezone and effective-date semantics;
4. verify source event keys are stable across repeated exports;
5. verify customer IDs are pseudonymized before analytical persistence;
6. ingest into a disposable DuckDB;
7. run `data-audit`;
8. inspect warnings and duplicate behavior;
9. only then backfill the production period.

## Backfill target

Initial target: the latest 60–90 days with the strongest reconstructable evidence.

Priority order:

1. qualification and buyer intent;
2. inventory snapshots;
3. offers/payment policies;
4. site tours;
5. verified booking/contract/cancel/lost/postpone outcomes;
6. reasons and outside options;
7. campaign/content provenance;
8. measured commute evidence.

Never fabricate missing history. Unknown values remain unknown and must be carried with provenance/confidence.

## Phase boundary

v0.7 connector profiles are production seams, not vendor integrations that have already been verified against Linkgroup systems. A connector should only be called production-ready for a source after sample export verification and an idempotent backfill test.
