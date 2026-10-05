"""Observation adapters — evidence only; never publish/repair/approve."""
from __future__ import annotations

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_UNAVAILABLE = "OBSERVATION_UNAVAILABLE"

SCHEMA_SPEECH = "amp_observation_speech_timing_v1"
SCHEMA_SCENE = "amp_observation_scene_boundary_v1"
SCHEMA_VMAF = "amp_observation_perceptual_quality_v1"
SCHEMA_FRAME_SAMPLE = "amp_observation_frame_sampling_v1"
SCHEMA_FRAME_EVIDENCE = "amp_observation_frame_evidence_v1"
SCHEMA_TEMPORAL = "amp_observation_temporal_evidence_v1"
SCHEMA_BEAT_COVERAGE = "amp_observation_beat_frame_coverage_v1"
SCHEMA_AUDIO = "amp_observation_audio_evidence_v1"

# Align with semantic / publishability — do not invent new statuses
STATUS_ABSENT = "ABSENT"  # missing mandatory evidence at publishability boundary


def unavailable(
    *,
    schema: str,
    tool: str,
    reason: str,
    detail: str = "",
) -> dict:
    return {
        "schema": schema,
        "status": STATUS_UNAVAILABLE,
        "observation_executed": False,
        "provider_verified": False,
        "tool": tool,
        "reason": reason,
        "detail": (detail or "")[:400],
        "issues": [f"observation_unavailable:{reason}"],
        "unknown_as_pass": False,
        "authority": "observation_only",
        "creates_final_gate": False,
        "creates_render_engine": False,
    }
