"""Canonical frame evidence contract — aligned to existing PASS/FAIL/UNKNOWN/ABSENT."""
from __future__ import annotations

import time
from typing import Any, Optional

from pipeline.observation.common import (
    SCHEMA_FRAME_EVIDENCE,
    STATUS_ABSENT,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNKNOWN,
    STATUS_UNAVAILABLE,
)
from pipeline.retrieval.common import strip_secrets

SCHEMA_VERSION = "amp_frame_evidence_v1"


def empty_frame_evidence(
    *,
    asset_id: str = "",
    scene_id: str = "",
    beat_id: str = "",
    timestamp: float = 0.0,
    frame_path: str = "",
    status: str = STATUS_UNKNOWN,
    provider: str = "",
    evidence_source: str = "unobserved",
    reason: str = "",
) -> dict[str, Any]:
    st = str(status or STATUS_UNKNOWN).upper()
    if st not in (STATUS_PASS, STATUS_FAIL, STATUS_UNKNOWN, STATUS_ABSENT, STATUS_UNAVAILABLE):
        st = STATUS_UNKNOWN
    return strip_secrets(
        {
            "schema": SCHEMA_FRAME_EVIDENCE,
            "schema_version": SCHEMA_VERSION,
            "asset_id": asset_id,
            "scene_id": scene_id,
            "beat_id": beat_id,
            "timestamp": float(timestamp),
            "frame_path": frame_path,
            "frame_reference": frame_path,
            "observation_status": st,
            "provider": provider,
            "observed_subjects": [],
            "observed_entities": [],
            "observed_relationships": [],
            "observed_location": "",
            "observed_actions": [],
            "observed_environment": "",
            "camera_observation": "",
            "lighting_observation": "",
            "confidence": STATUS_UNKNOWN,
            "evidence_source": evidence_source,
            "provider_verified": False,
            "heuristic": False,
            "clip_similarity_is_not_visual_truth": True,
            "filename_match_is_not_observation": True,
            "unknown_as_pass": False,
            "reason": reason,
            "created_at": time.time(),
        }
    )


def normalize_observation_status(status: str) -> str:
    st = str(status or STATUS_UNKNOWN).upper()
    if st in (STATUS_PASS, STATUS_FAIL, STATUS_UNKNOWN, STATUS_ABSENT, STATUS_UNAVAILABLE):
        return st
    return STATUS_UNKNOWN
