# LAA Calibration Run #001

## Status

**Workflow implemented in Synapse Real-World Platform v0.8.**

The real production Run #001 has **not** been declared complete merely because the code path exists. It can run only from a verified, training-ready **LAA Real Dataset Snapshot #001** built from real production evidence.

CI uses synthetic fixtures solely to verify the contract.

## Purpose

Calibration Run #001 is the first scientific checkpoint where the buyer-choice model is trained and temporally validated against a frozen Lan Anh Avenue evidence snapshot.

It must answer:

1. Can the model reconstruct buyer choice from time-correct inventory/offers and observed buyer evidence?
2. Does it outperform the agreed naive baseline on future holdout decisions?
3. Are price, payment, commute and product responses economically defensible?
4. Is uncertainty sufficiently disclosed for bounded decision support?

## Hard input boundary

Run #001 reads only from the verified Snapshot #001 directory:

- `events.jsonl`;
- frozen unit versions;
- frozen offers/payment terms;
- frozen travel-time evidence when available;
- the snapshot manifest and dataset ID.

It does not read a newer live inventory/price export after the snapshot has been frozen.

## Fail-closed gates

The command refuses to proceed when:

- snapshot hash verification fails;
- snapshot `training_ready=false`;
- frozen unit or offer evidence is missing;
- code commit SHA is absent;
- calibration produces fewer historical choices than the governed minimum;
- the run output directory is already populated.

The default governed minimum is currently 30 historical choices. This is only a minimum execution gate, not a claim that 30 decisions are statistically sufficient for all business conclusions.

## Run command

```bash
synapse-realworld laa-calibration-001-run \
  --snapshot-dir artifacts/laa_real_dataset_snapshot_001 \
  --model-registry-dir model_registry \
  --output-dir artifacts/laa_calibration_run_001 \
  --code-commit-sha <git-sha> \
  --holdout-fraction 0.2 \
  --bootstrap-samples 100 \
  --minimum-profile-confidence 0.3 \
  --diagnostic-population-size 5000 \
  --minimum-historical-choices 30 \
  --seed 42
```

The output directory is immutable and contains:

```text
laa_calibration_run_001/
  population_profile.json
  calibration.json
  run_manifest.json
```

## Population artifact

The empirical population profile is fitted from structured qualification evidence contained in Snapshot #001.

The profile:

- strips historical household analytics IDs;
- preserves observed joint feature combinations through empirical prototypes;
- carries `dataset_snapshot_id`;
- carries deterministic population content hash/version;
- reports population diagnostics and small-sample warnings.

It represents the **observed evidence base**, not automatically the entire LAA addressable market. Acquisition/channel bias must be assessed before calling it a market-population model.

## Temporal validation

Run #001 uses chronological train/holdout splitting rather than random row splitting.

Default:

```text
TRAIN   = earliest ~80% of decision timeline
HOLDOUT = latest ~20%
```

If a clean production calendar boundary is preferable, the evidence window and calibration policy should be versioned accordingly rather than silently changing the split after results are seen.

## Model artifact

Calibration creates and registers an immutable model artifact containing:

- dataset snapshot ID;
- code commit SHA;
- feature schema version;
- learned parameters;
- train metrics;
- holdout metrics;
- bootstrap coefficient intervals;
- retained bootstrap parameter vectors;
- diagnostics and provenance.

Training always registers the model as:

```text
candidate
```

It is never auto-approved.

## Human governance

A data reviewer may append:

```bash
synapse-realworld model-decide <ARTIFACT_ID> \
  --status validated \
  --decided-by <reviewer> \
  --reason "<documented review>" \
  --registry-dir model_registry
```

A separate authorized business owner may then append:

```bash
synapse-realworld model-decide <ARTIFACT_ID> \
  --status approved \
  --decided-by <business-owner> \
  --reason "Approved for bounded LAA decision support" \
  --registry-dir model_registry
```

The lifecycle remains:

```text
candidate -> validated -> approved/rejected -> archived
```

## Review checklist

Before validation/approval, inspect at minimum:

- data audit and provenance;
- future-leakage safeguards;
- holdout log loss;
- top-1/choice ranking behavior;
- baseline comparison;
- probability calibration where sample allows;
- coefficient direction and magnitude;
- price sensitivity;
- payment/cash-flow sensitivity;
- commute sensitivity;
- product substitution;
- outside-option migration;
- segment stability;
- bootstrap uncertainty;
- sparse-segment and acquisition-bias warnings.

Approval is a governance state for a bounded use case, not proof that the model is market truth.

## Relation to Prospective Experiment #001

An approved Calibration Run #001 artifact is a hard prerequisite for locking **LAA Prospective Experiment #001**.

The experiment workflow verifies that:

- the calibration run references Snapshot #001;
- the registered approved model references the same dataset snapshot;
- the fitted population profile references the same dataset snapshot;
- the forecast is locked before assignments or outcomes arrive.

## Important boundary

The v0.8 workflow being green in CI proves implementation correctness against synthetic contract fixtures. It does not mean real LAA Calibration Run #001 has occurred.

The production milestone is complete only when real redacted/approved evidence has produced:

1. a verified training-ready Snapshot #001;
2. an immutable Calibration Run #001 artifact;
3. documented holdout review;
4. explicit validated/approved or rejected governance decisions.
