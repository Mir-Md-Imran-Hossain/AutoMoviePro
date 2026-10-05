"""FAISS index with deterministic metadata mapping — AMP-owned, no OpenMontage."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

from pipeline.retrieval.common import (
    SCHEMA_INDEX,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_RETRIEVAL_UNAVAILABLE,
    content_hash_text,
    read_json,
    strip_secrets,
    write_json,
)

logger = logging.getLogger(__name__)


class FaissAssetIndex:
    """
    Flat IP FAISS index (vectors L2-normalized → cosine via inner product).
    Metadata rows aligned 1:1 with vector ids. Duplicate content_hash skipped.
    """

    def __init__(
        self,
        root: Path | str,
        *,
        embedding_model: str,
        embedding_version: str,
        dim: int,
        customer_id: str = "",
        channel_id: str = "",
        index_version: str = "faiss_flat_ip_v1",
    ) -> None:
        self.root = Path(root)
        self.embedding_model = embedding_model
        self.embedding_version = embedding_version
        self.dim = int(dim)
        self.customer_id = customer_id
        self.channel_id = channel_id
        self.index_version = index_version
        self.root.mkdir(parents=True, exist_ok=True)
        self._index = None
        self._meta: list[dict[str, Any]] = []
        self._hash_to_id: dict[str, int] = {}
        self._corrupt_reason = ""

    @property
    def index_path(self) -> Path:
        return self.root / "vectors.faiss"

    @property
    def meta_path(self) -> Path:
        return self.root / "metadata.json"

    def _faiss(self):
        try:
            import faiss  # type: ignore

            return faiss
        except Exception as exc:
            raise RuntimeError(f"faiss_unavailable:{exc}") from exc

    def _new_index(self):
        faiss = self._faiss()
        return faiss.IndexFlatIP(self.dim)

    def load(self) -> dict[str, Any]:
        if not self.meta_path.exists() and not self.index_path.exists():
            self._index = self._new_index()
            self._meta = []
            self._hash_to_id = {}
            return {"status": STATUS_PASS, "empty": True, "count": 0}
        try:
            meta_doc = read_json(self.meta_path)
            if meta_doc.get("embedding_model") != self.embedding_model:
                self._corrupt_reason = "embedding_model_mismatch"
                return {
                    "status": STATUS_FAIL,
                    "reason": self._corrupt_reason,
                    "detail": f"{meta_doc.get('embedding_model')}!={self.embedding_model}",
                }
            if int(meta_doc.get("dim") or 0) != self.dim:
                self._corrupt_reason = "dim_mismatch"
                return {"status": STATUS_FAIL, "reason": self._corrupt_reason}
            if meta_doc.get("customer_id") and self.customer_id and meta_doc["customer_id"] != self.customer_id:
                self._corrupt_reason = "customer_isolation_mismatch"
                return {"status": STATUS_FAIL, "reason": self._corrupt_reason}
            self._meta = list(meta_doc.get("assets") or [])
            self._hash_to_id = {
                str(a.get("content_hash")): int(a["vector_id"])
                for a in self._meta
                if a.get("content_hash") is not None and "vector_id" in a
            }
            faiss = self._faiss()
            if not self.index_path.exists():
                self._corrupt_reason = "missing_index_file"
                return {"status": STATUS_FAIL, "reason": self._corrupt_reason}
            self._index = faiss.read_index(str(self.index_path))
            if self._index.ntotal != len(self._meta):
                self._corrupt_reason = "index_meta_count_mismatch"
                return {
                    "status": STATUS_FAIL,
                    "reason": self._corrupt_reason,
                    "index_ntotal": int(self._index.ntotal),
                    "meta_count": len(self._meta),
                }
            return {"status": STATUS_PASS, "count": len(self._meta), "empty": len(self._meta) == 0}
        except Exception as exc:
            self._corrupt_reason = "index_corrupt_or_unreadable"
            logger.warning("faiss load failed: %s", exc)
            return {
                "status": STATUS_FAIL,
                "reason": self._corrupt_reason,
                "detail": str(exc)[:300],
            }

    def rebuild(self, vectors: list[np.ndarray], metas: list[dict[str, Any]]) -> dict[str, Any]:
        if len(vectors) != len(metas):
            return {"status": STATUS_FAIL, "reason": "rebuild_length_mismatch"}
        self._index = self._new_index()
        self._meta = []
        self._hash_to_id = {}
        self._corrupt_reason = ""
        for vec, meta in zip(vectors, metas):
            self.add_vector(vec, meta, persist=False)
        return self.persist()

    def add_vector(
        self,
        vector: np.ndarray,
        meta: dict[str, Any],
        *,
        persist: bool = True,
    ) -> dict[str, Any]:
        if self._corrupt_reason:
            return {
                "status": STATUS_FAIL,
                "reason": self._corrupt_reason,
                "added": False,
            }
        if self._index is None:
            loaded = self.load()
            if loaded.get("status") == STATUS_FAIL:
                return {**loaded, "added": False}
        assert self._index is not None
        ch = str(meta.get("content_hash") or "")
        if ch and ch in self._hash_to_id:
            return {
                "status": STATUS_PASS,
                "added": False,
                "duplicate": True,
                "vector_id": self._hash_to_id[ch],
                "reason": "duplicate_content_hash",
            }
        vec = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        if vec.shape[1] != self.dim:
            return {"status": STATUS_FAIL, "reason": "dim_mismatch", "added": False}
        vid = int(self._index.ntotal)
        self._index.add(vec)
        row = strip_secrets(dict(meta))
        row["vector_id"] = vid
        row["indexed_at"] = time.time()
        self._meta.append(row)
        if ch:
            self._hash_to_id[ch] = vid
        if persist:
            self.persist()
        return {"status": STATUS_PASS, "added": True, "duplicate": False, "vector_id": vid}

    def persist(self) -> dict[str, Any]:
        if self._index is None:
            return {"status": STATUS_FAIL, "reason": "no_index"}
        try:
            faiss = self._faiss()
            faiss.write_index(self._index, str(self.index_path))
            doc = {
                "schema": SCHEMA_INDEX,
                "index_version": self.index_version,
                "embedding_model": self.embedding_model,
                "embedding_version": self.embedding_version,
                "dim": self.dim,
                "customer_id": self.customer_id,
                "channel_id": self.channel_id,
                "count": len(self._meta),
                "assets": self._meta,
                "updated_at": time.time(),
                "fingerprint": content_hash_text(
                    f"{self.embedding_model}|{self.embedding_version}|{len(self._meta)}"
                ),
            }
            write_json(self.meta_path, doc)
            return {"status": STATUS_PASS, "count": len(self._meta), "path": str(self.root)}
        except Exception as exc:
            return {"status": STATUS_FAIL, "reason": "persist_failed", "detail": str(exc)[:300]}

    def search(self, query_vec: np.ndarray, *, top_k: int = 8) -> dict[str, Any]:
        if self._corrupt_reason:
            return {
                "status": STATUS_FAIL,
                "reason": self._corrupt_reason,
                "hits": [],
            }
        if self._index is None:
            loaded = self.load()
            if loaded.get("status") == STATUS_FAIL:
                return {**loaded, "hits": []}
        assert self._index is not None
        if self._index.ntotal == 0:
            return {"status": STATUS_PASS, "hits": [], "empty": True}
        q = np.asarray(query_vec, dtype=np.float32).reshape(1, -1)
        if q.shape[1] != self.dim:
            return {"status": STATUS_FAIL, "reason": "query_dim_mismatch", "hits": []}
        k = max(1, min(int(top_k), int(self._index.ntotal)))
        scores, ids = self._index.search(q, k)
        hits = []
        for score, vid in zip(scores[0].tolist(), ids[0].tolist()):
            if vid < 0 or vid >= len(self._meta):
                continue
            hits.append(
                {
                    "vector_id": int(vid),
                    "semantic_score": float(score),
                    "asset": dict(self._meta[vid]),
                }
            )
        return {"status": STATUS_PASS, "hits": hits, "count": len(hits)}

    def corrupt_for_test(self) -> None:
        """Test helper: break meta/index alignment deliberately."""
        if self.meta_path.exists():
            doc = read_json(self.meta_path)
            doc["assets"] = (doc.get("assets") or []) + [{"vector_id": 999999, "content_hash": "corrupt"}]
            write_json(self.meta_path, doc)


def faiss_available() -> dict[str, Any]:
    try:
        import faiss  # type: ignore

        return {"available": True, "version": getattr(faiss, "__version__", "unknown")}
    except Exception as exc:
        return {
            "available": False,
            "status": STATUS_RETRIEVAL_UNAVAILABLE,
            "reason": "faiss_unavailable",
            "detail": str(exc)[:200],
        }
