from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from synapse_realworld.audit import LAADataAudit, audit_laa_events
from synapse_realworld.domain.events import CanonicalEvent, SourceSnapshot


class SnapshotModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FileFingerprint(SnapshotModel):
    role: str
    filename: str
    sha256: str
    size_bytes: int = Field(ge=0)


class LAARealDatasetSnapshotManifest(SnapshotModel):
    snapshot_name: str = "LAA Real Dataset Snapshot #001"
    project_code: str = "LAA"
    snapshot_version: str = "001"
    dataset_snapshot_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    window_from: datetime | None = None
    window_to: datetime | None = None
    event_count: int = Field(ge=0)
    event_semantic_sha256: str
    events_file: FileFingerprint
    source_snapshot_count: int = Field(ge=0)
    source_snapshots_file: FileFingerprint
    input_files: tuple[FileFingerprint, ...]
    event_types: dict[str, int]
    sources: dict[str, int]
    audit: LAADataAudit
    training_ready: bool
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_identity(self) -> LAARealDatasetSnapshotManifest:
        if not self.dataset_snapshot_id.startswith("sha256:"):
            raise ValueError("dataset_snapshot_id must be a sha256 identifier")
        if self.window_from and self.window_to and self.window_from >= self.window_to:
            raise ValueError("window_from must be before window_to")
        return self


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _file_fingerprint(path: Path, *, role: str) -> FileFingerprint:
    content = path.read_bytes()
    return FileFingerprint(
        role=role,
        filename=path.name,
        sha256=_sha256_bytes(content),
        size_bytes=len(content),
    )


def _semantic_event_payload(event: CanonicalEvent) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "occurred_at": event.occurred_at.isoformat(),
        "source_id": event.source_id,
        "source_event_key": event.source_event_key,
        "payload": event.payload,
        "schema_version": event.schema_version,
    }


def _semantic_event_bytes(events: Iterable[CanonicalEvent]) -> bytes:
    rows = [
        json.dumps(
            _semantic_event_payload(event),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        for event in events
    ]
    return ("\n".join(rows) + ("\n" if rows else "")).encode("utf-8")


def _filter_window(
    events: Iterable[CanonicalEvent],
    *,
    window_from: datetime | None,
    window_to: datetime | None,
) -> tuple[CanonicalEvent, ...]:
    selected = []
    for event in events:
        if window_from is not None and event.occurred_at < window_from:
            continue
        if window_to is not None and event.occurred_at >= window_to:
            continue
        selected.append(event)
    return tuple(
        sorted(
            selected,
            key=lambda item: (
                item.occurred_at,
                item.source_id,
                item.source_event_key,
                item.event_type,
            ),
        )
    )


def _write_full_events(path: Path, events: Iterable[CanonicalEvent]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(
                json.dumps(
                    event.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
            )
            handle.write("\n")


def _write_source_snapshots(path: Path, snapshots: Iterable[SourceSnapshot]) -> None:
    rows = [
        snapshot.model_dump(mode="json")
        for snapshot in sorted(
            snapshots,
            key=lambda item: (item.captured_at, item.source_id, item.content_hash),
        )
    ]
    path.write_text(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _copy_input(path: Path, target_dir: Path, *, role: str) -> FileFingerprint:
    destination = target_dir / path.name
    shutil.copyfile(path, destination)
    return _file_fingerprint(destination, role=role)


def _manifest_identity_payload(
    *,
    project_code: str,
    snapshot_version: str,
    window_from: datetime | None,
    window_to: datetime | None,
    event_semantic_sha256: str,
    source_snapshots_sha256: str,
    input_files: tuple[FileFingerprint, ...],
) -> dict[str, Any]:
    return {
        "project_code": project_code,
        "snapshot_version": snapshot_version,
        "window_from": window_from.isoformat() if window_from else None,
        "window_to": window_to.isoformat() if window_to else None,
        "event_semantic_sha256": event_semantic_sha256,
        "source_snapshots_sha256": source_snapshots_sha256,
        "input_files": [item.model_dump(mode="json") for item in input_files],
    }


def create_laa_real_dataset_snapshot(
    *,
    events: Iterable[CanonicalEvent],
    source_snapshots: Iterable[SourceSnapshot],
    output_dir: str | Path,
    units_csv: str | Path,
    offers_csv: str | Path,
    travel_times_csv: str | Path | None = None,
    window_from: datetime | None = None,
    window_to: datetime | None = None,
    snapshot_version: str = "001",
) -> LAARealDatasetSnapshotManifest:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    evidence_dir = output / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    selected_events = _filter_window(
        events,
        window_from=window_from,
        window_to=window_to,
    )
    events_path = output / "events.jsonl"
    _write_full_events(events_path, selected_events)
    semantic_bytes = _semantic_event_bytes(selected_events)
    semantic_hash = _sha256_bytes(semantic_bytes)

    snapshots_path = output / "source_snapshots.json"
    materialized_snapshots = tuple(source_snapshots)
    _write_source_snapshots(snapshots_path, materialized_snapshots)

    input_files = [
        _copy_input(Path(units_csv), evidence_dir, role="unit_versions"),
        _copy_input(Path(offers_csv), evidence_dir, role="offers"),
    ]
    if travel_times_csv is not None:
        input_files.append(
            _copy_input(Path(travel_times_csv), evidence_dir, role="travel_times")
        )
    frozen_inputs = tuple(input_files)

    identity = _manifest_identity_payload(
        project_code="LAA",
        snapshot_version=snapshot_version,
        window_from=window_from,
        window_to=window_to,
        event_semantic_sha256=semantic_hash,
        source_snapshots_sha256=_file_fingerprint(
            snapshots_path,
            role="source_snapshots",
        ).sha256,
        input_files=frozen_inputs,
    )
    identity_bytes = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    dataset_snapshot_id = f"sha256:{_sha256_bytes(identity_bytes)}"

    audit = audit_laa_events(selected_events)
    manifest = LAARealDatasetSnapshotManifest(
        snapshot_version=snapshot_version,
        dataset_snapshot_id=dataset_snapshot_id,
        window_from=window_from,
        window_to=window_to,
        event_count=len(selected_events),
        event_semantic_sha256=semantic_hash,
        events_file=_file_fingerprint(events_path, role="canonical_events"),
        source_snapshot_count=len(materialized_snapshots),
        source_snapshots_file=_file_fingerprint(
            snapshots_path,
            role="source_snapshots",
        ),
        input_files=frozen_inputs,
        event_types=dict(sorted(Counter(item.event_type for item in selected_events).items())),
        sources=dict(sorted(Counter(item.source_id for item in selected_events).items())),
        audit=audit,
        training_ready=audit.training_ready,
        blockers=audit.blockers,
        warnings=audit.warnings,
    )
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def load_laa_snapshot_manifest(path: str | Path) -> LAARealDatasetSnapshotManifest:
    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / "manifest.json"
    return LAARealDatasetSnapshotManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )


def verify_laa_snapshot_directory(path: str | Path) -> LAARealDatasetSnapshotManifest:
    root = Path(path)
    manifest = load_laa_snapshot_manifest(root)
    events_path = root / manifest.events_file.filename
    snapshots_path = root / manifest.source_snapshots_file.filename
    if _file_fingerprint(events_path, role="canonical_events").sha256 != manifest.events_file.sha256:
        raise ValueError("events file hash does not match snapshot manifest")
    if (
        _file_fingerprint(snapshots_path, role="source_snapshots").sha256
        != manifest.source_snapshots_file.sha256
    ):
        raise ValueError("source snapshots hash does not match snapshot manifest")
    for item in manifest.input_files:
        candidate = root / "evidence" / item.filename
        if _file_fingerprint(candidate, role=item.role).sha256 != item.sha256:
            raise ValueError(f"evidence file hash mismatch: {item.role}")
    return manifest
