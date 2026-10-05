"""Source adapters — AMP-owned; no OpenMontage AGPL imports."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

from pipeline.retrieval.common import (
    STATUS_RETRIEVAL_UNAVAILABLE,
    asset_metadata,
    content_hash_file,
    content_hash_text,
    strip_secrets,
)

logger = logging.getLogger(__name__)


class StockSource(Protocol):
    name: str

    def search(self, query: str, *, media_type: str = "image", limit: int = 8) -> dict[str, Any]: ...


class LocalCorpusSource:
    """Scan a customer-scoped local folder of licensed/free assets."""

    name = "local_licensed"

    def __init__(self, root: Path | str, *, customer_id: str = "", channel_id: str = "") -> None:
        self.root = Path(root)
        self.customer_id = customer_id
        self.channel_id = channel_id

    def search(self, query: str, *, media_type: str = "image", limit: int = 8) -> dict[str, Any]:
        if not self.root.exists():
            return {
                "status": STATUS_RETRIEVAL_UNAVAILABLE,
                "reason": "local_corpus_missing",
                "candidates": [],
                "source": self.name,
            }
        exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"} if media_type == "image" else {".mp4", ".mov", ".webm", ".mkv"}
        qtok = set((query or "").lower().replace("_", " ").split())
        hits: list[dict[str, Any]] = []
        for p in sorted(self.root.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in exts:
                continue
            name_l = p.stem.lower().replace("_", " ")
            if qtok:
                score = len(qtok & set(name_l.split())) / max(1, len(qtok))
                path_l = str(p).lower()
                if score <= 0 and query.lower() not in name_l and query.lower() not in path_l:
                    if not any(t in name_l or t in path_l for t in qtok if len(t) >= 4):
                        continue
            else:
                score = 0.0
            try:
                ch = content_hash_file(p)
            except OSError:
                continue
            aid = f"local:{ch[:16]}"
            meta = asset_metadata(
                asset_id=aid,
                source=self.name,
                source_url="",
                local_path=str(p),
                media_type="image" if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"} else "video",
                content_hash=ch,
                license_usage="customer_local_licensed_or_owned",
                embedding_model="",
                embedding_version="",
                extra={
                    "customer_id": self.customer_id,
                    "channel_id": self.channel_id,
                    "caption": name_l,
                    "title": p.stem,
                    "path_score": score,
                },
            )
            hits.append({"asset": meta, "semantic_score": score, "semantic_kind": "HEURISTIC"})
            if len(hits) >= limit:
                break
        return {
            "status": "OK",
            "source": self.name,
            "candidates": hits,
            "activated": True,
            "terms_verified": True,
            "note": "local_folder_only",
        }


class PexelsSource:
    """AMP-owned Pexels adapter wrapping existing fetch_pexels_videos — metadata only until download.

    Does not activate if API key absent. Does not import OpenMontage.
    """

    name = "pexels"
    LICENSE = "Pexels License (verify current terms at pexels.com/license)"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = (api_key or "").strip()

    def search(self, query: str, *, media_type: str = "video", limit: int = 8) -> dict[str, Any]:
        if not self.api_key:
            return {
                "status": STATUS_RETRIEVAL_UNAVAILABLE,
                "reason": "pexels_api_key_missing",
                "candidates": [],
                "source": self.name,
                "activated": False,
                "terms_verified": False,
            }
        # Image endpoint not previously first-party; Phase 6B activates video via existing helper.
        # Image search requires verified AMP-owned HTTP — implement minimal image search here.
        try:
            if media_type == "image":
                return self._search_images(query, limit=limit)
            return self._search_videos(query, limit=limit)
        except Exception as exc:
            logger.warning("pexels search failed: %s", exc)
            return {
                "status": STATUS_RETRIEVAL_UNAVAILABLE,
                "reason": "pexels_request_failed",
                "detail": str(exc)[:200],
                "candidates": [],
                "source": self.name,
                "activated": True,
            }

    def _search_videos(self, query: str, *, limit: int) -> dict[str, Any]:
        from pipeline.ai_providers import fetch_pexels_videos

        urls = fetch_pexels_videos(self.api_key, query, per_page=limit)
        cands = []
        for i, url in enumerate(urls or []):
            ch = content_hash_text(url)
            meta = asset_metadata(
                asset_id=f"pexels:vid:{ch[:16]}",
                source=self.name,
                source_url=url,
                local_path="",
                media_type="video",
                content_hash=ch,
                license_usage=self.LICENSE,
                extra={"caption": query, "title": query, "rank": i},
            )
            cands.append({"asset": meta, "semantic_score": max(0.1, 1.0 - i * 0.05), "semantic_kind": "HEURISTIC"})
        return {
            "status": "OK",
            "source": self.name,
            "candidates": cands,
            "activated": True,
            "terms_verified": True,
            "note": "urls_only_until_download; provenance retained",
            "retrieved_at": time.time(),
        }

    def _search_images(self, query: str, *, limit: int) -> dict[str, Any]:
        import httpx

        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                "https://api.pexels.com/v1/search",
                params={"query": query, "per_page": limit},
                headers={"Authorization": self.api_key},
            )
            r.raise_for_status()
            data = r.json()
        cands = []
        for i, photo in enumerate(data.get("photos") or []):
            src = (photo.get("src") or {})
            url = str(src.get("large") or src.get("original") or src.get("medium") or "")
            if not url:
                continue
            ch = content_hash_text(url)
            meta = asset_metadata(
                asset_id=f"pexels:img:{ch[:16]}",
                source=self.name,
                source_url=url,
                local_path="",
                media_type="image",
                width=int(photo.get("width") or 0),
                height=int(photo.get("height") or 0),
                content_hash=ch,
                license_usage=self.LICENSE,
                extra={
                    "caption": str(photo.get("alt") or query),
                    "title": str(photo.get("alt") or query),
                    "photographer": str(photo.get("photographer") or ""),
                    "rank": i,
                },
            )
            cands.append({"asset": strip_secrets(meta), "semantic_score": max(0.1, 1.0 - i * 0.05), "semantic_kind": "HEURISTIC"})
        return {
            "status": "OK",
            "source": self.name,
            "candidates": cands,
            "activated": True,
            "terms_verified": True,
            "retrieved_at": time.time(),
        }


class UnverifiedSourceStub:
    """Sources whose ToS cannot be verified are NOT activated."""

    def __init__(self, name: str) -> None:
        self.name = name

    def search(self, query: str, *, media_type: str = "image", limit: int = 8) -> dict[str, Any]:
        return {
            "status": STATUS_RETRIEVAL_UNAVAILABLE,
            "reason": "source_terms_unverified",
            "source": self.name,
            "activated": False,
            "candidates": [],
            "note": "Phase 6B refuses to activate unverified production sources",
        }


def list_production_sources() -> list[dict[str, Any]]:
    return [
        {"name": "local_licensed", "activated": True, "terms_verified": True},
        {"name": "pexels", "activated": True, "terms_verified": True, "requires": "PEXELS_API_KEY"},
        {"name": "openmontage_stock_adapters", "activated": False, "terms_verified": False, "reason": "AGPL_isolation"},
        {"name": "archive_org", "activated": False, "terms_verified": False, "reason": "terms_not_verified_in_amp"},
        {"name": "unsplash", "activated": False, "terms_verified": False, "reason": "terms_not_verified_in_amp"},
    ]
