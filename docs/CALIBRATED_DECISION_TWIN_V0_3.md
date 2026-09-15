# Synapse Real-World Platform — Calibrated Decision Twin v0.3

v0.3 adds the first governance and uncertainty layer on top of the v0.2 real-data pipeline.

The key change is conceptual: **a fitted set of weights is not automatically a usable model**.
A model must be reproducible, diagnosed, registered, reviewed, and explicitly approved before it can be used for business decision support.

## Calibration lifecycle

```text
Versioned evidence
      │
      ▼
Historical ChoiceEvent reconstruction
      │
      ▼
Leakage-safe Decision Dataset
      │
      ├── chronological train window
      └── latest-period holdout
      │
      ▼
Multinomial-logit calibration
      │
      ▼
Diagnostics
  ├── holdout log loss
  ├── top-1 accuracy
  ├── uniform-choice baseline comparison
  ├── segment metrics
  └── bootstrap coefficient intervals
      │
      ▼
Immutable ModelArtifact
      │
      ▼
candidate → validated → approved → archived
             └───────→ rejected → archived
```

Approval is intentionally separate from training. Synapse does not self-approve a model.

## Governed model artifact

Every model artifact records:

- logical model name and version;
- model family;
- code commit SHA;
- combined dataset snapshot ID;
- training time window;
- feature-schema version;
- fitted parameters;
- train metrics;
- holdout metrics;
- diagnostics and warnings;
- immutable content hash.

The local reference registry stores immutable artifact JSON plus append-only decision JSONL. A production implementation can move the same registry contract to PostgreSQL/object storage.

## Governance states

Allowed transitions:

```text
candidate → validated
candidate → rejected
candidate → archived
validated → approved
validated → rejected
validated → archived
approved → archived
rejected → archived
```

Direct `candidate → approved` is blocked. Archived models cannot be reactivated by the v0.3 registry.

## Calibration diagnostics

### Temporal holdout

Validation uses the newest observations rather than a random split. This protects against a common failure mode where future market conditions leak into the training distribution.

### Uniform-choice baseline

The calibrated model is compared with the log loss of a model that assigns equal probability to every available alternative in each historical choice set.

### Segment diagnostics

Holdout metrics are broken down by `purchase_purpose` where data exists. Sparse segments create warnings rather than false precision.

### Bootstrap coefficient intervals

Synapse repeatedly resamples the **training set**, refits the logit model, and estimates percentile intervals for each coefficient. Holdout examples remain reserved for evaluation.

v0.3 warnings include:

- fewer than 100 training choices;
- fewer than 50 holdout choices;
- fewer than 20 holdout choices in a segment;
- coefficient interval crossing zero.

These warnings are evidence for human review; they are not silently suppressed.

## Temporal commute evidence

v0.3 adds a spatial contract for commute/accessibility features:

- origin/destination anchor;
- travel mode;
- departure bucket;
- travel time;
- optional distance;
- optional p90 travel-time reliability;
- observation timestamp;
- validity interval;
- provenance.

A household workplace anchor is also time-versioned. If a workplace is first observed on September 10, it cannot be used to explain a decision on September 5.

This keeps the commute feature under the same anti-leakage rules as price, inventory, policy and buyer features.

## LAA calibration with commute

The repository includes synthetic, non-production examples only:

```bash
DB=./synapse.duckdb
REGISTRY=./model_registry

synapse-realworld calibrate \
  --units-csv examples/data/laa_unit_versions_sample.csv \
  --offers-csv examples/data/laa_offers_sample.csv \
  --travel-times-csv examples/data/laa_travel_times_sample.csv \
  --project-anchor-id LAA \
  --db "$DB" \
  --registry-dir "$REGISTRY" \
  --code-commit-sha "$(git rev-parse HEAD)" \
  --bootstrap-samples 50 \
  --output calibration.json
```

The output is a **candidate**, not an approved production model.

## Review and approval

```bash
ARTIFACT_ID=<uuid-from-calibration-output>

synapse-realworld model-decide "$ARTIFACT_ID" \
  --status validated \
  --decided-by data-lead \
  --reason "Temporal holdout and diagnostics reviewed" \
  --registry-dir "$REGISTRY"

synapse-realworld model-decide "$ARTIFACT_ID" \
  --status approved \
  --decided-by business-owner \
  --reason "Approved for bounded decision-support scenarios" \
  --registry-dir "$REGISTRY"

synapse-realworld models --registry-dir "$REGISTRY"
```

## What approval does not mean

An approved v0.3 model is still decision support. It does **not** authorize:

- autonomous price changes;
- legally binding customer offers;
- autonomous credit/financing decisions;
- claims of individual buyer certainty;
- extrapolation far outside observed data without an out-of-distribution warning layer.

## Next engineering slice

1. real LAA CRM/SAP/Ads source mappings;
2. 60–90 day real historical backfill;
3. richer choice-set competitor alternatives;
4. model-selection and champion/challenger logic;
5. posterior/mixed-logit or hierarchical preference heterogeneity;
6. empirical synthetic-population calibration;
7. scenario uncertainty propagation;
8. experiment registry linking predictions to real A/B outcomes.
