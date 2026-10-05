"""Quality dimension weights and thresholds (BUILD-04F)."""
from __future__ import annotations

from pipeline.quality.contracts import QualityDimension, IssueSeverity

# Weights sum to 1.0 — used for aggregate score only; CRITICAL issues can block regardless.
DIMENSION_WEIGHTS: dict[str, float] = {
    QualityDimension.CONTENT_RELEVANCE.value: 0.07,
    QualityDimension.FACTUAL_COHERENCE.value: 0.09,
    QualityDimension.SCRIPT_STRUCTURE.value: 0.05,
    QualityDimension.HOOK_STRENGTH.value: 0.07,
    QualityDimension.RETENTION_STRUCTURE.value: 0.05,
    QualityDimension.DIALOGUE_NATURALNESS.value: 0.07,
    QualityDimension.SCENE_COHERENCE.value: 0.05,
    QualityDimension.VISUAL_DIALOGUE_ALIGNMENT.value: 0.09,
    QualityDimension.VISUAL_QUALITY.value: 0.05,
    QualityDimension.VISUAL_CONTINUITY.value: 0.04,
    QualityDimension.AUDIO_QUALITY.value: 0.05,
    QualityDimension.VOICE_CONSISTENCY.value: 0.04,
    QualityDimension.EMOTION_ALIGNMENT.value: 0.04,
    QualityDimension.PACING.value: 0.05,
    QualityDimension.SUBTITLE_ALIGNMENT.value: 0.04,
    QualityDimension.TIMING.value: 0.03,
    QualityDimension.TECHNICAL_MEDIA_QUALITY.value: 0.05,
    QualityDimension.CROSS_MODAL_CONSISTENCY.value: 0.05,
    QualityDimension.FINAL_VIDEO_COHERENCE.value: 0.02,
}

PASS_SCORE_THRESHOLD = 0.72
REPAIR_SCORE_THRESHOLD = 0.55

# Blocking: CRITICAL severity always forces non-PASS regardless of score.
BLOCKING_SEVERITIES = {IssueSeverity.CRITICAL}

# Dialogue duration target window (seconds) — short-form spoken beats.
DEFAULT_MIN_DIALOGUE_SEC = 7.0
DEFAULT_MAX_DIALOGUE_SEC = 9.0

# Repair budgets
DEFAULT_MAX_SCENE_REPAIRS = 3
DEFAULT_MAX_SCRIPT_REPAIRS = 2
DEFAULT_MAX_REPAIR_ATTEMPTS = 3
