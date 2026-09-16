# Current Status — Synapse Real-World Platform v0.7

This document is the source of truth for the current implementation state while older milestone documents remain preserved as historical runbooks.

## Completed

- v0.1 Foundation
- v0.2 Real Data Pipeline
- v0.3 Calibrated Decision Twin
- v0.4 Synthetic Market
- v0.5 Prospective Experiment Loop
- v0.6 Model Operations first slices:
  - experiment QA and SRM checks;
  - governed recalibration assessment;
  - pseudonymous assignment receipts;
  - bucketed allocation QA by date/channel/cohort.

## Current release line

`0.7.0` — LAA Productionization.

Current implementation in this release line adds:

- configurable production CSV connector contracts;
- Lan Anh Avenue connector profiles for CRM leads, CRM qualification, SAP outcomes, inventory, offers, ads and website events;
- upstream pseudonymization of customer-linked analytical entity keys;
- idempotent append-only ingest into the existing canonical event store;
- LAA `data-audit` model-readiness checks;
- productionization-specific CI;
- a real-data backfill and Calibration Run #001 runbook scaffold.

## Historical-document note

Older files may describe features as "not yet implemented" because they are milestone records. In particular, assignment receipts were subsequently implemented in the v0.6 assignment-evidence slice. Use this file plus package version and current `main` code when determining current capability.

## Not yet production-verified

The built-in connector profiles are canonical export contracts. They have not yet been verified against the exact Linkgroup CRM/SAP/Ads vendor schemas or real Lan Anh Avenue exports.

Therefore the next operational milestone is **source verification + real 60–90 day backfill**, not additional synthetic modeling.

## Next gates

1. obtain redacted real source samples;
2. verify/export-map each production source;
3. run idempotent disposable-store ingests;
4. run `data-audit` and close P0 blockers;
5. freeze the first real dataset snapshot;
6. execute LAA Calibration Run #001;
7. review holdout diagnostics;
8. only after approval, run the first prospectively locked LAA experiment.
