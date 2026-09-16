from pathlib import Path

from synapse_realworld.audit import audit_laa_events
from synapse_realworld.connectors import GenericCsvConnector, get_laa_profile
from synapse_realworld.domain.events import CanonicalEvent
from synapse_realworld.ingestion import EventIngestor
from synapse_realworld.persistence import DuckDBStore


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_crm_connector_pseudonymizes_identity_and_is_idempotent(tmp_path) -> None:
    csv_path = _write(
        tmp_path / "crm.csv",
        "lead_id,contact_id,created_at,lead_source,campaign_id\n"
        "L-001,PHONE-0900000000,2026-09-16T08:00:00+07:00,facebook,C-01\n",
    )
    batch = GenericCsvConnector(
        csv_path,
        source_id="crm-production",
        profile=get_laa_profile("crm_leads"),
    ).extract()
    assert len(batch.events) == 1
    event = batch.events[0]
    assert event.entity_id.startswith("sha256:")
    assert "0900000000" not in event.entity_id
    assert event.payload["lead_source"] == "facebook"

    db = tmp_path / "synapse.duckdb"
    with DuckDBStore(db) as store:
        ingestor = EventIngestor(store, store)
        first = ingestor.ingest(
            source_id=batch.source_id,
            events=batch.events,
            snapshot=batch.snapshot,
        )
        second = ingestor.ingest(
            source_id=batch.source_id,
            events=batch.events,
            snapshot=batch.snapshot,
        )
    assert first.inserted == 1
    assert second.inserted == 0
    assert second.duplicates == 1


def test_data_audit_blocks_training_without_real_decision_evidence() -> None:
    events = (
        CanonicalEvent(
            event_type="qualification_observed",
            entity_type="household",
            entity_id="HH-1",
            occurred_at="2026-09-16T08:00:00+07:00",
            source_id="crm",
            source_event_key="q1",
            payload={
                "purchase_purpose": "own_stay",
                "workplace_zone": "VSIP III",
                "shortlisted_unit_code": "LK4-42",
            },
        ),
    )
    audit = audit_laa_events(events)
    assert audit.qualified_households == 1
    assert audit.training_ready is False
    assert "no_verified_decision_outcomes" in audit.blockers
    assert "no_temporal_inventory_evidence" in audit.blockers
    assert "no_temporal_offer_evidence" in audit.blockers


def test_data_audit_recognizes_core_decision_evidence() -> None:
    events = []
    for index in range(30):
        household_id = f"HH-{index}"
        events.extend(
            [
                CanonicalEvent(
                    event_type="qualification_observed",
                    entity_type="household",
                    entity_id=household_id,
                    occurred_at="2026-09-16T08:00:00+07:00",
                    source_id="crm",
                    source_event_key=f"q-{index}",
                    payload={
                        "purchase_purpose": "own_stay",
                        "workplace_zone": "VSIP III",
                        "shortlisted_unit_code": "LK4-42",
                        "outside_option": "continue_renting",
                    },
                ),
                CanonicalEvent(
                    event_type="decision_outcome_observed",
                    entity_type="household",
                    entity_id=household_id,
                    occurred_at="2026-09-20T08:00:00+07:00",
                    source_id="crm",
                    source_event_key=f"o-{index}",
                    payload={
                        "outcome_type": "lost",
                        "outside_option": "continue_renting",
                        "verified": True,
                    },
                ),
            ]
        )
    events.extend(
        [
            CanonicalEvent(
                event_type="unit_inventory_observed",
                entity_type="unit",
                entity_id="LK4-42",
                occurred_at="2026-09-16T07:00:00+07:00",
                source_id="inventory",
                source_event_key="inv-1",
                payload={"inventory_state": "available", "product_type": "townhouse"},
            ),
            CanonicalEvent(
                event_type="offer_observed",
                entity_type="unit",
                entity_id="LK4-42",
                occurred_at="2026-09-16T07:00:00+07:00",
                source_id="offers",
                source_event_key="offer-1",
                payload={
                    "list_price_vnd": "3000000000",
                    "payment_plan_code": "PLAN-A",
                },
            ),
        ]
    )
    audit = audit_laa_events(events)
    assert audit.trainable_choice_events == 30
    assert audit.readiness["price"].status == "ready"
    assert audit.readiness["payment"].status == "ready"
    assert audit.readiness["commute"].status == "ready"
    assert audit.readiness["product"].status == "ready"
    assert audit.readiness["outside_options"].status == "ready"
    assert audit.training_ready is True
