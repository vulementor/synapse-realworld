# Synapse Real-World Platform — Architecture v0.1

## 1. Platform objective

Synapse Real-World is a decision platform for reconstructing real-world decision states, fitting/calibrating behavioural models, generating synthetic populations, executing counterfactual scenarios, and validating predictions against subsequent real outcomes.

The first implementation domain is residential real estate, but platform contracts should not assume that the long-term platform is only a CRM extension or only a property simulator.

## 2. Bounded contexts

### Domain contracts
Canonical, immutable entities. PII is not part of these analytical contracts.

### Data / evidence
Responsible for source provenance, effective dating, snapshots, deduplication, quality gates and leakage prevention.

### Behaviour
Core probability/utility layer. v0.1 contains a transparent baseline; real LAA coefficients must be calibrated from historical data.

### Population
Creates versioned synthetic household cohorts. v0.1 uses seeded distributions; future versions add empirical resampling, IPF/raking and Bayesian population models.

### Simulation
Applies scenarios to valid choice sets and aggregates outcomes. A simulation must be reproducible from metadata.

### Project adapters
Domain-specific fixtures/mappings. `projects/laa` is the first reference adapter and must not leak LAA assumptions into generic platform modules.

## 3. Golden rule: time-correct choice sets

A historical model is invalid when it lets a buyer choose a product or offer that was not actually available at that moment.

Every production choice event therefore requires:

- event timestamp;
- inventory snapshot/effective validity;
- offer effective range;
- source provenance;
- at least one outside option.

Critical violations fail closed rather than silently entering a training or simulation dataset.

## 4. LLM boundary

LLMs are useful for:

- extracting `reason_code` from notes/transcripts with confidence and evidence;
- summarizing household context;
- normalizing messy source text;
- explaining calibrated model output;
- generating human-readable scenario narratives.

LLMs must not be the sole source of purchase probability, missing financial attributes, verified outcomes, inventory truth, or legal conclusions.

## 5. Persistence roadmap

v0.1 intentionally keeps persistence out of core interfaces. Planned adapters:

- local: DuckDB/Parquet;
- production: PostgreSQL + PostGIS;
- event ingestion: append-only source events plus materialized analytical snapshots;
- object evidence: immutable source pointers/hashes where permitted.

## 6. Evolution to Spatial Real-World

Spatial/3D layers should consume the same canonical project/unit/household/choice contracts. GIS, BIM, 3D Gaussian splats, IoT and facility data enrich utilities/features; they should not replace the calibrated behaviour and evidence layers.
