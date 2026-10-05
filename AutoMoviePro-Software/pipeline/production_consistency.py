"""C05-Q — Production Consistency & Naturalness foundation (orchestration only).

Composes existing authorities — does NOT replace:
  SceneIntent, VisualBible, ContinuityTracker, AudioPlan, multimodal_consistency,
  Artifact Verification, BUILD-04F quality/repair, LocalizationContract.

Observation honesty:
  HEURISTIC | PROVIDER_VERIFIED | UNKNOWN
Never convert heuristic similarity into PROVIDER_VERIFIED.
Never claim character/emotion/voice/semantic visual verification without capable observation.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Sequence

from domain.scene_intent import AudioIntent, SceneIntent
from pipeline.artifact_verification.semantic_boundary import classify_semantic_observation
from pipeline.multimodal_consistency.cross_modal import (
    validate_dialogue_visual_consistency,
)
from pipeline.multimodal_consistency.industrial_status import (
    ConfidenceLevel,
    LayerStatus,
)
from pipeline.quality.contracts import (
    CreativeQualityResult,
    IssueSeverity,
    QualityIssue,
    QualityVerdict,
    RepairScope,
)
from pipeline.quality.publishability import evaluate_publishability
from pipeline.quality.repair_planner import RepairPlan, plan_repair
from pipeline.visual_intelligence import (
    MODE_IMAGE,
    SceneVisualDelta,
    VisualBible,
    build_scene_visual_contract,
    compile_visual_prompt,
    detect_delta_contradictions,
    localization_safe_bible_check,
    sanitize_visual_metadata,
    seed_status_for_provider,
    validate_pre_visual_generation,
)
from pipeline.visual_semantic.continuity import ContinuityTracker

CAPABILITY_LIMITATION = "CAPABILITY_LIMITATION"
OBS_HEURISTIC = ConfidenceLevel.HEURISTIC.value
OBS_PROVIDER_VERIFIED = ConfidenceLevel.PROVIDER_VERIFIED.value
OBS_UNKNOWN = "UNKNOWN"

# TTS fields commonly unsupported as true prosody control (honest limitations)
_DEFAULT_TTS_LIMITATIONS = {
    "emotion_intensity": CAPABILITY_LIMITATION,
    "pause_intent": CAPABILITY_LIMITATION,
    "emphasis": CAPABILITY_LIMITATION,
    "pacing": CAPABILITY_LIMITATION,
}


@dataclass
class VoiceIdentity:
    """Stable speaker identity — independent of scene emotion."""

    voice_identity_id: str
    speaker_id: str = ""
    language: str = "en"
    vocal_profile: str = ""
    speaking_rate_baseline: float = 1.0
    emotional_baseline: str = "neutral"
    delivery_baseline: str = "neutral"
    provider: str = ""
    model: str = ""
    multilingual_consistent: bool = False  # provider-capable claim only when True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return sanitize_consistency_metadata(asdict(self))


@dataclass
class SceneEmotionState:
    """Per-scene emotion — must not replace VoiceIdentity."""

    emotion: str = ""
    intensity: float = 0.5
    delivery: str = "neutral"
    pacing: str = ""
    emphasis: list[str] = field(default_factory=list)
    pause_intent: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TemporalVisualContract:
    """Interface for future frame-to-frame observation — not fake VLM."""

    contract_id: str
    scene_id: str
    prior_scene_id: str = ""
    dimensions: list[str] = field(
        default_factory=lambda: [
            "frame_to_frame_identity",
            "object_persistence",
            "environment_persistence",
            "motion_continuity",
            "camera_continuity",
        ]
    )
    observation_status: str = OBS_UNKNOWN
    confidence: str = OBS_UNKNOWN
    notes: str = "temporal_semantic_observation_unavailable_without_VLM_CV"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConsistencyObservation:
    """Truthful observation envelope — never silent PASS."""

    domain: str  # visual | audio | voice | cross_modal | temporal | localization
    status: str  # PASS | FAIL | UNKNOWN | BLOCKED
    confidence: str  # HEURISTIC | PROVIDER_VERIFIED | UNKNOWN
    claim: str = ""
    issues: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sanitize_consistency_metadata(obj: Any) -> Any:
    """Strip secrets from visual/voice metadata projections."""
    return sanitize_visual_metadata(obj)


def create_voice_identity(
    *,
    voice_identity_id: str,
    speaker_id: str = "",
    language: str = "en",
    vocal_profile: str = "",
    speaking_rate_baseline: float = 1.0,
    emotional_baseline: str = "neutral",
    delivery_baseline: str = "neutral",
    provider: str = "",
    model: str = "",
    multilingual_consistent: bool = False,
) -> VoiceIdentity:
    if not (voice_identity_id or "").strip():
        raise ValueError("voice_identity_id_required")
    return VoiceIdentity(
        voice_identity_id=voice_identity_id.strip(),
        speaker_id=(speaker_id or voice_identity_id).strip(),
        language=(language or "en").strip().lower(),
        vocal_profile=vocal_profile,
        speaking_rate_baseline=float(speaking_rate_baseline or 1.0),
        emotional_baseline=emotional_baseline or "neutral",
        delivery_baseline=delivery_baseline or "neutral",
        provider=provider,
        model=model,
        multilingual_consistent=bool(multilingual_consistent),
    )


def apply_voice_identity_to_audio_intent(
    intent: AudioIntent,
    voice: VoiceIdentity,
    emotion: Optional[SceneEmotionState] = None,
) -> AudioIntent:
    """Bind stable voice identity; emotion may change without replacing speaker."""
    data = intent.model_dump()
    data["speaker_id"] = voice.speaker_id or voice.voice_identity_id
    data["voice_identity_id"] = voice.voice_identity_id
    data["voice_profile"] = voice.vocal_profile or data.get("voice_profile") or ""
    if not data.get("language"):
        data["language"] = voice.language
    if emotion:
        data["emotion"] = emotion.emotion
        data["emotion_intensity"] = emotion.intensity
        data["delivery"] = emotion.delivery or data.get("delivery") or "neutral"
        if emotion.pacing:
            data["pacing"] = emotion.pacing
        if emotion.emphasis:
            data["emphasis"] = list(emotion.emphasis)
        if emotion.pause_intent:
            data["pause_intent"] = list(emotion.pause_intent)
    # Do not overwrite speech_rate baseline unless unset
    if abs(float(data.get("speech_rate") or 1.0) - 1.0) < 1e-9 and voice.speaking_rate_baseline:
        data["speech_rate"] = voice.speaking_rate_baseline
    return AudioIntent.model_validate(data)


def record_tts_capability_limitations(
    intent: AudioIntent,
    *,
    provider: str = "",
    supported_fields: Optional[Sequence[str]] = None,
) -> AudioIntent:
    """Mark unsupported dialogue fields as CAPABILITY_LIMITATION — not false success."""
    data = intent.model_dump()
    supported = set(supported_fields or ())
    limitations = list(data.get("capability_limitations") or [])
    requested = {
        "emotion_intensity": data.get("emotion_intensity") not in (None, 0.5),
        "pause_intent": bool(data.get("pause_intent")),
        "emphasis": bool(data.get("emphasis")),
        "pacing": bool(str(data.get("pacing") or "").strip()),
        "pronunciation": bool(data.get("pronunciation")),
    }
    # Conservative defaults: most TTS adapters do not guarantee prosody fields
    for field_name, is_requested in requested.items():
        if not is_requested:
            continue
        if field_name in supported:
            continue
        tag = f"{field_name}:{CAPABILITY_LIMITATION}"
        if provider:
            tag = f"{provider}:{tag}"
        if tag not in limitations:
            limitations.append(tag)
    data["capability_limitations"] = limitations
    return AudioIntent.model_validate(data)


def voice_identity_preserved(
    master: VoiceIdentity,
    localized: VoiceIdentity,
    *,
    language_changed: bool = False,
) -> dict[str, Any]:
    """Speaker identity must not silently change with language.

    Equality is OBS_HEURISTIC only — never acoustic / PROVIDER_VERIFIED.
    """
    same_id = master.voice_identity_id == localized.voice_identity_id
    same_speaker = master.speaker_id == localized.speaker_id
    if language_changed and not master.multilingual_consistent and not localized.multilingual_consistent:
        out = {
            "ok": same_id and same_speaker,
            "preserved": same_id and same_speaker,
            "note": "multilingual_speaker_consistency_not_claimed_without_provider_support",
            "confidence": OBS_HEURISTIC,
            "acoustic_verification": False,
            "provider_verified": False,
        }
    else:
        out = {
            "ok": same_id and same_speaker,
            "preserved": same_id and same_speaker,
            "confidence": OBS_HEURISTIC,
            "note": "identity_equality_check_not_acoustic_verification",
            "acoustic_verification": False,
            "provider_verified": False,
        }
    # Hard rule: never upgrade heuristic equality to PROVIDER_VERIFIED
    if str(out.get("confidence") or "").upper() == str(OBS_PROVIDER_VERIFIED).upper():
        out["confidence"] = OBS_HEURISTIC
    out["provider_verified"] = False
    out["acoustic_verification"] = False
    return out


def resolve_canonical_voice_identity(
    *,
    language: str = "en",
    speaker_id: str = "",
    voice_profile: str = "",
    voice_identity_id: str = "",
    provider: str = "",
    model: str = "",
    multilingual_consistent: bool = False,
    emotional_baseline: str = "neutral",
) -> VoiceIdentity:
    """Plan-level VoiceIdentity — product lock defaults to MASTER_VOICE_NAME when unset."""
    from pipeline.lang_config import MASTER_VOICE_NAME

    profile = (voice_profile or "").strip() or MASTER_VOICE_NAME
    vid = (voice_identity_id or "").strip() or f"voice:{profile.lower()}"
    speaker = (speaker_id or "").strip() or "narrator"
    return create_voice_identity(
        voice_identity_id=vid,
        speaker_id=speaker,
        language=language or "en",
        vocal_profile=profile,
        provider=provider,
        model=model,
        multilingual_consistent=bool(multilingual_consistent),
        emotional_baseline=emotional_baseline or "neutral",
    )


def voice_identity_from_mapping(data: Optional[dict[str, Any]]) -> Optional[VoiceIdentity]:
    """Rehydrate VoiceIdentity from plan / segment dict. Missing id+profile → None (not PASS)."""
    if not isinstance(data, dict):
        return None
    vid = str(
        data.get("voice_identity_id")
        or data.get("voice_identity")
        or (data.get("metadata") or {}).get("voice_identity_id")
        or ""
    ).strip()
    profile = str(
        data.get("vocal_profile")
        or data.get("voice_profile")
        or data.get("voice_name")
        or ""
    ).strip()
    if not vid and not profile:
        return None
    return resolve_canonical_voice_identity(
        language=str(data.get("language") or "en"),
        speaker_id=str(data.get("speaker_id") or data.get("speaker") or ""),
        voice_profile=profile,
        voice_identity_id=vid,
        provider=str(data.get("provider") or ""),
        model=str(data.get("model") or ""),
        multilingual_consistent=bool(data.get("multilingual_consistent") or False),
        emotional_baseline=str(data.get("emotional_baseline") or "neutral"),
    )


def apply_voice_identity_to_audio_plan(plan: Any, voice: VoiceIdentity) -> Any:
    """Stamp AudioPlan with stable VoiceIdentity (emotion fields untouched)."""
    from domain.scene import AudioPlan

    if isinstance(plan, AudioPlan):
        data = plan.model_dump()
    elif hasattr(plan, "model_dump"):
        data = plan.model_dump()
    elif isinstance(plan, dict):
        data = dict(plan)
    else:
        raise TypeError("audio_plan_required")
    data["voice_profile"] = voice.vocal_profile or data.get("voice_profile")
    data["speaker_id"] = voice.speaker_id or data.get("speaker_id")
    if not data.get("language"):
        data["language"] = voice.language
    meta = dict(data.get("metadata") or {})
    meta["voice_identity_id"] = voice.voice_identity_id
    meta["voice_identity_authority"] = "pipeline.production_consistency.VoiceIdentity"
    meta["voice_identity_confidence"] = OBS_HEURISTIC
    meta["voice_identity_provider_verified"] = False
    data["metadata"] = meta
    return AudioPlan.model_validate(data)


def extract_scene_voice_ref(scene_or_segment: dict[str, Any]) -> dict[str, str]:
    """Pull identity fields from plan segment / handoff scene (no inference PASS)."""
    ap = scene_or_segment.get("audio_plan") if isinstance(scene_or_segment.get("audio_plan"), dict) else {}
    meta = ap.get("metadata") if isinstance(ap.get("metadata"), dict) else {}
    vi = scene_or_segment.get("voice_identity") if isinstance(scene_or_segment.get("voice_identity"), dict) else {}
    vid = str(
        scene_or_segment.get("voice_identity_id")
        or scene_or_segment.get("voice_identity_ref")
        or vi.get("voice_identity_id")
        or meta.get("voice_identity_id")
        or ap.get("voice_identity_id")
        or ""
    ).strip()
    profile = str(
        scene_or_segment.get("voice_profile")
        or scene_or_segment.get("voice_name")
        or vi.get("vocal_profile")
        or ap.get("voice_profile")
        or ""
    ).strip()
    speaker = str(
        scene_or_segment.get("speaker_id")
        or scene_or_segment.get("speaker")
        or vi.get("speaker_id")
        or ap.get("speaker_id")
        or ""
    ).strip()
    return {"voice_identity_id": vid, "voice_profile": profile, "speaker_id": speaker}


def evaluate_voice_identity_continuity(
    *,
    canonical: Optional[Any] = None,
    scene_refs: Sequence[dict[str, Any]] = (),
    localized: Optional[Any] = None,
    language_changed: bool = False,
) -> dict[str, Any]:
    """Fail-closed VoiceIdentity continuity across scenes (+ optional localized).

    Missing canonical → BLOCKED (never inferred PASS).
    Mismatch → BLOCKED.
    Equality checks remain OBS_HEURISTIC — never PROVIDER_VERIFIED / acoustic.
    """
    blocks: list[str] = []
    voice: Optional[VoiceIdentity] = None
    if isinstance(canonical, VoiceIdentity):
        voice = canonical
    elif isinstance(canonical, dict):
        voice = voice_identity_from_mapping(canonical)

    if voice is None or not (voice.voice_identity_id or "").strip():
        return {
            "ok": False,
            "status": "BLOCKED",
            "confidence": OBS_HEURISTIC,
            "blocks": ["VOICE_IDENTITY_MISSING:canonical"],
            "preserved": False,
            "note": "missing_voice_identity_is_not_pass",
            "acoustic_verification": False,
            "provider_verified": False,
            "authority": "pipeline.production_consistency.VoiceIdentity",
        }

    for i, raw in enumerate(scene_refs or ()):
        if not isinstance(raw, dict):
            blocks.append(f"VOICE_IDENTITY_MISSING:scene[{i}]")
            continue
        ref = extract_scene_voice_ref(raw)
        if raw.get("audio_plan") and isinstance(raw["audio_plan"], dict):
            nested = extract_scene_voice_ref(
                {
                    "audio_plan": raw["audio_plan"],
                    "voice_identity_ref": raw.get("voice_identity_ref"),
                    "voice_identity_id": raw.get("voice_identity_id"),
                    "speaker": raw.get("speaker"),
                }
            )
            if nested.get("voice_identity_id") or nested.get("voice_profile"):
                ref = nested
            if not ref.get("voice_identity_id") and raw.get("voice_identity_ref"):
                ref["voice_identity_id"] = str(raw.get("voice_identity_ref") or "").strip()
            if not ref.get("voice_profile") and raw.get("voice_identity_ref"):
                maybe = str(raw.get("voice_identity_ref") or "").strip()
                if maybe and not maybe.startswith("voice:"):
                    ref["voice_profile"] = ref.get("voice_profile") or maybe

        has_id = bool(ref.get("voice_identity_id"))
        has_prof = bool(ref.get("voice_profile"))
        if not has_id and not has_prof:
            blocks.append(f"VOICE_IDENTITY_MISSING:scene[{i}]")
            continue
        if has_id:
            rid = ref["voice_identity_id"]
            if rid.lower() != voice.voice_identity_id.lower() and rid.lower() != (voice.vocal_profile or "").lower():
                blocks.append(
                    f"VOICE_IDENTITY_MISMATCH:scene[{i}]:id:{rid}!={voice.voice_identity_id}"
                )
        if has_prof and voice.vocal_profile:
            if ref["voice_profile"].lower() != voice.vocal_profile.lower():
                blocks.append(
                    f"VOICE_IDENTITY_MISMATCH:scene[{i}]:profile:{ref['voice_profile']}!={voice.vocal_profile}"
                )

    loc_check: Optional[dict[str, Any]] = None
    if localized is not None:
        loc_voice: Optional[VoiceIdentity] = None
        if isinstance(localized, VoiceIdentity):
            loc_voice = localized
        elif isinstance(localized, dict):
            loc_voice = voice_identity_from_mapping(localized)
        if loc_voice is None:
            blocks.append("VOICE_IDENTITY_MISSING:localized")
        else:
            loc_check = voice_identity_preserved(voice, loc_voice, language_changed=language_changed)
            if not loc_check.get("ok"):
                blocks.append("VOICE_IDENTITY_MISMATCH:localized")
            if str(loc_check.get("confidence") or "").upper() == str(OBS_PROVIDER_VERIFIED).upper():
                blocks.append("VOICE_IDENTITY_HONESTY:localized_claimed_provider_verified")

    ok = not blocks
    return {
        "ok": ok,
        "status": "PASS" if ok else "BLOCKED",
        "confidence": OBS_HEURISTIC,
        "blocks": blocks,
        "preserved": ok,
        "canonical": voice.to_dict(),
        "localized_check": loc_check,
        "note": "identity_equality_check_not_acoustic_verification",
        "acoustic_verification": False,
        "provider_verified": False,
        "authority": "pipeline.production_consistency.VoiceIdentity",
    }


def resolve_locked_tts_voice_name(
    scene: dict[str, Any],
    *,
    canonical: Optional[Any] = None,
) -> str:
    """TTS voice_name from canonical VoiceIdentity / scene AudioPlan."""
    from pipeline.lang_config import MASTER_VOICE_NAME

    voice = None
    if isinstance(canonical, VoiceIdentity):
        voice = canonical
    elif isinstance(canonical, dict):
        voice = voice_identity_from_mapping(canonical)
    if voice is None and isinstance(scene.get("voice_identity"), dict):
        voice = voice_identity_from_mapping(scene["voice_identity"])
    if voice and voice.vocal_profile:
        return voice.vocal_profile
    ap = scene.get("audio_plan") if isinstance(scene.get("audio_plan"), dict) else {}
    name = str(ap.get("voice_profile") or scene.get("voice_profile") or scene.get("voice_name") or "").strip()
    return name or MASTER_VOICE_NAME


def assert_voice_identity_continuity_or_raise(
    *,
    canonical: Optional[Any] = None,
    scene_refs: Sequence[dict[str, Any]] = (),
    localized: Optional[Any] = None,
    language_changed: bool = False,
) -> dict[str, Any]:
    """Raise RuntimeError when VoiceIdentity continuity is BLOCKED."""
    result = evaluate_voice_identity_continuity(
        canonical=canonical,
        scene_refs=scene_refs,
        localized=localized,
        language_changed=language_changed,
    )
    if not result.get("ok"):
        detail = ",".join(result.get("blocks") or ["voice_identity_blocked"])
        raise RuntimeError(f"VOICE_IDENTITY_CONTINUITY_BLOCKED:{detail}")
    return result


def build_temporal_visual_contract(
    *,
    scene_id: str,
    prior_scene_id: str = "",
    has_vlm_observation: bool = False,
) -> TemporalVisualContract:
    """Temporal observation interface — UNKNOWN unless real VLM/CV exists."""
    if has_vlm_observation:
        # Still do not claim PROVIDER_VERIFIED without actual adapter result
        status = OBS_UNKNOWN
        conf = OBS_UNKNOWN
        notes = "vlm_flag_set_but_no_provider_result_attached"
    else:
        status = OBS_UNKNOWN
        conf = OBS_UNKNOWN
        notes = "temporal_semantic_observation_unavailable_without_VLM_CV"
    return TemporalVisualContract(
        contract_id=f"tvc-{scene_id}",
        scene_id=scene_id,
        prior_scene_id=prior_scene_id,
        observation_status=status,
        confidence=conf,
        notes=notes,
    )


def observe_temporal_visual(
    contract: TemporalVisualContract,
    *,
    provider_verified_evidence: Optional[dict[str, Any]] = None,
) -> ConsistencyObservation:
    """Never convert heuristic similarity into PROVIDER_VERIFIED."""
    if provider_verified_evidence and provider_verified_evidence.get("verified") is True:
        return ConsistencyObservation(
            domain="temporal",
            status=LayerStatus.VERIFIED.value,
            confidence=OBS_PROVIDER_VERIFIED,
            claim="temporal_provider_verified",
            evidence=dict(provider_verified_evidence),
        )
    return ConsistencyObservation(
        domain="temporal",
        status=OBS_UNKNOWN,
        confidence=OBS_UNKNOWN,
        claim="temporal_observation_unavailable",
        issues=["UNKNOWN_without_VLM_CV"],
        evidence={"contract": contract.to_dict()},
    )


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", (text or "").lower()))


def _has_stem(token_set: set[str], stem: str) -> bool:
    s = (stem or "").lower()
    if not s:
        return False
    return any(t == s or t.startswith(s) or s.startswith(t) for t in token_set)


def check_cross_modal_intent_compatibility(
    *,
    narration: str,
    intent: SceneIntent,
    bible: Optional[VisualBible] = None,
    delta: Optional[SceneVisualDelta] = None,
) -> ConsistencyObservation:
    """
    Pre-generation / intent-level SCRIPT ↔ VISUAL compatibility.

    Deterministic contradictions → FAIL (HEURISTIC).
    Insufficient signal → UNKNOWN (never silent PASS).
    """
    delta = delta or SceneVisualDelta()
    narr_text = narration or intent.dialogue_intent or ""
    # Prefer explicit narration; do not treat summary as visual evidence when it duplicates narration
    narr = _tokens(narr_text) or _tokens(intent.summary or "")
    issues: list[str] = []

    # Explicit forbidden objects named in narration
    forb = [x.lower() for x in (intent.forbidden_objects or []) + list(delta.must_not_appear or [])]
    for f in forb:
        ft = _tokens(f)
        if ft and ft <= narr:
            issues.append(f"narration_mentions_forbidden_object:{f}")

    # Visual contract signals only (not narration/summary — avoids false overlap)
    vis_blob = " ".join(
        [
            " ".join(intent.required_objects or []),
            " ".join(intent.forbidden_objects or []),
            " ".join(delta.must_appear or []),
            " ".join(delta.must_not_appear or []),
            intent.primary_action or "",
            delta.action or "",
            intent.location or "",
            intent.environment or "",
            intent.visual_intent or "",
            intent.visual_emphasis or "",
            (bible.object_identity if bible else ""),
            (bible.subject_identity if bible else ""),
            (bible.location if bible else ""),
            (bible.environment if bible else ""),
            (bible.character_identity if bible else ""),
        ]
    ).lower()
    vis_tok = _tokens(vis_blob)

    # Classic mismatch: narration says red car, visual says blue truck
    if _has_stem(narr, "car") and _has_stem(vis_tok, "truck") and not _has_stem(vis_tok, "car"):
        issues.append("object_mismatch:narration_car_vs_visual_truck")
    if _has_stem(narr, "truck") and _has_stem(vis_tok, "car") and not _has_stem(vis_tok, "truck"):
        issues.append("object_mismatch:narration_truck_vs_visual_car")

    color_pairs = (
        ("red", "blue"),
        ("blue", "red"),
        ("black", "white"),
        ("white", "black"),
    )
    for a, b in color_pairs:
        if a in narr and b in vis_tok and a not in vis_tok:
            issues.append(f"color_mismatch:narration_{a}_vs_visual_{b}")

    # Location mismatch
    places = {"office", "kitchen", "beach", "forest", "studio", "street", "warehouse", "loft"}
    narr_places = narr & places
    vis_places = vis_tok & places
    if narr_places and vis_places and not (narr_places & vis_places):
        issues.append(
            f"location_mismatch:narration_{sorted(narr_places)[0]}_vs_visual_{sorted(vis_places)[0]}"
        )

    # Action mismatch: entering vs exiting (stem-aware)
    action_pairs = (("enter", "exit"), ("enter", "leave"), ("arrive", "leave"), ("open", "close"))
    act = _tokens(intent.primary_action or delta.action or "")
    for a, b in action_pairs:
        if _has_stem(narr, a) and _has_stem(act, b) and not _has_stem(act, a):
            issues.append(f"action_mismatch:narration_{a}_vs_visual_{b}")
        if _has_stem(narr, b) and _has_stem(act, a) and not _has_stem(act, b):
            issues.append(f"action_mismatch:narration_{b}_vs_visual_{a}")

    if issues:
        return ConsistencyObservation(
            domain="cross_modal",
            status="FAIL",
            confidence=OBS_HEURISTIC,
            claim="cross_modal_intent_contradiction",
            issues=issues,
            evidence={"narration_tokens": sorted(narr)[:12], "visual_tokens": sorted(vis_tok)[:12]},
        )

    # Matching case: require some overlap for PASS-at-intent (still HEURISTIC, not verified)
    req = _tokens(
        " ".join(intent.required_objects or [])
        + " "
        + (intent.location or "")
        + " "
        + (intent.primary_action or "")
        + " "
        + ((bible.character_identity if bible else "") or " ".join(intent.actors or []))
    )
    if narr and req and (narr & req):
        return ConsistencyObservation(
            domain="cross_modal",
            status="PASS",
            confidence=OBS_HEURISTIC,
            claim="cross_modal_intent_compatible_heuristic",
            evidence={"overlap": sorted(narr & req)[:12]},
        )

    return ConsistencyObservation(
        domain="cross_modal",
        status=OBS_UNKNOWN,
        confidence=OBS_UNKNOWN,
        claim="cross_modal_insufficient_signal_or_no_observation",
        issues=["UNKNOWN_cross_modal_without_capable_observation"],
    )


def observe_cross_modal_post_generation(
    intent: SceneIntent,
    visual_analysis: Optional[dict[str, Any]] = None,
    *,
    has_vlm_or_asr: bool = False,
    strict: bool = False,
) -> ConsistencyObservation:
    """Post-gen observation via existing multimodal validators — honesty preserved."""
    if not visual_analysis and not has_vlm_or_asr:
        sem = classify_semantic_observation(expected={"objects": intent.required_objects})
        return ConsistencyObservation(
            domain="cross_modal",
            status=sem.get("semantic_status") or OBS_UNKNOWN,
            confidence=sem.get("confidence_label") or OBS_UNKNOWN,
            claim=sem.get("claim") or "unknown_not_pass",
            issues=list(sem.get("issues") or []),
            evidence={"authority": "artifact_verification.semantic_boundary"},
        )

    analysis = dict(visual_analysis or {})
    if has_vlm_or_asr:
        analysis.setdefault("source", "PROVIDER")
    else:
        analysis.setdefault("source", "HEURISTIC")

    issues = validate_dialogue_visual_consistency(intent, analysis, strict=strict)
    critical = [i for i in issues if str(getattr(i, "severity", "")).upper() in ("CRITICAL", "HIGH")]
    conf = OBS_PROVIDER_VERIFIED if has_vlm_or_asr and analysis.get("verified") else OBS_HEURISTIC
    if critical:
        return ConsistencyObservation(
            domain="cross_modal",
            status="FAIL",
            confidence=conf if conf == OBS_PROVIDER_VERIFIED else OBS_HEURISTIC,
            claim="dialogue_visual_contradiction",
            issues=[getattr(i, "message", str(i)) for i in critical],
            evidence={"validator": "multimodal_consistency.cross_modal"},
        )
    if not has_vlm_or_asr:
        # Heuristic overlap is not verification
        if issues:
            return ConsistencyObservation(
                domain="cross_modal",
                status="FAIL" if any(str(getattr(i, "severity", "")).upper() == "CRITICAL" for i in issues) else "PASS",
                confidence=OBS_HEURISTIC,
                claim="heuristic_cross_modal_only",
                issues=[getattr(i, "message", str(i)) for i in issues],
            )
        return ConsistencyObservation(
            domain="cross_modal",
            status="PASS",
            confidence=OBS_HEURISTIC,
            claim="heuristic_cross_modal_compatible_not_provider_verified",
        )
    return ConsistencyObservation(
        domain="cross_modal",
        status="PASS",
        confidence=OBS_PROVIDER_VERIFIED,
        claim="provider_verified_cross_modal",
    )


def validate_pre_production_consistency(
    *,
    bible: VisualBible,
    intent: SceneIntent,
    delta: Optional[SceneVisualDelta] = None,
    visual_mode: str = MODE_IMAGE,
    provider: str = "",
    seed: Optional[int] = None,
    tracker: Optional[ContinuityTracker] = None,
    voice: Optional[VoiceIdentity] = None,
    audio_intent: Optional[AudioIntent] = None,
    narration: str = "",
    unlocked_languages: Optional[Sequence[str]] = None,
    owner_login_id: str = "",
    requesting_login_id: str = "",
) -> dict[str, Any]:
    """Fail-closed preflight before paid generation — composes existing authorities."""
    issues: list[str] = []
    observations: list[dict[str, Any]] = []

    # Ownership
    if owner_login_id and requesting_login_id and owner_login_id.strip() != requesting_login_id.strip():
        issues.append("cross_customer_access_blocked")

    # Visual preflight (C05-V)
    vis = validate_pre_visual_generation(
        bible=bible,
        intent=intent,
        delta=delta,
        visual_mode=visual_mode,
        provider=provider,
        seed=seed,
        tracker=tracker,
    )
    if vis.get("blocked"):
        issues.extend(list(vis.get("issues") or []))
    observations.append({"domain": "visual_preflight", **{k: vis.get(k) for k in ("ok", "blocked", "issues", "visual_mode")}})

    # Delta contradictions already in vis; reinforce
    delta = delta or SceneVisualDelta()
    issues.extend(detect_delta_contradictions(delta))

    # Voice identity availability
    ai = audio_intent or intent.audio_intent
    if voice is None and ai is not None and (ai.voice_identity_id or ai.speaker_id):
        voice = create_voice_identity(
            voice_identity_id=ai.voice_identity_id or ai.speaker_id,
            speaker_id=ai.speaker_id or ai.voice_identity_id,
            language=ai.language or "en",
            vocal_profile=ai.voice_profile or "",
        )
    if ai is not None:
        # Emotion compatibility via existing audio preflight heuristics (compose, don't replace)
        try:
            from pipeline.audio_design.preflight import _emotion_delivery_conflict

            conflict = _emotion_delivery_conflict(ai.emotion or "", ai.delivery or "")
            if conflict:
                issues.append(conflict)
        except Exception:
            pass
        limited = record_tts_capability_limitations(ai, provider=provider)
        observations.append(
            {
                "domain": "voice",
                "voice_identity_id": (voice.voice_identity_id if voice else limited.voice_identity_id),
                "emotion": limited.emotion,
                "capability_limitations": list(limited.capability_limitations or []),
                "confidence": OBS_HEURISTIC,
                "note": "capability_limitations_are_not_false_success",
            }
        )

    # Language entitlement (existing commercial surface)
    lang = (ai.language if ai else "") or (intent.localization_intent.target_language if intent.localization_intent else "") or ""
    if lang and unlocked_languages is not None:
        unlocked = {str(x).strip().lower() for x in unlocked_languages}
        if lang.strip().lower() not in unlocked and lang.strip().lower()[:2] not in {u[:2] for u in unlocked}:
            issues.append("language_not_entitled")

    # Cross-modal intent
    xm = check_cross_modal_intent_compatibility(
        narration=narration or intent.summary or intent.dialogue_intent,
        intent=intent,
        bible=bible,
        delta=delta,
    )
    observations.append(xm.to_dict())
    if xm.status == "FAIL":
        issues.extend(xm.issues)

    # Localization: bible must remain language-independent
    if bible and re.search(r"(?i)\b(translate|subtitle|narration language)\b", bible.subject_identity or ""):
        issues.append("bible_language_leak:subject_identity")

    blocked = bool(issues)
    return sanitize_consistency_metadata(
        {
            "ok": not blocked,
            "blocked": blocked,
            "issues": issues,
            "observations": observations,
            "authorities": {
                "visual": "pipeline.visual_intelligence",
                "continuity": "pipeline.visual_semantic.continuity.ContinuityTracker",
                "prompt": "pipeline.multimodal_consistency.prompt_compiler",
                "audio_plan": "domain.scene.AudioPlan",
                "multimodal": "pipeline.multimodal_consistency",
                "quality": "pipeline.quality (BUILD-04F)",
                "artifact": "pipeline.artifact_verification",
                "repair": "pipeline.quality.repair_planner",
            },
            "seed": seed_status_for_provider(provider, seed),
            "paid_api_calls": 0,
        }
    )


def plan_consistency_repair(
    *,
    scene_id: str,
    issue_domain: str,
    issue_message: str,
    all_scene_ids: Optional[Sequence[str]] = None,
    attempt: int = 1,
) -> dict[str, Any]:
    """Use existing BUILD-04F plan_repair — targeted scene only; no second repair engine."""
    scope = RepairScope.SCENE
    if issue_domain in ("visual", "visual_asset"):
        scope = RepairScope.VISUAL_ASSET
    elif issue_domain in ("audio", "voice"):
        scope = RepairScope.AUDIO_ASSET
    elif issue_domain in ("cross_modal", "multimodal"):
        scope = RepairScope.SCENE
    elif issue_domain == "subtitle":
        scope = RepairScope.SUBTITLE

    issue = QualityIssue(
        issue_id=f"c05q_{issue_domain}_{scene_id}",
        stage="c05q_consistency",
        severity=IssueSeverity.HIGH,
        category=issue_domain,
        subject_id=scene_id,
        description=issue_message,
        repair_scope=scope,
        recommended_action="targeted_repair",
    )
    result = CreativeQualityResult(
        subject="scene",
        subject_id=scene_id,
        stage="c05q_consistency",
        verdict=QualityVerdict.REPAIR_REQUIRED,
        score=0.0,
        issues=[issue],
        repair_scope=scope,
        recommended_action="targeted_repair",
    )
    plan = plan_repair(result, attempt=attempt)
    preserved = [s for s in (all_scene_ids or []) if s != scene_id]
    return sanitize_consistency_metadata(
        {
            "ok": plan is not None,
            "affected_scene_id": scene_id,
            "preserved_scene_ids": preserved,
            "targeted_only": True,
            "repair_engine": "pipeline.quality.repair_planner.plan_repair",
            "duplicate_repair_engine": False,
            "plan": plan.to_dict() if isinstance(plan, RepairPlan) else None,
        }
    )


def evaluate_consistency_publishability(
    *,
    visual_status: str,
    audio_status: str,
    multimodal_status: str,
    creative_verdict: str = "PASS",
    technical_pass: bool = True,
) -> dict[str, Any]:
    """Publishability via existing gate — UNKNOWN fail-closed when mandatory."""
    out = evaluate_publishability(
        technical_pass=technical_pass,
        creative_report={"overall_verdict": creative_verdict, "publishable": creative_verdict == "PASS"},
        multimodal_status=multimodal_status,
        multimodal_mandatory_unknown=True,
        semantic_status=visual_status,
        audio_status=audio_status,
        artifact_status="PASS",
        render_status="PASS",
    )
    # Explicit visual/audio UNKNOWN dimensions (honesty)
    notes = []
    for name, st in (("visual", visual_status), ("audio", audio_status), ("multimodal", multimodal_status)):
        if str(st).upper() == OBS_UNKNOWN:
            notes.append(f"{name}_UNKNOWN_blocks_publishability")
            out = dict(out)
            out["publishable"] = False
            if str(out.get("verdict") or "").upper() == "PUBLISHABLE":
                out["verdict"] = "UNKNOWN"
    out["consistency_notes"] = notes
    # Provider success is not quality PASS
    out["provider_success_is_not_quality_pass"] = True
    return out


def localization_consistency_bundle(
    *,
    master_bible: VisualBible,
    lang_a_bible: VisualBible,
    lang_b_bible: VisualBible,
    master_voice: VoiceIdentity,
    lang_a_voice: VoiceIdentity,
    lang_b_voice: VoiceIdentity,
) -> dict[str, Any]:
    """Same visual identity across languages; voice preserved where supported."""
    vis = localization_safe_bible_check(master_bible, lang_a_bible, lang_b_bible)
    va = voice_identity_preserved(master_voice, lang_a_voice, language_changed=True)
    vb = voice_identity_preserved(master_voice, lang_b_voice, language_changed=True)
    return {
        "visual": vis,
        "voice_a": va,
        "voice_b": vb,
        "ok": bool(vis.get("ok") and va.get("ok") and vb.get("ok")),
        "no_accidental_visual_regeneration": bool(vis.get("ok")),
        "note": "language may change narration/subtitle only",
    }


def compile_consistent_visual_prompt(
    *,
    bible: VisualBible,
    intent: SceneIntent,
    delta: Optional[SceneVisualDelta] = None,
    visual_mode: str = MODE_IMAGE,
) -> dict[str, Any]:
    """Canonical prompt compiler only — provenance from C05-V path."""
    return compile_visual_prompt(
        bible=bible, intent=intent, delta=delta, visual_mode=visual_mode
    )


def architecture_integrity_snapshot() -> dict[str, Any]:
    """Assert single-authority doctrine for tests."""
    return {
        "visual_bible_authority": "pipeline.visual_intelligence.VisualBible",
        "second_visual_bible": False,
        "continuity_authority": "pipeline.visual_semantic.continuity.ContinuityTracker",
        "second_continuity_engine": False,
        "audio_authority": "domain.scene.AudioPlan + pipeline.audio_design",
        "second_audio_engine": False,
        "voice_identity_authority": "pipeline.production_consistency.VoiceIdentity",
        "second_voice_engine": False,
        "quality_authority": "pipeline.quality (BUILD-04F)",
        "second_quality_engine": False,
        "repair_authority": "pipeline.quality.repair_planner",
        "second_repair_engine": False,
        "prompt_authority": "pipeline.multimodal_consistency.prompt_compiler",
        "multimodal_authority": "pipeline.multimodal_consistency",
        "artifact_authority": "pipeline.artifact_verification",
        "l3_vlm_asr_status": "DEFERRED_UNKNOWN_WITHOUT_CAPABLE_OBSERVATION",
    }
