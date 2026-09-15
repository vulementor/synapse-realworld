-- Synapse Real-World Platform
-- PostgreSQL production baseline for append-only evidence.
-- PII must live in a separate restricted vault/schema; do not add phone/email here.

CREATE TABLE IF NOT EXISTS canonical_events (
    event_id UUID PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    source_id TEXT NOT NULL,
    source_event_key TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_hash TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_canonical_events_entity_time
    ON canonical_events(entity_type, entity_id, occurred_at);

CREATE INDEX IF NOT EXISTS idx_canonical_events_type_time
    ON canonical_events(event_type, occurred_at);

CREATE INDEX IF NOT EXISTS idx_canonical_events_source_time
    ON canonical_events(source_id, occurred_at);

CREATE TABLE IF NOT EXISTS source_snapshots (
    snapshot_id UUID PRIMARY KEY,
    source_id TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    content_hash TEXT NOT NULL,
    record_count BIGINT NOT NULL CHECK (record_count >= 0),
    schema_version TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(source_id, content_hash, schema_version)
);

CREATE INDEX IF NOT EXISTS idx_source_snapshots_source_time
    ON source_snapshots(source_id, captured_at);

COMMENT ON TABLE canonical_events IS
    'Append-only pseudonymous evidence emitted by CRM/SAP/Ads/Sales/GIS adapters.';
COMMENT ON COLUMN canonical_events.dedupe_key IS
    'SHA-256(source_id | source_event_key | schema_version); ingestion idempotency boundary.';
