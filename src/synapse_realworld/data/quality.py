from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from synapse_realworld.domain.enums import InventoryState
from synapse_realworld.domain.models import ChoiceAlternative


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: str
    message: str
    severity: str = "error"


class DataQualityError(ValueError):
    def __init__(self, issues: Iterable[QualityIssue]):
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{i.code}: {i.message}" for i in self.issues))


def validate_choice_set(
    alternatives: Iterable[ChoiceAlternative],
    *,
    as_of: datetime,
    fail_closed: bool = True,
) -> tuple[QualityIssue, ...]:
    items = tuple(alternatives)
    issues: list[QualityIssue] = []

    if not items:
        issues.append(QualityIssue("empty_choice_set", "choice set is empty"))

    if not any(a.outside_option is not None for a in items):
        issues.append(
            QualityIssue("missing_outside_option", "choice set requires an outside option")
        )

    ids = [a.alternative_id for a in items]
    if len(ids) != len(set(ids)):
        issues.append(QualityIssue("duplicate_alternative", "alternative ids must be unique"))

    for alt in items:
        if alt.alternative_type != "laa_unit":
            continue
        assert alt.unit is not None and alt.offer is not None
        if not alt.availability_confirmed:
            issues.append(
                QualityIssue(
                    "unconfirmed_inventory",
                    f"{alt.alternative_id} availability not confirmed",
                )
            )
        if alt.unit.inventory_state != InventoryState.AVAILABLE:
            issues.append(
                QualityIssue(
                    "unavailable_unit",
                    f"{alt.alternative_id} inventory_state={alt.unit.inventory_state}",
                )
            )
        if alt.offer.effective_from > as_of:
            issues.append(
                QualityIssue("future_offer", f"{alt.alternative_id} offer not effective yet")
            )
        if alt.offer.effective_to is not None and as_of >= alt.offer.effective_to:
            issues.append(QualityIssue("expired_offer", f"{alt.alternative_id} offer expired"))
        if not alt.offer.source_id.strip():
            issues.append(
                QualityIssue("missing_provenance", f"{alt.alternative_id} offer has no source")
            )

    result = tuple(issues)
    if fail_closed and any(issue.severity == "error" for issue in result):
        raise DataQualityError(result)
    return result
