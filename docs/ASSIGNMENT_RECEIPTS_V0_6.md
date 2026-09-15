# Assignment Receipts v0.6

## Purpose

The first Model Operations slice could detect sample-ratio mismatch from aggregate control/treatment outcome counts. That is useful when no assignment evidence exists, but outcomes are downstream of assignment and may already contain attrition or logging bias.

This slice adds append-only, pseudonymous **assignment receipts** so experiment QA can inspect the allocation process itself.

## Receipt contract

Each assignment receipt contains:

```text
experiment_id
subject_key          # pseudonymous; never raw PII
variant
assigned_at
source_id
source_event_key
channel              # optional
cohort               # optional
metadata             # optional
```

`subject_key` should be generated upstream from an approved pseudonymization scheme. The registry does not need names, phone numbers, email addresses or raw CRM identifiers.

## Ordering and immutability

The registry requires:

1. experiment definition exists;
2. model prediction is locked;
3. assignment timestamp is not earlier than prediction lock;
4. variant belongs to the experiment;
5. assignment is inside the planned experiment window when one exists.

Assignments are append-only and idempotent by `(source_id, source_event_key)`.

A subject already assigned to one variant cannot later be assigned to the other variant in the same experiment. Re-importing the same subject into the same variant is treated as a duplicate rather than additional allocation weight.

This prevents duplicated assignment exports from inflating SRM counts.

## QA source precedence

`experiment-qa` now uses this order:

```text
assignment receipts available
    -> use unique assignment receipts for allocation/SRM

no assignment receipts
    -> fall back to outcome trial counts
```

Outcome sample sufficiency still uses observed outcome trials because the experiment's `minimum_trials_per_variant` is an evaluation requirement, not an assignment-volume requirement.

The QA output includes `allocation_source` so downstream consumers know which evidence generated the allocation check.

## Bucketed allocation checks

When assignment receipts exist, QA calculates allocation checks for:

- assignment date;
- channel;
- cohort.

For each bucket it reports:

```text
control_assignments
treatment_assignments
total_assignments
observed_treatment_share
sample_ratio_zscore
sample_ratio_mismatch
```

This catches cases where the aggregate ratio looks healthy but implementation is badly imbalanced inside a channel or cohort.

Example:

```text
Meta: 50 control / 0 treatment
Zalo: 0 control / 50 treatment
Overall: 50 control / 50 treatment
```

The aggregate 50/50 ratio has no SRM, but both channel buckets are severely imbalanced. v0.6 surfaces both warnings.

## CLI

Append a receipt after prediction lock:

```bash
synapse-realworld experiment-assign <EXPERIMENT_ID> \
  --subject-key hash:crm-subject-001 \
  --variant control \
  --source-id crm-assignment-export \
  --source-event-key assignment-000001 \
  --channel meta \
  --cohort week-1 \
  --registry-dir experiment_registry
```

List assignment evidence:

```bash
synapse-realworld experiment-assignments <EXPERIMENT_ID> \
  --registry-dir experiment_registry
```

Run QA:

```bash
synapse-realworld experiment-qa <EXPERIMENT_ID> \
  --registry-dir experiment_registry
```

When receipts exist, the output should show:

```text
allocation_source = assignment_receipts
```

## CI guarantee

The Model Operations E2E smoke test now proves this order:

```text
create experiment
-> lock prediction
-> append pseudonymous assignments
-> append observed outcomes
-> evaluate
-> QA from assignment receipts
-> recalibration assessment
```

CI asserts a balanced assignment set remains SRM-clean and that the QA source is `assignment_receipts` rather than downstream outcome counts.

## Boundaries

Assignment receipts improve implementation evidence but still do not prove a flawless randomized experiment.

This slice does not yet reconcile every observed outcome back to a specific assigned subject. It also does not detect exposure contamination, cross-device identity collisions, missing assignment receipts, or sample-ratio drift at arbitrary rolling-window granularity.

Those require stronger participant/exposure reconciliation in later Model Operations work.
