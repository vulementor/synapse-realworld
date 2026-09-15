from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from uuid import UUID

from synapse_realworld.domain.enums import InventoryState, ProductType
from synapse_realworld.domain.models import Offer, Unit
from synapse_realworld.domain.temporal import UnitVersion


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _optional_dt(value: str | None) -> datetime | None:
    return _dt(value) if value else None


def load_unit_versions_csv(path: str | Path) -> tuple[UnitVersion, ...]:
    records: list[UnitVersion] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            unit = Unit(
                unit_id=UUID(row["unit_id"]),
                project_id=UUID(row["project_id"]),
                unit_code=row["unit_code"],
                product_type=ProductType(row["product_type"]),
                inventory_state=InventoryState(row["inventory_state"]),
                lot_area_m2=float(row["lot_area_m2"]) if row.get("lot_area_m2") else None,
                built_area_m2=(
                    float(row["built_area_m2"]) if row.get("built_area_m2") else None
                ),
            )
            records.append(
                UnitVersion(
                    unit=unit,
                    effective_from=_dt(row["effective_from"]),
                    effective_to=_optional_dt(row.get("effective_to")),
                    source_id=row["source_id"],
                )
            )
    return tuple(records)


def load_offers_csv(path: str | Path) -> tuple[Offer, ...]:
    offers: list[Offer] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            offers.append(
                Offer(
                    unit_id=UUID(row["unit_id"]) if row.get("unit_id") else None,
                    product_type=ProductType(row["product_type"]) if row.get("product_type") else None,
                    list_price=float(row["list_price"]),
                    net_price=float(row["net_price"]) if row.get("net_price") else None,
                    discount_pct=float(row.get("discount_pct") or 0),
                    incentive_cash=float(row.get("incentive_cash") or 0),
                    payment_plan_code=row["payment_plan_code"],
                    down_payment_pct=float(row.get("down_payment_pct") or 0.3),
                    monthly_payment_est=float(row.get("monthly_payment_est") or 0),
                    effective_from=_dt(row["effective_from"]),
                    effective_to=_optional_dt(row.get("effective_to")),
                    source_id=row["source_id"],
                )
            )
    return tuple(offers)
