from __future__ import annotations

from uuid import UUID, uuid5

SYNAPSE_ANALYTICS_NAMESPACE = UUID("78e92a33-6e3d-4c2c-bada-e56a8663378a")


def analytics_uuid(value: str, *, namespace: str = "default") -> UUID:
    """Return a stable analytics UUID without requiring source IDs to be UUIDs.

    This is not a replacement for the restricted PII/identity vault. Callers must
    pass a pseudonymous source key, not raw phone/email/document numbers.
    """

    normalized = value.strip()
    if not normalized:
        raise ValueError("analytics identity value cannot be empty")
    try:
        return UUID(normalized)
    except ValueError:
        return uuid5(SYNAPSE_ANALYTICS_NAMESPACE, f"{namespace}:{normalized}")
