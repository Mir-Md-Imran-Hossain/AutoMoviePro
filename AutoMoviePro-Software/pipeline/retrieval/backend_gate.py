"""Retrieval backend readiness gate (CLIP/FAISS optional production path)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


GATE_NAME = "RETRIEVAL_BACKEND_GATE.json"


def run_retrieval_backend_gate(work_dir: Path | None = None) -> dict[str, Any]:
    """Honest CLIP/FAISS availability — UNAVAILABLE is not PASS."""
    gate: dict[str, Any] = {
        "schema": "amp_retrieval_backend_gate_v1",
        "status": "UNKNOWN",
        "clip_available": False,
        "faiss_available": False,
        "fallback": "RETRIEVAL_UNAVAILABLE_allows_generation",
        "unknown_as_pass": False,
        "customer_isolation_required": True,
        "issues": [],
    }
    try:
        from pipeline.retrieval.embedding import resolve_embedding_backend

        _be, meta = resolve_embedding_backend(prefer="clip", allow_hash_fallback=False)
        gate["embedding_backend"] = dict(meta) if isinstance(meta, dict) else {"raw": str(meta)}
        status = str((meta or {}).get("status") or "").upper()
        kind = str((meta or {}).get("kind") or (meta or {}).get("backend") or "").lower()
        gate["clip_available"] = status == "OK" and "hash" not in kind and "unavailable" not in status.lower()
        if not gate["clip_available"]:
            gate["issues"].append("clip_backend_unavailable")
            if (meta or {}).get("reason"):
                gate["issues"].append(str((meta or {}).get("reason")))
            # Honest: FAISS alone is never semantic CLIP PASS
            if status in ("RETRIEVAL_UNAVAILABLE", "UNKNOWN"):
                gate["embedding_status"] = status
            gate["claims_semantic_truth"] = False
            gate["unknown_as_pass"] = False
    except Exception as exc:
        gate["issues"].append(f"clip_probe_failed:{str(exc)[:120]}")

    try:
        import faiss  # noqa: F401

        gate["faiss_available"] = True
    except Exception as exc:
        gate["issues"].append(f"faiss_unavailable:{str(exc)[:80]}")

    if gate["clip_available"] and gate["faiss_available"]:
        gate["status"] = "PASS"
    elif gate["clip_available"] or gate["faiss_available"]:
        gate["status"] = "PARTIAL"
    else:
        gate["status"] = "UNAVAILABLE"

    if work_dir is not None:
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        (Path(work_dir) / GATE_NAME).write_text(
            json.dumps(gate, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
    return gate
