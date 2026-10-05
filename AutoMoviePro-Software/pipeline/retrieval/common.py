"""Retrieval adapters — candidate search only; never publish/repair/approve."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_RETRIEVAL_UNAVAILABLE = "RETRIEVAL_UNAVAILABLE"
STATUS_OBSERVATION_UNAVAILABLE = "OBSERVATION_UNAVAILABLE"
STATUS_NO_SUITABLE = "NO_SUITABLE_ASSET"
STATUS_RETRIEVAL_AVAILABLE = "RETRIEVAL_AVAILABLE"

SCHEMA_RETRIEVAL = "amp_retrieval_visual_candidate_v1"
SCHEMA_EMBEDDING = "amp_retrieval_embedding_meta_v1"
SCHEMA_INDEX = "amp_retrieval_faiss_index_v1"

HEURISTIC = "HEURISTIC"  # legacy alias
HEURISTIC_NON_SEMANTIC = "HEURISTIC_NON_SEMANTIC"
CLIP = "CLIP"
CLIP_MODEL_ID = "openai/clip-vit-base-patch32"
CLIP_OPENCLIP_ARCH = "ViT-B-32"
CLIP_OPENCLIP_PRETRAINED = "openai"
CLIP_EMBED_VERSION = "v1"
HASH_EMBED_MODEL = "amp_hash_embed_v1"
HASH_EMBED_VERSION = "v1"
EMBED_DIM_DEFAULT = 512
REASON_EMBEDDING_BACKEND_UNAVAILABLE = "EMBEDDING_BACKEND_UNAVAILABLE"
# Production CLIP selection (single backend): open_clip ViT-B-32 / openai weights
CLIP_PRODUCTION_IMPL = "open_clip"
CLIP_PRODUCTION_MODEL = f"open_clip:{CLIP_OPENCLIP_ARCH}:{CLIP_OPENCLIP_PRETRAINED}"


def content_hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash_file(path: Path | str) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def content_hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def unavailable(
    *,
    reason: str,
    detail: str = "",
    tool: str = "retrieval",
    schema: str = SCHEMA_RETRIEVAL,
) -> dict[str, Any]:
    return {
        "schema": schema,
        "status": STATUS_RETRIEVAL_UNAVAILABLE,
        "retrieval_executed": False,
        "provider_verified": False,
        "tool": tool,
        "reason": reason,
        "detail": (detail or "")[:400],
        "issues": [f"retrieval_unavailable:{reason}"],
        "unknown_as_pass": False,
        "authority": "retrieval_candidate_only",
        "creates_final_gate": False,
        "publishes": False,
        "approves": False,
        "repairs": False,
        "publishability_pass": False,
        "replaces_continuity_tracker": False,
        "semantic_final_authority": False,
        "candidates": [],
        "selected": None,
    }


def strip_secrets(meta: dict[str, Any]) -> dict[str, Any]:
    """Never persist API keys/secrets in embedding or asset metadata."""
    banned = {
        "api_key",
        "apikey",
        "authorization",
        "token",
        "secret",
        "password",
        "bearer",
        "pexels_api",
        "pexels_api_key",
    }
    out: dict[str, Any] = {}
    for k, v in (meta or {}).items():
        lk = str(k).lower().replace("-", "_")
        if lk in banned or any(b in lk for b in ("api_key", "secret", "token", "password")):
            continue
        if isinstance(v, dict):
            out[k] = strip_secrets(v)
        else:
            out[k] = v
    return out


def asset_metadata(
    *,
    asset_id: str,
    source: str,
    source_url: str = "",
    local_path: str = "",
    media_type: str,
    width: int = 0,
    height: int = 0,
    duration: float = 0.0,
    embedding_model: str = "",
    embedding_version: str = "",
    content_hash: str = "",
    license_usage: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    meta = {
        "asset_id": asset_id,
        "source": source,
        "source_url": source_url,
        "local_path": local_path,
        "media_type": media_type,
        "width": int(width or 0),
        "height": int(height or 0),
        "duration": float(duration or 0.0),
        "embedding_model": embedding_model,
        "embedding_version": embedding_version,
        "created_at": time.time(),
        "content_hash": content_hash,
        "license_usage": license_usage,
        "retrieved_at": time.time(),
    }
    if extra:
        meta.update(strip_secrets(extra))
    return strip_secrets(meta)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
