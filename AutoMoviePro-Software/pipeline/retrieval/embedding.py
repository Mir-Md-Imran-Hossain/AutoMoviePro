"""Optional CLIP embedding backend — CPU preferred; never required at startup.

T1-B: ONE production CLIP path (open_clip ViT-B-32 openai).
Hash embedder remains HEURISTIC_NON_SEMANTIC fallback only — never semantic PASS.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol, Tuple

import numpy as np

from pipeline.retrieval.common import (
    CLIP,
    CLIP_EMBED_VERSION,
    CLIP_MODEL_ID,
    CLIP_OPENCLIP_ARCH,
    CLIP_OPENCLIP_PRETRAINED,
    CLIP_PRODUCTION_IMPL,
    CLIP_PRODUCTION_MODEL,
    EMBED_DIM_DEFAULT,
    HASH_EMBED_MODEL,
    HASH_EMBED_VERSION,
    HEURISTIC,
    HEURISTIC_NON_SEMANTIC,
    REASON_EMBEDDING_BACKEND_UNAVAILABLE,
    STATUS_OBSERVATION_UNAVAILABLE,
    STATUS_RETRIEVAL_UNAVAILABLE,
    STATUS_UNKNOWN,
    content_hash_bytes,
    content_hash_file,
    content_hash_text,
)

logger = logging.getLogger(__name__)

# Process-local lazy CLIP cache: (arch, pretrained, device) -> bundle
_CLIP_MODEL_CACHE: dict[Tuple[str, str, str], dict[str, Any]] = {}


class EmbeddingBackend(Protocol):
    model_id: str
    version: str
    dim: int
    kind: str  # CLIP | HEURISTIC_NON_SEMANTIC

    def available(self) -> bool: ...

    def embed_text(self, text: str) -> np.ndarray: ...

    def embed_image(self, path: Path | str) -> np.ndarray: ...


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    v = np.asarray(vec, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(v))
    if n <= 1e-12:
        return v
    return (v / n).astype(np.float32)


def clip_cache_root() -> Path:
    env = (os.environ.get("AMP_CLIP_CACHE") or "").strip()
    if env:
        root = Path(env)
    else:
        try:
            from app.config import DATA_DIR

            root = Path(DATA_DIR) / "models" / "open-clip"
        except Exception:
            root = Path(__file__).resolve().parents[2] / "data" / "models" / "open-clip"
    root.mkdir(parents=True, exist_ok=True)
    return root


def index_namespace_for_backend(backend: EmbeddingBackend) -> str:
    """Separate FAISS namespaces — never mix hash + CLIP in one index."""
    safe_model = (
        str(backend.model_id)
        .replace("/", "_")
        .replace(":", "_")
        .replace(" ", "_")
    )
    kind = str(backend.kind or "unknown").lower()
    return f"{kind}__{safe_model}__d{int(backend.dim)}__{backend.version}"


def namespaced_index_root(base_root: Path | str, backend: EmbeddingBackend) -> Path:
    return Path(base_root) / index_namespace_for_backend(backend)


@dataclass
class HashEmbeddingBackend:
    """Deterministic CPU embedder — HEURISTIC_NON_SEMANTIC only.

    NOT production CLIP. NOT semantic verification. NOT CLIP-equivalent.
    """

    dim: int = EMBED_DIM_DEFAULT
    model_id: str = HASH_EMBED_MODEL
    version: str = HASH_EMBED_VERSION
    kind: str = HEURISTIC_NON_SEMANTIC
    device: str = "cpu"
    dtype: str = "float32"

    def available(self) -> bool:
        return True

    def _embed_bytes(self, data: bytes) -> np.ndarray:
        seed = int(hashlib.sha256(data).hexdigest()[:16], 16) % (2**32 - 1)
        rng = np.random.RandomState(seed)
        return _l2_normalize(rng.randn(self.dim).astype(np.float32))

    def embed_text(self, text: str) -> np.ndarray:
        return self._embed_bytes((text or "").encode("utf-8"))

    def embed_image(self, path: Path | str) -> np.ndarray:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(str(p))
        return self._embed_bytes(p.read_bytes())


class ClipEmbeddingBackend:
    """Lazy open_clip ViT-B-32 (openai) — single production CLIP backend.

    transformers path retained only as secondary load attempt if open_clip missing,
    still one ClipEmbeddingBackend class (not a second competing engine).
    GPU optional via device=; CPU default. Never mandatory GPU.
    """

    def __init__(
        self,
        *,
        model_id: str = CLIP_PRODUCTION_MODEL,
        version: str = CLIP_EMBED_VERSION,
        device: str = "",
    ) -> None:
        env_dev = (os.environ.get("AMP_CLIP_DEVICE") or "").strip()
        self.model_id = model_id or CLIP_PRODUCTION_MODEL
        self.version = version
        self.kind = CLIP
        self.device = (device or env_dev or "cpu").strip() or "cpu"
        self.dim = EMBED_DIM_DEFAULT
        self.dtype = "float32"
        self.normalized = True
        self._impl: Optional[str] = None
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._error = ""
        self._load_sec: Optional[float] = None
        self._from_cache = False

    def available(self) -> bool:
        return self._ensure() is None

    def probe(self) -> dict[str, Any]:
        err = self._ensure()
        return {
            "available": err is None,
            "backend": CLIP_PRODUCTION_IMPL if err is None else "",
            "model_id": self.model_id,
            "version": self.version,
            "kind": self.kind,
            "device": self.device,
            "dtype": self.dtype,
            "embedding_dim": self.dim,
            "normalized": self.normalized,
            "impl": self._impl or "",
            "error": err or "",
            "gpu_mandatory": False,
            "load_sec": self._load_sec,
            "from_cache": self._from_cache,
            "cache_root": str(clip_cache_root()),
            "claims_semantic_truth": False,
        }

    def _ensure(self) -> Optional[str]:
        if self._model is not None:
            return None
        if self._error:
            return self._error

        cache_key = (CLIP_OPENCLIP_ARCH, CLIP_OPENCLIP_PRETRAINED, self.device)
        cached = _CLIP_MODEL_CACHE.get(cache_key)
        if cached:
            self._model = cached["model"]
            self._preprocess = cached["preprocess"]
            self._tokenizer = cached["tokenizer"]
            self._impl = cached["impl"]
            self.dim = int(cached["dim"])
            self.model_id = cached["model_id"]
            self._from_cache = True
            self._load_sec = 0.0
            return None

        t0 = time.perf_counter()
        # Preferred: open_clip (ONE production backend)
        try:
            import open_clip  # type: ignore
            import torch

            # Prefer HF/torch hub cache under AMP data when possible
            cache_dir = str(clip_cache_root())
            os.environ.setdefault("TORCH_HOME", cache_dir)
            os.environ.setdefault("HF_HOME", str(Path(cache_dir) / "hf"))

            model, _, preprocess = open_clip.create_model_and_transforms(
                CLIP_OPENCLIP_ARCH,
                pretrained=CLIP_OPENCLIP_PRETRAINED,
            )
            tokenizer = open_clip.get_tokenizer(CLIP_OPENCLIP_ARCH)
            model = model.to(self.device)
            model.eval()
            visual = getattr(model, "visual", None)
            dim = int(getattr(visual, "output_dim", None) or getattr(model, "embed_dim", None) or 512)
            self._model = model
            self._preprocess = preprocess
            self._tokenizer = tokenizer
            self._impl = CLIP_PRODUCTION_IMPL
            self.model_id = CLIP_PRODUCTION_MODEL
            self.dim = dim
            self._load_sec = round(time.perf_counter() - t0, 3)
            self._from_cache = False
            _CLIP_MODEL_CACHE[cache_key] = {
                "model": model,
                "preprocess": preprocess,
                "tokenizer": tokenizer,
                "impl": self._impl,
                "dim": dim,
                "model_id": self.model_id,
            }
            return None
        except Exception as exc:
            logger.debug("open_clip unavailable: %s", exc)

        # Secondary load of same conceptual CLIP (ViT-B/32) via transformers — not a second engine
        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor  # type: ignore

            hf_id = CLIP_MODEL_ID
            proc = CLIPProcessor.from_pretrained(hf_id)
            model = CLIPModel.from_pretrained(hf_id)
            model = model.to(self.device)
            model.eval()
            self._model = model
            self._preprocess = proc
            self._tokenizer = proc
            self._impl = "transformers"
            self.model_id = f"transformers:{hf_id}"
            self.dim = int(model.config.projection_dim)
            self._load_sec = round(time.perf_counter() - t0, 3)
            self._from_cache = False
            _CLIP_MODEL_CACHE[cache_key] = {
                "model": model,
                "preprocess": proc,
                "tokenizer": proc,
                "impl": self._impl,
                "dim": self.dim,
                "model_id": self.model_id,
            }
            return None
        except Exception as exc:
            self._error = f"{REASON_EMBEDDING_BACKEND_UNAVAILABLE}:{exc}"[:300]
            return self._error

    def embed_text(self, text: str) -> np.ndarray:
        err = self._ensure()
        if err:
            raise RuntimeError(err)
        import torch

        with torch.no_grad():
            if self._impl == CLIP_PRODUCTION_IMPL:
                tokens = self._tokenizer([text or ""])
                feats = self._model.encode_text(tokens.to(self.device))
                vec = feats.detach().float().cpu().numpy()[0]
            else:
                inputs = self._tokenizer(text=[text or ""], return_tensors="pt", padding=True)
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
                feats = self._model.get_text_features(**inputs)
                vec = feats.detach().float().cpu().numpy()[0]
        return _l2_normalize(vec)

    def embed_image(self, path: Path | str) -> np.ndarray:
        err = self._ensure()
        if err:
            raise RuntimeError(err)
        from PIL import Image
        import torch

        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(str(p))
        try:
            img = Image.open(p).convert("RGB")
        except Exception as exc:
            raise RuntimeError(f"corrupt_or_unreadable_image:{exc}") from exc
        with torch.no_grad():
            if self._impl == CLIP_PRODUCTION_IMPL:
                t = self._preprocess(img).unsqueeze(0).to(self.device)
                feats = self._model.encode_image(t)
                vec = feats.detach().float().cpu().numpy()[0]
            else:
                inputs = self._preprocess(images=img, return_tensors="pt")
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
                feats = self._model.get_image_features(**inputs)
                vec = feats.detach().float().cpu().numpy()[0]
        return _l2_normalize(vec)


def resolve_embedding_backend(
    *,
    prefer: str = "clip",
    allow_hash_fallback: bool = False,
    device: str = "cpu",
) -> tuple[Optional[EmbeddingBackend], dict[str, Any]]:
    """
    prefer=clip → ClipEmbeddingBackend.
    Hash fallback ONLY when allow_hash_fallback=True — labeled HEURISTIC_NON_SEMANTIC.
    Never promotes hash or unavailable CLIP to semantic PASS.
    """
    prefer = (prefer or "clip").strip().lower()
    if prefer in ("hash", "amp_hash", HASH_EMBED_MODEL, "heuristic"):
        be = HashEmbeddingBackend()
        return be, {
            "status": STATUS_UNKNOWN,
            "backend": be.model_id,
            "kind": HEURISTIC_NON_SEMANTIC,
            "note": "heuristic_hash_embedder_not_clip",
            "claims_semantic_truth": False,
            "semantic_pass": False,
            "embedding_dim": be.dim,
            "normalized": True,
            "device": "cpu",
            "dtype": "float32",
        }

    clip = ClipEmbeddingBackend(device=device)
    probe = clip.probe()
    if probe["available"]:
        return clip, {
            "status": "OK",
            "backend": clip.model_id,
            "kind": CLIP,
            "claims_semantic_truth": False,
            "semantic_pass": False,
            **probe,
        }

    if allow_hash_fallback:
        be = HashEmbeddingBackend()
        return be, {
            "status": STATUS_UNKNOWN,
            "backend": be.model_id,
            "kind": HEURISTIC_NON_SEMANTIC,
            "clip_probe": probe,
            "note": "hash_fallback_explicit_non_semantic",
            "reason": "CLIP_UNAVAILABLE_HASH_FALLBACK",
            "claims_semantic_truth": False,
            "semantic_pass": False,
            "embedding_dim": be.dim,
            "normalized": True,
            "device": "cpu",
            "dtype": "float32",
        }

    return None, {
        "status": STATUS_RETRIEVAL_UNAVAILABLE,
        "reason": REASON_EMBEDDING_BACKEND_UNAVAILABLE,
        "clip_probe": probe,
        "observation_status": STATUS_OBSERVATION_UNAVAILABLE,
        "claims_semantic_truth": False,
        "semantic_pass": False,
        "unknown_as_pass": False,
    }


def embedding_evidence(
    backend: EmbeddingBackend,
    *,
    vector: np.ndarray,
    source: str,
    source_path: str = "",
    source_hash: str = "",
    modality: str = "text",
) -> dict[str, Any]:
    """Normalize CLIP/hash output through AMP embedding evidence contract."""
    vec = np.asarray(vector, dtype=np.float32).reshape(-1)
    kind = str(getattr(backend, "kind", "") or "")
    is_clip = kind == CLIP
    return {
        "schema": "amp_retrieval_embedding_meta_v1",
        "backend": "clip" if is_clip else "hash",
        "model": backend.model_id,
        "model_version": backend.version,
        "embedding_dim": int(vec.shape[0]),
        "normalized": True,
        "source": source,
        "source_path": source_path,
        "source_hash": source_hash,
        "modality": modality,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "device": str(getattr(backend, "device", "cpu") or "cpu"),
        "dtype": str(getattr(backend, "dtype", "float32") or "float32"),
        "kind": kind,
        "status": "PASS" if is_clip else STATUS_UNKNOWN,
        "claims_semantic_truth": False,
        "semantic_pass": False,
        "heuristic_non_semantic": kind == HEURISTIC_NON_SEMANTIC or kind == HEURISTIC,
        "index_namespace": index_namespace_for_backend(backend),
        "vector_preview_norm": float(np.linalg.norm(vec)),
    }


def embed_asset_record(
    backend: EmbeddingBackend,
    *,
    local_path: Path | str,
    media_type: str,
    text_fallback: str = "",
) -> dict[str, Any]:
    path = Path(local_path)
    if not path.is_file():
        return {
            "ok": False,
            "status": STATUS_RETRIEVAL_UNAVAILABLE,
            "reason": "missing_local_asset",
            "claims_semantic_truth": False,
        }
    ch = content_hash_file(path)
    t0 = time.perf_counter()
    try:
        if media_type == "image" or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            vec = backend.embed_image(path)
            modality = "image"
        elif text_fallback:
            vec = backend.embed_text(text_fallback)
            modality = "text"
        else:
            try:
                vec = backend.embed_image(path)
                modality = "image"
            except Exception:
                vec = backend.embed_text(path.name)
                modality = "text"
    except Exception as exc:
        return {
            "ok": False,
            "status": STATUS_RETRIEVAL_UNAVAILABLE,
            "reason": "embedding_failed",
            "detail": str(exc)[:300],
            "claims_semantic_truth": False,
        }
    ev = embedding_evidence(
        backend,
        vector=vec,
        source="local_asset",
        source_path=str(path),
        source_hash=ch,
        modality=modality,
    )
    ev["inference_sec"] = round(time.perf_counter() - t0, 4)
    return {
        "ok": True,
        "vector": vec,
        "content_hash": ch,
        "embedding_model": backend.model_id,
        "embedding_version": backend.version,
        "embedding_kind": backend.kind,
        "dim": int(vec.shape[0]),
        "evidence": ev,
        "claims_semantic_truth": False,
    }
