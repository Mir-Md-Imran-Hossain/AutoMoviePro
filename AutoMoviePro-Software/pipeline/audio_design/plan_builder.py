"""Canonical industrial AudioPlan builder from SceneIntent / handoff (AMP-004 P05)."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional

from domain.scene import AudioPlan
from domain.scene_intent import SceneIntent


# Ambience types compatible with location keywords
AMBIENCE_COMPAT = {
    "office": {"office", "room", "indoor", "studio", "quiet_room"},
    "room": {"office", "room", "indoor", "home", "studio", "quiet_room"},
    "quiet_room": {"office", "room", "indoor", "home", "studio", "quiet_room"},
    "street": {"street", "city", "outdoor", "road"},
    "forest": {"forest", "woods", "nature", "outdoor"},
    "vehicle": {"vehicle", "car", "bus", "train", "cabin"},
    "crowd": {"crowd", "stadium", "market", "rally"},
    "rain": {"rain", "storm", "outdoor", "wet"},
    "wind": {"wind", "outdoor", "cliff", "shore"},
    "none": set(),
}

LOUD_AMBIENCE = {"crowd", "stadium", "rally"}
QUIET_LOCATIONS = {"office", "room", "quiet_room", "indoor", "studio", "home", "library"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def audio_plan_fingerprint(plan: AudioPlan | dict[str, Any]) -> str:
    if isinstance(plan, AudioPlan):
        data = plan.model_dump() if hasattr(plan, "model_dump") else plan.dict()
    else:
        data = dict(plan)
    # Stable subset affecting generation
    keys = (
        "scene_id",
        "dialogue_id",
        "segment_id",
        "revision_id",
        "language",
        "speaker_id",
        "emotion",
        "intensity",
        "delivery_style",
        "speech_rate",
        "pronunciation",
        "ambience",
        "sfx_events",
        "music",
        "ducking",
        "mix_priority",
        "loudness_policy",
        "duration_target_sec",
    )
    payload = {k: data.get(k) for k in keys}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _infer_ambience(location: str, environment: str) -> Optional[dict[str, Any]]:
    blob = f"{location} {environment}".lower()
    if not blob.strip():
        return None
    for key in ("office", "forest", "street", "vehicle", "crowd", "rain", "wind", "room"):
        if key in blob:
            return {"type": key if key != "room" else "quiet_room", "intensity": 0.25, "purpose": "scene_support"}
    if any(q in blob for q in QUIET_LOCATIONS):
        return {"type": "quiet_room", "intensity": 0.15, "purpose": "scene_support"}
    return {"type": "none", "intensity": 0.0, "purpose": "none"}


def _infer_sfx_from_action(action: str, dialogue: str) -> list[dict[str, Any]]:
    """Purposeful SFX only — bound to explicit action/event language."""
    text = f"{action} {dialogue}".lower()
    events: list[dict[str, Any]] = []
    rules = [
        (r"\b(door\s+(closes|close|opens|open)|closes?\s+the\s+door)\b", "door", "door_action"),
        (r"\b(places?|puts?|sets?)\b.*\b(on\s+(the\s+)?table|on\s+(the\s+)?desk)\b", "placement", "object_placement"),
        (r"\b(explosion|explodes|blast)\b", "impact", "impact_event"),
        (r"\b(footsteps?|walks?\s+away|walking)\b", "footsteps", "movement"),
        (r"\b(phone\s+(rings|buzzes)|notification)\b", "notification", "device_alert"),
    ]
    for pat, kind, purpose in rules:
        if re.search(pat, text):
            events.append(
                {
                    "sfx_id": f"sfx-{kind}",
                    "kind": kind,
                    "purpose": purpose,
                    "event_binding": kind,
                    "action_binding": action or dialogue[:80],
                    "timing": "on_action",
                    "duration_sec": 0.4,
                    "priority": 2,
                    "intensity": 0.5,
                }
            )
    return events


def build_industrial_audio_plan(
    *,
    scene_id: str,
    dialogue_id: str,
    dialogue_text: str,
    language: str = "en",
    speaker_id: str = "",
    voice_profile: str = "",
    emotion: str = "neutral",
    intensity: float = 0.5,
    delivery_style: str = "neutral",
    speech_rate: float = 1.0,
    location: str = "",
    environment: str = "",
    primary_action: str = "",
    duration_target_sec: Optional[float] = None,
    segment_id: str = "",
    revision_id: str = "",
    pronunciation: Optional[list[str]] = None,
    ambience: Optional[dict[str, Any]] = None,
    sfx_events: Optional[list[dict[str, Any]]] = None,
    music: Optional[dict[str, Any]] = None,
    intent: Optional[SceneIntent] = None,
) -> AudioPlan:
    """Build canonical AudioPlan. SceneIntent remains semantic source when provided."""
    if intent is not None:
        scene_id = intent.scene_id or scene_id
        dialogue_id = intent.dialogue_id or dialogue_id
        location = location or intent.location
        environment = environment or intent.environment
        primary_action = primary_action or intent.primary_action
        emotion = emotion or intent.emotional_intent or (intent.audio_intent.emotion if intent.audio_intent else "") or emotion
        if intent.audio_intent:
            language = intent.audio_intent.language or language
            delivery_style = intent.audio_intent.delivery or delivery_style
            speech_rate = float(intent.audio_intent.speech_rate or speech_rate)
            intensity = float(intent.audio_intent.emotion_intensity or intensity)
            if intent.audio_intent.ambience_type and not ambience:
                ambience = {"type": intent.audio_intent.ambience_type, "intensity": 0.25, "purpose": "scene_support"}
            if intent.audio_intent.music_mood and not music:
                music = {
                    "mood": intent.audio_intent.music_mood,
                    "energy": 0.3,
                    "purpose": "support",
                    "priority": 4,
                    "ducking": "under_dialogue",
                }
            duration_target_sec = duration_target_sec or intent.audio_intent.duration_target_sec
            pronunciation = pronunciation or list(intent.audio_intent.pronunciation or [])
        revision_id = revision_id or intent.revision_id

    if ambience is None:
        ambience = _infer_ambience(location, environment)
    if sfx_events is None:
        sfx_events = _infer_sfx_from_action(primary_action, dialogue_text)

    # Default music: low-priority support only when mood implied; never equal to dialogue
    if music is None and emotion and emotion.lower() not in ("", "neutral"):
        music = {
            "mood": emotion.lower(),
            "energy": min(0.4, float(intensity or 0.5)),
            "purpose": "support",
            "priority": 4,
            "ducking": "under_dialogue",
            "start_behavior": "fade_in",
            "end_behavior": "fade_out",
        }

    ducking = {
        "policy": "dialogue_primary_v1",
        "when_dialogue_active_db": -12.0,
        "recovery_db": 0.0,
        "attack_ms": 50,
        "release_ms": 200,
    }

    plan = AudioPlan(
        scene_id=str(scene_id),
        dialogue_id=str(dialogue_id),
        segment_id=segment_id or None,
        revision_id=revision_id or None,
        language=language or "en",
        speaker_id=speaker_id or None,
        voice_profile=voice_profile or None,
        emotion=(emotion or "neutral"),
        intensity=float(intensity if intensity is not None else 0.5),
        delivery_style=delivery_style or "neutral",
        speech_rate=float(speech_rate or 1.0),
        speed=float(speech_rate or 1.0),
        pronunciation=list(pronunciation or []),
        ambience=ambience,
        sfx_events=list(sfx_events or []),
        music=music,
        ducking=ducking,
        mix_priority={"dialogue": 1, "sfx": 2, "ambience": 3, "music": 4},
        loudness_policy="dialogue_primary_v1",
        duration_target_sec=duration_target_sec,
        metadata={
            "plan_fingerprint": "",
            "location": location,
            "environment": environment,
            "primary_action": primary_action,
            "dialogue_preview": (dialogue_text or "")[:120],
        },
    )
    fp = audio_plan_fingerprint(plan)
    meta = dict(plan.metadata or {})
    meta["plan_fingerprint"] = fp
    plan.metadata = meta
    return plan
