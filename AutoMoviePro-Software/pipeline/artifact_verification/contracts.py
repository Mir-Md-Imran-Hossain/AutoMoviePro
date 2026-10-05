"""Canonical artifact observation contract (AMP-004 Phase-04).

Distinguishes INTENT / PROMPT / PROVIDER / OBSERVED / COMPOSITE.
Does not claim semantic correctness from metadata alone.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class MediaType(str, Enum):
    VIDEO = "VIDEO"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    SUBTITLE = "SUBTITLE"
    COMPOSITE = "COMPOSITE"
    THUMBNAIL = "THUMBNAIL"
    UNKNOWN = "UNKNOWN"


class ObservationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class ObservationMethod(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    HEURISTIC = "HEURISTIC"
    PROVIDER_CLAIM = "PROVIDER_CLAIM"
    METADATA_ONLY = "METADATA_ONLY"
    UNAVAILABLE = "UNAVAILABLE"


class VerificationTier(str, Enum):
    L0 = "L0"  # file/format/container
    L1 = "L1"  # technical media
    L2 = "L2"  # deterministic relationship
    L3 = "L3"  # heuristic semantic
    L4 = "L4"  # future VLM/ASR — never claim without evidence


@dataclass
class ArtifactObservation:
    artifact_id: str
    job_id: str = ""
    scene_id: str = ""
    dialogue_id: str = ""
    segment_id: str = ""
    revision_id: str = ""
    media_type: MediaType = MediaType.UNKNOWN
    layer: str = "C"  # A|B|C|D|E
    source_intent_fingerprint: str = ""
    prompt_fingerprint: str = ""
    artifact_fingerprint: str = ""
    observation_time: str = ""
    path: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    frame_count: int = 0
    audio_streams: int = 0
    video_streams: int = 0
    subtitle_streams: int = 0
    sample_rate: int = 0
    channels: int = 0
    observation_method: ObservationMethod = ObservationMethod.DETERMINISTIC
    observation_status: ObservationStatus = ObservationStatus.UNKNOWN
    verification_tier: VerificationTier = VerificationTier.L0
    technical_status: ObservationStatus = ObservationStatus.UNKNOWN
    semantic_status: ObservationStatus = ObservationStatus.UNKNOWN
    issues: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence_label: str = "STRUCTURAL_ONLY"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["media_type"] = self.media_type.value
        d["observation_method"] = self.observation_method.value
        d["observation_status"] = self.observation_status.value
        d["verification_tier"] = self.verification_tier.value
        d["technical_status"] = self.technical_status.value
        d["semantic_status"] = self.semantic_status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactObservation":
        return cls(
            artifact_id=str(data.get("artifact_id") or ""),
            job_id=str(data.get("job_id") or ""),
            scene_id=str(data.get("scene_id") or ""),
            dialogue_id=str(data.get("dialogue_id") or ""),
            segment_id=str(data.get("segment_id") or ""),
            revision_id=str(data.get("revision_id") or ""),
            media_type=MediaType(str(data.get("media_type") or "UNKNOWN")),
            layer=str(data.get("layer") or "C"),
            source_intent_fingerprint=str(data.get("source_intent_fingerprint") or ""),
            prompt_fingerprint=str(data.get("prompt_fingerprint") or ""),
            artifact_fingerprint=str(data.get("artifact_fingerprint") or ""),
            observation_time=str(data.get("observation_time") or ""),
            path=str(data.get("path") or ""),
            duration=float(data.get("duration") or 0.0),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            fps=float(data.get("fps") or 0.0),
            frame_count=int(data.get("frame_count") or 0),
            audio_streams=int(data.get("audio_streams") or 0),
            video_streams=int(data.get("video_streams") or 0),
            subtitle_streams=int(data.get("subtitle_streams") or 0),
            sample_rate=int(data.get("sample_rate") or 0),
            channels=int(data.get("channels") or 0),
            observation_method=ObservationMethod(
                str(data.get("observation_method") or ObservationMethod.DETERMINISTIC.value)
            ),
            observation_status=ObservationStatus(
                str(data.get("observation_status") or ObservationStatus.UNKNOWN.value)
            ),
            verification_tier=VerificationTier(str(data.get("verification_tier") or "L0")),
            technical_status=ObservationStatus(
                str(data.get("technical_status") or ObservationStatus.UNKNOWN.value)
            ),
            semantic_status=ObservationStatus(
                str(data.get("semantic_status") or ObservationStatus.UNKNOWN.value)
            ),
            issues=list(data.get("issues") or []),
            evidence=dict(data.get("evidence") or {}),
            confidence_label=str(data.get("confidence_label") or "STRUCTURAL_ONLY"),
        )


def combine_status(technical: ObservationStatus, semantic: ObservationStatus) -> ObservationStatus:
    """
    Technical FAIL → FAIL.
    Semantic FAIL → FAIL.
    Technical PASS does NOT imply semantic PASS — if semantic UNKNOWN, overall
    observation_status for the *technical* claim may still be PASS while
    semantic_status remains UNKNOWN (honest split). Overall gate uses technical
    for artifact_status and keeps semantic nested.
    """
    if technical == ObservationStatus.FAIL or semantic == ObservationStatus.FAIL:
        return ObservationStatus.FAIL
    if technical == ObservationStatus.UNKNOWN:
        return ObservationStatus.UNKNOWN
    return ObservationStatus.PASS
