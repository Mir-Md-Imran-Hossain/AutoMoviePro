"""Audio/TTS request identity (BUILD-04B)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from pipeline.idempotency.fingerprint import compute_fingerprint, hash_text


@dataclass
class AudioRequestSpec:
    job_id: str
    scene_id: int
    dialogue_id: str
    audio_plan_id: str
    dialogue_text: str
    language: str
    provider: str
    model: str
    voice_profile: str = ""
    voice_id: str = ""
    emotion: str = "neutral"
    delivery_style: str = "neutral"
    emotion_intensity: float = 0.5
    speaking_speed: float = 1.0
    output_format: str = "m4a"
    audio_plan_version: str = "1.1.0"
    audio_plan_fingerprint: str = ""
    part_index: int = 0
    segment_id: str = ""
    revision_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized_inputs(self) -> dict[str, Any]:
        return {
            "scene_id": int(self.scene_id),
            "dialogue_id": self.dialogue_id.strip(),
            "audio_plan_id": self.audio_plan_id.strip(),
            "audio_plan_fingerprint": self.audio_plan_fingerprint.strip(),
            "segment_id": self.segment_id.strip(),
            "revision_id": self.revision_id.strip(),
            "part_index": int(self.part_index),
            "dialogue_text": self.dialogue_text.strip(),
            "language": self.language.strip().lower(),
            "provider": self.provider.strip().lower(),
            "model": self.model.strip().lower(),
            "voice_profile": self.voice_profile.strip(),
            "voice_id": self.voice_id.strip(),
            "emotion": self.emotion.strip().lower(),
            "delivery_style": self.delivery_style.strip().lower(),
            "emotion_intensity": round(float(self.emotion_intensity), 4),
            "speaking_speed": round(float(self.speaking_speed), 4),
            "output_format": self.output_format.strip().lower(),
            "audio_plan_version": self.audio_plan_version.strip(),
        }

    def fingerprint(self) -> str:
        return compute_audio_fingerprint(self)

    @property
    def dialogue_hash(self) -> str:
        return hash_text(self.dialogue_text.strip())

    @property
    def entity_id(self) -> str:
        seg = self.segment_id.strip() or (f"p{self.part_index}" if self.part_index else "")
        suffix = f"-{seg}" if seg else ""
        return f"scene-{self.scene_id:02d}-{self.dialogue_id}{suffix}"


def compute_audio_fingerprint(spec: AudioRequestSpec) -> str:
    return compute_fingerprint(
        job_id=spec.job_id,
        stage="audio",
        entity_id=spec.entity_id,
        provider=spec.provider,
        model=spec.model,
        inputs=spec.normalized_inputs(),
    )
