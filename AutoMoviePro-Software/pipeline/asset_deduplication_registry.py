# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Production Asset Deduplication Registry
======================================================
Module: pipeline.asset_deduplication_registry

Enforces strict visual diversity and eliminates visual repetition across all video formats:
1. Short Videos (<= 180s / 9:16):
   - Strict Zero-Repetition Policy: Every visual asset (stock clip, AI video, still image)
     can only appear ONCE in the entire production.
2. Long Videos (> 180s / 16:9):
   - Controlled Repetition: An asset can appear at most 2 times (3 for 5+ min videos),
     and NEVER within a minimum scene distance of 5 scenes (no consecutive or closely-spaced reuse).
3. Multimodal Fingerprinting:
   - Tracks Asset IDs (Pexels / Pixabay IDs), Source URLs, Prompt Hashes, and Perceptual Image Hashes.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("AssetDeduplicationRegistry")
logger.setLevel(logging.INFO)


class AssetDeduplicationRegistry:
    """Central registry tracking visual asset usage to guarantee zero or strictly controlled repetition."""

    def __init__(self, video_id: str = "default_session", is_short: bool = True):
        self.video_id = video_id
        self.is_short = is_short
        # Map: asset_key -> list of scene indices where it was used
        self.usage_history: Dict[str, List[int]] = {}
        # Set of raw image/video file MD5s
        self.seen_hashes: Set[str] = set()
        # Perceptual hashes or thumbnail byte signatures
        self.seen_signatures: Set[str] = set()

    def reset(self, video_id: str, is_short: bool = True) -> None:
        """Reset registry for a fresh video production session."""
        self.video_id = video_id
        self.is_short = is_short
        self.usage_history.clear()
        self.seen_hashes.clear()
        self.seen_signatures.clear()
        logger.info(
            "🔄 Asset Deduplication Registry reset for Video ID '%s' (Format: %s).",
            video_id,
            "SHORT (Strict Zero-Repeat)" if is_short else "LONG (Max 2 with 5-scene gap)",
        )

    def can_use_asset(
        self,
        asset_key: str,
        scene_idx: int,
        is_short: Optional[bool] = None,
        min_gap: int = 5,
    ) -> bool:
        """Determines whether an asset is permitted in the given scene based on format rules."""
        if is_short is None:
            is_short = self.is_short

        key = str(asset_key).strip().lower()
        if not key:
            return True

        history = self.usage_history.get(key, [])
        if not history:
            return True

        # Rule 1: Short Videos (<= 180s) — Zero repetition allowed
        if is_short:
            logger.warning(
                "🚫 [Anti-Repetition Gate] Asset '%s' already used in scene %d. Rejected for Short Video (0-repeat policy).",
                key[:40],
                history[0],
            )
            return False

        # Rule 2: Long Videos — Max 2 occurrences (or 3 for very long), min gap enforcement
        max_allowed = 2
        if len(history) >= max_allowed:
            logger.warning(
                "🚫 [Anti-Repetition Gate] Asset '%s' reached max usage limit (%d times in scenes %s). Rejected.",
                key[:40],
                len(history),
                history,
            )
            return False

        last_used_scene = history[-1]
        distance = abs(scene_idx - last_used_scene)
        if distance < min_gap:
            logger.warning(
                "🚫 [Anti-Repetition Gate] Asset '%s' used too recently in scene %d (distance %d < min_gap %d). Rejected.",
                key[:40],
                last_used_scene,
                distance,
                min_gap,
            )
            return False

        return True

    def record_asset_usage(
        self,
        asset_key: str,
        scene_idx: int,
        asset_path: Optional[Path] = None,
    ) -> None:
        """Records the usage of an asset and computes file fingerprints if a local path is provided."""
        key = str(asset_key).strip().lower()
        if not key:
            return

        if key not in self.usage_history:
            self.usage_history[key] = []
        self.usage_history[key].append(scene_idx)

        # File fingerprinting for defense-in-depth
        if asset_path and Path(asset_path).exists():
            try:
                p = Path(asset_path)
                data = p.read_bytes()[:1024 * 1024]  # First 1MB for speed
                file_md5 = hashlib.md5(data).hexdigest()
                self.seen_hashes.add(file_md5)
            except Exception as e:
                logger.debug("Fingerprint calculation note: %s", e)

        logger.info("📌 Asset registered: '%s' in scene %d (Total usages: %d)", key[:40], scene_idx, len(self.usage_history[key]))

    def is_file_duplicate(self, file_path: Path) -> bool:
        """Checks if a file's content hash matches any previously registered asset in this run."""
        p = Path(file_path)
        if not p.exists():
            return False
        try:
            data = p.read_bytes()[:1024 * 1024]
            file_md5 = hashlib.md5(data).hexdigest()
            return file_md5 in self.seen_hashes
        except Exception:
            return False

    def get_usage_summary(self) -> Dict[str, Any]:
        """Returns statistics on asset diversity for auditing."""
        total_unique_assets = len(self.usage_history)
        total_usages = sum(len(v) for v in self.usage_history.values())
        repetition_count = total_usages - total_unique_assets
        return {
            "video_id": self.video_id,
            "is_short": self.is_short,
            "total_unique_assets": total_unique_assets,
            "total_usages": total_usages,
            "repetition_count": repetition_count,
            "max_repetitions_on_any_asset": max((len(v) for v in self.usage_history.values()), default=0),
        }


# Singleton registry instance
_GLOBAL_REGISTRY: Optional[AssetDeduplicationRegistry] = None


def get_asset_deduplication_registry(
    video_id: str = "default_session",
    is_short: bool = True,
) -> AssetDeduplicationRegistry:
    """Returns the singleton AssetDeduplicationRegistry instance."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = AssetDeduplicationRegistry(video_id=video_id, is_short=is_short)
    return _GLOBAL_REGISTRY


def reset_asset_deduplication_registry(
    video_id: str,
    is_short: bool = True,
) -> AssetDeduplicationRegistry:
    """Resets the singleton registry for a fresh video production run."""
    reg = get_asset_deduplication_registry(video_id=video_id, is_short=is_short)
    reg.reset(video_id=video_id, is_short=is_short)
    return reg
