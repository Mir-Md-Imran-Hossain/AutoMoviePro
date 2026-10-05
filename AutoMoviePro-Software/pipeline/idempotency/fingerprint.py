"""SHA-256 request fingerprint (BUILD-03)."""
from __future__ import annotations

import hashlib
from typing import Any

from pipeline.idempotency.normalize import canonical_json


BUILD03_FINGERPRINT_VERSION = "build03-1.0.0"


def compute_fingerprint(
    *,
    job_id: str,
    stage: str,
    entity_id: str,
    contract_version: str = "1.0.0",
    provider: str = "",
    model: str = "",
    inputs: dict[str, Any] | None = None,
) -> str:
    """
    Deterministic semantic fingerprint.
    Attempt number is NOT included — retries share the same fingerprint.
    """
    payload = {
        "fingerprint_version": BUILD03_FINGERPRINT_VERSION,
        "job_id": job_id,
        "stage": stage,
        "entity_id": entity_id,
        "contract_version": contract_version,
        "provider": provider or "",
        "model": model or "",
        "inputs": inputs or {},
    }
    canonical = canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_artifact(path: str, *, max_bytes: int = 65536) -> str:
    """Hash file content (partial read for large media)."""
    import os

    h = hashlib.sha256()
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size <= max_bytes:
                h.update(f.read())
            else:
                h.update(f.read(max_bytes // 2))
                f.seek(max(size - max_bytes // 2, 0))
                h.update(f.read(max_bytes // 2))
                h.update(str(size).encode())
    except OSError:
        return ""
    return h.hexdigest()


def hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()
