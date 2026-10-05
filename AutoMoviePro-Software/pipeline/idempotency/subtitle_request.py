"""Subtitle request identity (BUILD-04E)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pipeline.idempotency.fingerprint import compute_fingerprint, hash_text

SUBTITLE_CONTRACT_VERSION = "1.0.0"
DEFAULT_SUBTITLE_PROVIDER = "subtitle_engine"
DEFAULT_SUBTITLE_MODEL = "proportional-v1"
SUBTITLE_TEMPLATE_VERSION = "1.0.0"
TIMING_MODEL = "audio_relative"


@dataclass
class SubtitleRequestSpec:
    job_id: str
    scene_id: str
    dialogue_id: str
    segment_id: str
    language: str
    localized_text: str
    audio_fingerprint: str
    audio_duration_sec: float
    subtitle_format: str = "srt"
    subtitle_template_version: str = SUBTITLE_TEMPLATE_VERSION
    timing_model: str = TIMING_MODEL
    scene_duration_sec: float = 0.0
    leading_gap_sec: float = 0.5
    trailing_gap_sec: float = 0.5
    provider: str = DEFAULT_SUBTITLE_PROVIDER
    model: str = DEFAULT_SUBTITLE_MODEL
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized_inputs(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id.strip(),
            "dialogue_id": self.dialogue_id.strip(),
            "segment_id": self.segment_id.strip(),
            "language": self.language.strip().lower()[:8],
            "localized_text_hash": hash_text(self.localized_text.strip())[:32],
            "audio_fingerprint": self.audio_fingerprint.strip(),
            "audio_duration_sec": round(float(self.audio_duration_sec), 4),
            "subtitle_format": self.subtitle_format.strip().lower(),
            "subtitle_template_version": self.subtitle_template_version.strip(),
            "timing_model": self.timing_model.strip(),
            "scene_duration_sec": round(float(self.scene_duration_sec), 4),
            "leading_gap_sec": round(float(self.leading_gap_sec), 4),
            "trailing_gap_sec": round(float(self.trailing_gap_sec), 4),
            "provider": self.provider.strip().lower(),
            "model": self.model.strip().lower(),
            "subtitle_contract_version": SUBTITLE_CONTRACT_VERSION,
        }

    def fingerprint(self) -> str:
        return compute_subtitle_fingerprint(self)

    @property
    def entity_id(self) -> str:
        seg = self.segment_id.strip()
        suffix = f"-{seg}" if seg else ""
        return f"sub-{self.scene_id}-{self.dialogue_id}{suffix}-{self.language}"


def compute_subtitle_fingerprint(spec: SubtitleRequestSpec) -> str:
    return compute_fingerprint(
        job_id=spec.job_id,
        stage="subtitle",
        entity_id=spec.entity_id,
        contract_version=SUBTITLE_CONTRACT_VERSION,
        provider=spec.provider,
        model=spec.model,
        inputs=spec.normalized_inputs(),
    )
