"""AudioPlan + request preflight — MUST run before TTS provider (AMP-004 Phase-05)."""
from __future__ import annotations

import re
from typing import Any, Optional, Sequence

from domain.scene import AudioPlan
from pipeline.audio_design.mix_policy import validate_music_vs_dialogue_priority
from pipeline.audio_design.naturalness import naturalness_preflight
from pipeline.audio_design.plan_builder import AMBIENCE_COMPAT, LOUD_AMBIENCE, QUIET_LOCATIONS, _norm
from pipeline.lang_config import TARGET_LANG_CODES


class AudioPreflightError(ValueError):
    """Deterministic-invalid audio request — must not call provider."""

    def __init__(self, message: str, *, issues: Optional[list[str]] = None) -> None:
        super().__init__(message)
        self.issues = list(issues or [])


# Canonical production languages (lang_config) + extra locale aliases.
# Prior gap: ur/ta/ml were catalog targets but missing here → scene_localize blocked.
VALID_LANGUAGES = {
    "en", "en-us", "en-gb", "bn", "bn-bd", "hi", "es", "fr", "de", "pt", "ar", "ja", "ko", "zh", "id", "tr", "ru",
} | {str(c).lower() for c in TARGET_LANG_CODES}
CALM_EMOTIONS = {"calm", "neutral", "soft", "gentle", "quiet", "serene"}
LOUD_DELIVERIES = {"screaming", "scream", "shouting", "shout", "yell", "yelling", "loud_announcement", "announce"}
WHISPER_EMOTIONS = {"whisper", "whispering", "hushed"}
LOUD_EMOTIONS = {"angry", "furious", "ecstatic", "panic"}


def _emotion_delivery_conflict(emotion: str, delivery: str) -> Optional[str]:
    e = _norm(emotion)
    d = _norm(delivery)
    if e in CALM_EMOTIONS and d in LOUD_DELIVERIES:
        return "contradictory_emotion_delivery:calm_vs_screaming"
    if e in WHISPER_EMOTIONS and d in LOUD_DELIVERIES:
        return "contradictory_emotion_delivery:whisper_vs_loud"
    if e in LOUD_EMOTIONS and d in ("whisper", "whispering", "soft"):
        return "contradictory_emotion_delivery:loud_emotion_vs_whisper"
    if "whisper" in e and "loud" in d:
        return "contradictory_emotion_delivery:whisper_vs_loud_policy"
    return None


def _ambience_location_conflict(ambience: Optional[dict[str, Any]], location: str, environment: str) -> Optional[str]:
    if not ambience:
        return None
    atype = _norm(str(ambience.get("type") or "none"))
    if atype in ("", "none"):
        return None
    loc = _norm(f"{location} {environment}")
    if atype in LOUD_AMBIENCE or atype == "crowd":
        if any(q in loc for q in QUIET_LOCATIONS) or "quiet" in loc:
            return f"contradictory_ambience:{atype}_vs_quiet_location"
    allowed = AMBIENCE_COMPAT.get(atype)
    if allowed is not None and allowed:
        # If location is known quiet/office and ambience not compatible
        loc_tokens = set(re.findall(r"[a-z_]+", loc))
        if loc_tokens and not (loc_tokens & allowed) and any(q in loc_tokens for q in QUIET_LOCATIONS):
            if atype not in ("quiet_room", "room", "office", "none"):
                return f"ambience_incompatible_with_location:{atype}"
    return None


def _sfx_unrelated(sfx: dict[str, Any], action: str, dialogue: str) -> Optional[str]:
    purpose = _norm(str(sfx.get("purpose") or ""))
    binding = _norm(str(sfx.get("event_binding") or sfx.get("action_binding") or ""))
    kind = _norm(str(sfx.get("kind") or ""))
    if not purpose and not binding:
        return "sfx_missing_purpose_binding"
    blob = _norm(f"{action} {dialogue}")
    # Unrelated: stadium cheer with no crowd/action support
    if kind in ("cheer", "applause", "laser") and kind not in blob and binding not in blob:
        if purpose not in blob:
            return f"unrelated_sfx_rejected:{kind}"
    if not binding and kind and kind not in blob and purpose not in ("scene_support",):
        # require some textual support for non-support SFX
        if purpose and purpose.replace("_", " ") not in blob and kind not in blob:
            return f"unrelated_sfx_rejected:{kind}"
    return None


def _pronunciation_malformed(items: Sequence[str]) -> Optional[str]:
    for p in items or []:
        s = (p or "").strip()
        if not s:
            return "empty_pronunciation_entry"
        if len(s) > 120:
            return "pronunciation_too_long"
        if re.search(r"[<>]|javascript:|https?://", s, re.I):
            return "malformed_pronunciation_instruction"
        if s.count("/") > 6:
            return "malformed_pronunciation_instruction"
    return None


def validate_industrial_audio_plan(
    plan: AudioPlan,
    *,
    dialogue_text: str = "",
    location: str = "",
    environment: str = "",
    primary_action: str = "",
    known_dialogue_ids: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Validate canonical AudioPlan. Returns status PASS|BLOCK|UNKNOWN + issues."""
    issues: list[str] = []
    dialogue_text = dialogue_text or str((plan.metadata or {}).get("dialogue_preview") or "")
    location = location or str((plan.metadata or {}).get("location") or "")
    environment = environment or str((plan.metadata or {}).get("environment") or "")
    primary_action = primary_action or str((plan.metadata or {}).get("primary_action") or "")

    if not (plan.dialogue_id or "").strip():
        issues.append("missing_dialogue_id")
    if not (plan.scene_id or "").strip():
        issues.append("missing_scene_id")
    if not dialogue_text.strip():
        issues.append("empty_dialogue")

    lang = _norm(plan.language or "")
    if lang and lang.split("-")[0] not in {x.split("-")[0] for x in VALID_LANGUAGES} and lang not in VALID_LANGUAGES:
        issues.append(f"invalid_language:{plan.language}")

    if plan.speaker_id is not None and not str(plan.speaker_id).strip():
        issues.append("invalid_speaker_empty")

    intensity = plan.intensity
    if intensity is not None and (intensity < 0 or intensity > 1):
        issues.append("emotion_intensity_out_of_bounds")

    conflict = _emotion_delivery_conflict(plan.emotion or "", plan.delivery_style or "")
    if conflict:
        issues.append(conflict)

    rate = plan.speech_rate if plan.speech_rate is not None else plan.speed
    if rate is not None and (rate < 0.5 or rate > 2.0):
        issues.append("invalid_speech_rate")

    if plan.duration_target_sec is not None and plan.duration_target_sec < 0:
        issues.append("invalid_timing_negative")
    if plan.duration_target_sec is not None and plan.duration_target_sec > 600:
        issues.append("invalid_timing_excessive")

    for ph in plan.pause_hints or []:
        if float(ph) < 0 or float(ph) > 30:
            issues.append("impossible_pause_hint")
            break

    pron_err = _pronunciation_malformed(plan.pronunciation or [])
    if pron_err:
        issues.append(pron_err)

    amb_err = _ambience_location_conflict(plan.ambience, location, environment)
    if amb_err:
        issues.append(amb_err)

    for sfx in plan.sfx_events or []:
        err = _sfx_unrelated(sfx, primary_action, dialogue_text)
        if err:
            issues.append(err)

    issues.extend(validate_music_vs_dialogue_priority(plan.music, plan.mix_priority or {}))

    if known_dialogue_ids is not None and plan.dialogue_id:
        ids = [str(x) for x in known_dialogue_ids]
        if ids.count(str(plan.dialogue_id)) > 1:
            issues.append("duplicate_dialogue_identity")

    nat = naturalness_preflight(dialogue_text)
    if nat["status"] == "BLOCK":
        issues.extend(nat["issues"])

    # Timing vs dialogue length heuristic
    if plan.duration_target_sec and dialogue_text:
        words = max(1, len(re.findall(r"\w+", dialogue_text)))
        # ~2.5 words/sec rough; if target << needed → invalid timing
        needed = words / 3.5
        if plan.duration_target_sec < needed * 0.35 and words > 12:
            issues.append("dialogue_timing_conflict_with_scene")

    status = "BLOCK" if issues else "PASS"
    return {
        "status": status,
        "issues": issues,
        "method": "DETERMINISTIC",
        "naturalness": nat,
        "plan_fingerprint": (plan.metadata or {}).get("plan_fingerprint") or "",
    }


def preflight_audio_request(
    *,
    dialogue_text: str,
    language: str,
    speaker_id: str = "",
    voice_id: str = "",
    emotion: str = "neutral",
    delivery_style: str = "neutral",
    intensity: float = 0.5,
    speech_rate: float = 1.0,
    pronunciation: Optional[Sequence[str]] = None,
    dialogue_id: str = "",
    scene_id: str = "",
    segment_id: str = "",
    duration_target_sec: Optional[float] = None,
    audio_plan: Optional[AudioPlan] = None,
    location: str = "",
    environment: str = "",
    primary_action: str = "",
    known_dialogue_ids: Optional[Sequence[str]] = None,
    block: bool = True,
) -> dict[str, Any]:
    """
    Cost protection: validate everything deterministic BEFORE provider call.
    Raises AudioPreflightError when block=True and status=BLOCK.
    """
    issues: list[str] = []
    text = (dialogue_text or "").strip()
    if not text:
        issues.append("empty_dialogue")

    lang = _norm(language)
    if not lang:
        issues.append("invalid_language:empty")
    elif lang.split("-")[0] not in {x.split("-")[0] for x in VALID_LANGUAGES} and lang not in VALID_LANGUAGES:
        issues.append(f"invalid_language:{language}")

    # Speaker: empty string means unspecified OK; whitespace-only invalid; explicit "invalid"/"none" blocked
    sp = (speaker_id or voice_id or "").strip()
    if speaker_id is not None and str(speaker_id) != "" and not str(speaker_id).strip():
        issues.append("invalid_speaker")
    if _norm(speaker_id) in {"invalid", "none", "null", "undefined"}:
        issues.append("invalid_speaker")

    if intensity < 0 or intensity > 1:
        issues.append("emotion_intensity_out_of_bounds")

    c = _emotion_delivery_conflict(emotion, delivery_style)
    if c:
        issues.append(c)

    if speech_rate < 0.5 or speech_rate > 2.0:
        issues.append("invalid_speech_rate")

    if duration_target_sec is not None and (duration_target_sec < 0 or duration_target_sec > 600):
        issues.append("invalid_timing")

    pe = _pronunciation_malformed(list(pronunciation or []))
    if pe:
        issues.append(pe)

    if known_dialogue_ids is not None and dialogue_id:
        if list(known_dialogue_ids).count(dialogue_id) > 1:
            issues.append("duplicate_dialogue_identity")

    nat = naturalness_preflight(text)
    if nat["status"] == "BLOCK":
        issues.extend(nat["issues"])

    plan_result = None
    if audio_plan is not None:
        plan_result = validate_industrial_audio_plan(
            audio_plan,
            dialogue_text=text,
            location=location,
            environment=environment,
            primary_action=primary_action,
            known_dialogue_ids=known_dialogue_ids,
        )
        if plan_result["status"] == "BLOCK":
            issues.extend(plan_result["issues"])

    # Dedupe issues
    uniq: list[str] = []
    for i in issues:
        if i not in uniq:
            uniq.append(i)

    result = {
        "status": "BLOCK" if uniq else "PASS",
        "issues": uniq,
        "method": "DETERMINISTIC",
        "naturalness": nat,
        "plan_validation": plan_result,
        "identity": {
            "scene_id": scene_id,
            "dialogue_id": dialogue_id,
            "segment_id": segment_id,
            "language": language,
        },
    }
    if block and result["status"] == "BLOCK":
        raise AudioPreflightError(
            f"audio_preflight_blocked:{uniq[0]}",
            issues=uniq,
        )
    return result
