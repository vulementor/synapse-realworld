# v0.5 implementation checkpoint

This file intentionally stays short. The complete operational and design runbook is in `docs/EXPERIMENT_LOOP_V0_5.md`.

Implemented in v0.5:

- immutable prospective experiment definitions;
- paired control/treatment scenario prediction from governed models;
- prediction lock before observations;
- rejection of backdated outcomes;
- append-only idempotent experiment observations;
- randomized-assignment causal guard;
- predicted-vs-actual evaluation;
- per-model experiment scorecards;
- full closed-loop GitHub Actions smoke test.

The next model-operations slice should add multiple pre-registered challenger predictions, experiment-design QA, drift thresholds and governed recalibration recommendations.
