"""Industrial audio & sound design — AMP-004 Phase-05.

Prevention-first AudioPlan preflight before TTS provider.
Does NOT create a second idempotency, repair, quality, or continuity engine.
"""
from __future__ import annotations

from pipeline.audio_design.preflight import (
    AudioPreflightError,
    preflight_audio_request,
    validate_industrial_audio_plan,
)
from pipeline.audio_design.plan_builder import build_industrial_audio_plan, audio_plan_fingerprint
from pipeline.audio_design.production import (
    apply_production_audio_design,
    run_production_audio_design_gate,
)
from pipeline.audio_design.mix_policy import MixPolicy, default_mix_policy, ducking_gain_db
from pipeline.audio_design.gate import AUDIO_DESIGN_GATE_FILE, load_audio_design_gate

__all__ = [
    "AudioPreflightError",
    "preflight_audio_request",
    "validate_industrial_audio_plan",
    "build_industrial_audio_plan",
    "audio_plan_fingerprint",
    "apply_production_audio_design",
    "run_production_audio_design_gate",
    "MixPolicy",
    "default_mix_policy",
    "ducking_gain_db",
    "AUDIO_DESIGN_GATE_FILE",
    "load_audio_design_gate",
]
