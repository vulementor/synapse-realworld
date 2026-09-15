from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from synapse_realworld.behaviour.calibration import (
    FEATURE_NAMES,
    CalibrationExample,
    CalibrationMetrics,
    MultinomialLogitCalibrator,
)


class DiagnosticsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoefficientInterval(DiagnosticsModel):
    estimate: float
    lower: float
    upper: float
    bootstrap_samples: int = Field(gt=0)


class BaselineComparison(DiagnosticsModel):
    model_log_loss: float = Field(ge=0)
    uniform_log_loss: float = Field(ge=0)
    improvement_pct: float


class CalibrationDiagnostics(DiagnosticsModel):
    coefficient_intervals: dict[str, CoefficientInterval]
    segment_metrics: dict[str, CalibrationMetrics]
    baseline: BaselineComparison
    warnings: tuple[str, ...] = ()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return ordered[lower_index] * (1 - fraction) + ordered[upper_index] * fraction


def uniform_baseline_log_loss(examples: Iterable[CalibrationExample]) -> float:
    data = tuple(examples)
    if not data:
        return 0.0
    return sum(math.log(len(example.alternatives)) for example in data) / len(data)


def build_calibration_diagnostics(
    *,
    examples: Iterable[CalibrationExample],
    weights: dict[str, float],
    calibrator: MultinomialLogitCalibrator | None = None,
    bootstrap_samples: int = 100,
    seed: int = 42,
) -> CalibrationDiagnostics:
    data = tuple(examples)
    if not data:
        raise ValueError("diagnostics require at least one example")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")

    model = calibrator or MultinomialLogitCalibrator()
    model_metrics = model.evaluate(data, weights=weights)
    uniform_loss = uniform_baseline_log_loss(data)
    improvement = (
        (uniform_loss - model_metrics.log_loss) / uniform_loss * 100
        if uniform_loss > 0
        else 0.0
    )

    grouped: dict[str, list[CalibrationExample]] = defaultdict(list)
    for example in data:
        grouped[example.household.purchase_purpose.value].append(example)
    segment_metrics = {
        segment: model.evaluate(segment_examples, weights=weights)
        for segment, segment_examples in sorted(grouped.items())
    }

    rng = random.Random(seed)
    bootstrap_weights: dict[str, list[float]] = {name: [] for name in FEATURE_NAMES}
    bootstrap_calibrator = MultinomialLogitCalibrator(
        learning_rate=model.learning_rate,
        max_epochs=min(model.max_epochs, 500),
        l2=model.l2,
        tolerance=model.tolerance,
    )
    for _ in range(bootstrap_samples):
        sample = tuple(rng.choice(data) for _ in range(len(data)))
        fitted = bootstrap_calibrator.fit(sample)
        for name in FEATURE_NAMES:
            bootstrap_weights[name].append(fitted.weights[name])

    intervals = {
        name: CoefficientInterval(
            estimate=weights[name],
            lower=_percentile(values, 0.025),
            upper=_percentile(values, 0.975),
            bootstrap_samples=bootstrap_samples,
        )
        for name, values in bootstrap_weights.items()
    }

    warnings: list[str] = []
    if len(data) < 100:
        warnings.append("small_sample: fewer than 100 historical choices")
    for segment, metrics in segment_metrics.items():
        if metrics.examples < 20:
            warnings.append(f"small_segment:{segment}: fewer than 20 examples")
    for name, interval in intervals.items():
        if interval.lower <= 0 <= interval.upper:
            warnings.append(f"uncertain_coefficient:{name}: interval crosses zero")

    return CalibrationDiagnostics(
        coefficient_intervals=intervals,
        segment_metrics=segment_metrics,
        baseline=BaselineComparison(
            model_log_loss=model_metrics.log_loss,
            uniform_log_loss=uniform_loss,
            improvement_pct=improvement,
        ),
        warnings=tuple(warnings),
    )
