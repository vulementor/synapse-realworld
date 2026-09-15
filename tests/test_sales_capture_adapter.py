from synapse_realworld.adapters.sales_capture import sales_capture_row_to_events


def test_sales_capture_row_maps_to_stable_events() -> None:
    row = {
        "captured_at": "2026-09-16T09:00:00+07:00",
        "party_id": "party-001",
        "household_id": "hh-001",
        "decision_stage": "qualified",
        "purchase_purpose": "own_stay",
        "household_size_band": "3-4",
        "children_band": "1",
        "household_income_band": "50-80m",
        "liquid_capital_band": "1-2b",
        "max_monthly_payment_band": "15-20m",
        "purchase_horizon": "90d",
        "workplace_zone": "VSIP III",
        "spouse_workplace_zone": "unknown",
        "stated_max_travel_min": "30",
        "preferred_product_type": "townhouse",
        "shortlisted_unit_code": "LK4-42",
        "reason_1": "commute",
        "reason_1_direction": "objection",
        "reason_2": "park_green_space",
        "reason_2_direction": "motivator",
        "competitor_mentioned": "unknown",
        "outside_option": "unresolved",
        "next_action": "send measured commute",
        "next_action_date": "2026-09-17",
        "confidence_note": "",
    }

    first = sales_capture_row_to_events(row)
    second = sales_capture_row_to_events(row)

    assert [event.event_type for event in first] == [
        "qualification_observed",
        "decision_stage_observed",
        "reason_observed",
        "reason_observed",
    ]
    assert [event.dedupe_key for event in first] == [event.dedupe_key for event in second]
    assert first[0].entity_type == "household"
    assert first[0].entity_id == "hh-001"
    assert first[0].payload["workplace_zone"] == "VSIP III"
    assert first[2].payload == {
        "reason_code": "commute",
        "direction": "objection",
        "evidence_type": "explicit",
    }
