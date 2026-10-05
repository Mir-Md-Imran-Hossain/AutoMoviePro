"""C05-GP — Generation payload & provider routing (composition only).

Extends existing VisualRequestSpec / GenerationMode / Agnes bridge / harden.
Does NOT create a second prompt compiler, continuity, or provider orchestration engine.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Sequence

from pipeline.idempotency.visual_request import GenerationMode, VisualRequestSpec
from pipeline.visual_intelligence import (
    MODE_IMAGE,
    MODE_IMAGE_WITH_MOTION,
    MODE_VIDEO,
    SUPPORTED_VISUAL_MODES,
    map_mode_to_generation_mode,
)

# Provider route labels (adapter selection — not a new engine)
ROUTE_IMAGE = "IMAGE_PROVIDER"
ROUTE_IMAGE_WITH_MOTION = "IMAGE_WITH_MOTION_PROVIDER"
ROUTE_VIDEO = "VIDEO_PROVIDER"

PROVIDER_CAPABILITIES: dict[str, frozenset[str]] = {
    "agnes": frozenset({MODE_VIDEO, MODE_IMAGE_WITH_MOTION}),  # Agnes is video-primary
    "pollinations": frozenset({MODE_IMAGE, MODE_IMAGE_WITH_MOTION}),
    "fallback_image_video": frozenset({MODE_IMAGE, MODE_IMAGE_WITH_MOTION}),
    "mock": frozenset({MODE_IMAGE, MODE_IMAGE_WITH_MOTION, MODE_VIDEO}),
}


def _fp(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


@dataclass
class GenerationPayload:
    """Provider-neutral structured generation request (extends VisualRequestSpec identity)."""

    job_id: str = ""
    scene_id: int = 0
    dialogue_id: str = ""
    beat_id: str = ""
    canonical_scene_id: str = ""
    script_id: str = ""
    # C05-GX ownership / execution identity
    customer_id: str = ""
    channel_id: str = ""
    generation_id: str = ""
    language_entitlement: str = ""
    visual_mode: str = MODE_IMAGE
    generation_mode: str = GenerationMode.IMAGE_GENERATION.value
    canonical_prompt: str = ""
    provider_prompt: str = ""
    negative_constraints: list[str] = field(default_factory=list)
    required_entities: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    character_state: dict[str, Any] = field(default_factory=dict)
    object_state: list[str] = field(default_factory=list)
    location_identity: str = ""
    environment_state: dict[str, Any] = field(default_factory=dict)
    camera: str = ""
    framing: str = ""
    lighting: str = ""
    atmosphere: str = ""
    emotion: str = ""
    shot_purpose: str = ""
    timing: dict[str, Any] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)
    continuity_fingerprint: str = ""
    continuity_refs: dict[str, Any] = field(default_factory=dict)
    previous_beat_id: str = ""
    next_beat_id: str = ""
    transition_intent: str = ""
    visual_bible_id: str = ""
    route: str = ROUTE_IMAGE
    requested_mode: str = MODE_IMAGE
    actual_mode: str = MODE_IMAGE
    fallback_used: bool = False
    fallback_reason: str = ""
    provider_name: str = ""
    adapter: str = ""
    capability_status: str = "UNKNOWN"
    legacy_compat: bool = False
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def prompt_fingerprint(self) -> str:
        return _fp({"canonical": self.canonical_prompt, "provider": self.provider_prompt})

    @property
    def payload_fingerprint(self) -> str:
        return _fp(
            {
                "dialogue_id": self.dialogue_id,
                "beat_id": self.beat_id,
                "scene_id": self.scene_id,
                "mode": self.visual_mode,
                "canonical": self.canonical_prompt,
                "location": self.location_identity,
                "character": (self.character_state or {}).get("identity") or "",
                "rels": self.relationships,
                "coverage": self.coverage,
                "timing": self.timing,
                "continuity": self.continuity_fingerprint,
                "customer_id": self.customer_id,
                "channel_id": self.channel_id,
            }
        )

    @property
    def alignment_fingerprint(self) -> str:
        return _fp(
            {
                "dialogue_id": self.dialogue_id,
                "beat_id": self.beat_id,
                "mode": self.visual_mode,
                "location": self.location_identity,
                "character": (self.character_state or {}).get("identity") or "",
                "rels": [
                    f"{r.get('relation_type')}:{r.get('source_id')}:{r.get('target_id')}"
                    for r in (self.relationships or [])
                    if isinstance(r, dict)
                ],
                "coverage": self.coverage,
                "timing": self.timing,
                "continuity": self.continuity_fingerprint,
            }
        )


def extract_required_semantic_phrases(scene: dict[str, Any], canonical_prompt: str) -> list[str]:
    """Phrases that harden must not delete."""
    phrases: list[str] = []
    prompt_l = (canonical_prompt or "").lower()
    # Relation types that must remain distinguishable
    for r in scene.get("required_relationships") or []:
        if isinstance(r, dict):
            rt = str(r.get("relation_type") or r.get("attributes", {}).get("c05s_relation") or "").strip()
            if rt and rt.lower() in prompt_l:
                phrases.append(rt.lower())
            elif rt:
                phrases.append(rt.lower())
    for key in ("beside", "holding", "inside", "driving", "looking_at", "next_to"):
        if key.replace("_", " ") in prompt_l or key in prompt_l:
            phrases.append(key.replace("_", " ") if "_" in key else key)
    loc = str(scene.get("location") or "").strip()
    if loc:
        phrases.append(loc.lower())
    for actor in scene.get("actors") or []:
        if str(actor).strip():
            phrases.append(str(actor).strip().lower())
    subj = str(scene.get("subject") or (scene.get("character_state") or {}).get("identity") or "").strip()
    if subj:
        phrases.append(subj.lower())
    for obj in scene.get("required_objects") or []:
        if str(obj).strip():
            phrases.append(str(obj).strip().lower())
    cam = str(scene.get("camera_intent") or scene.get("camera") or "").strip()
    if cam:
        phrases.append(cam.lower())
    light = str(scene.get("lighting_intent") or scene.get("lighting") or "").strip()
    if light:
        phrases.append(light.lower())
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for p in phrases:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def harden_provider_prompt_preserving_semantics(
    canonical_prompt: str,
    *,
    scene: dict[str, Any],
    narration: str = "",
    keywords: Optional[Sequence[str]] = None,
    product_name: str = "",
    element: str = "",
    niche: str = "",
    duration_sec: float = 0.0,
    prior_issues: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Provider-safe formatting only — not a second semantic compiler."""
    from pipeline.prompt_hardening import harden_video_prompt

    required = extract_required_semantic_phrases(scene, canonical_prompt)
    mode = str(scene.get("visual_mode") or "").strip().upper()
    hardened = harden_video_prompt(
        canonical_prompt,
        narration=narration,
        keywords=list(keywords or []),
        product_name=product_name,
        element=element,
        niche=niche,
        duration_sec=duration_sec,
        prior_issues=list(prior_issues or []),
    )
    # Restore any required semantic tokens lost to truncation/injection
    restored: list[str] = []
    low = hardened.lower()
    for phrase in required:
        if phrase and phrase not in low:
            restored.append(phrase)
            hardened = hardened.rstrip() + f" SEMANTIC_LOCK: {phrase}."
            low = hardened.lower()
    # Mode must not be rewritten by harden
    if mode and f"visual_mode:{mode.lower()}" not in low and mode in SUPPORTED_VISUAL_MODES:
        hardened = hardened.rstrip() + f" VISUAL_MODE_LOCK: {mode}."
    integrity = validate_semantic_integrity(
        canonical_prompt=canonical_prompt,
        provider_prompt=hardened,
        scene=scene,
        required_phrases=required,
        visual_mode=mode,
    )
    return {
        "canonical_prompt": canonical_prompt,
        "provider_prompt": hardened,
        "required_phrases": required,
        "restored_phrases": restored,
        "integrity": integrity,
        "visual_mode": mode,
    }


def validate_semantic_integrity(
    *,
    canonical_prompt: str,
    provider_prompt: str,
    scene: dict[str, Any],
    required_phrases: Optional[Sequence[str]] = None,
    visual_mode: str = "",
) -> dict[str, Any]:
    """Deterministic check: provider formatting must not destroy canonical semantics."""
    blocks: list[str] = []
    warnings: list[str] = []
    prov = (provider_prompt or "").lower()
    canon = (canonical_prompt or "").lower()
    phrases = list(required_phrases or extract_required_semantic_phrases(scene, canonical_prompt))
    for p in phrases:
        if p and p in canon and p not in prov:
            blocks.append(f"lost_semantic_phrase:{p}")
    # Relation degradation: beside present canonically but only located_at in provider
    if "beside" in canon and "beside" not in prov and "located at" in prov:
        blocks.append("relation_degraded_beside_to_located_at")
    mode = (visual_mode or scene.get("visual_mode") or "").strip().upper()
    if mode in SUPPORTED_VISUAL_MODES:
        # Accept either original section or VISUAL_MODE_LOCK
        if mode.lower() not in prov and f"visual_mode_lock: {mode.lower()}" not in prov:
            # soft if mode only in scene metadata and never in canonical string
            if mode.lower() in canon or "visual_mode" in canon:
                blocks.append(f"lost_visual_mode:{mode}")
            else:
                warnings.append(f"visual_mode_not_in_prompt_text:{mode}")
    return {
        "ok": not blocks,
        "blocked": bool(blocks),
        "blocks": blocks,
        "warnings": warnings,
        "paid_api_calls": 0,
    }


def resolve_provider_route(
    visual_mode: str,
    *,
    preferred_provider: str = "",
    allow_fallback: bool = True,
) -> dict[str, Any]:
    """Map IMAGE/IMAGE_WITH_MOTION/VIDEO → route + GenerationMode (no prompt-text routing)."""
    mode = (visual_mode or "").strip().upper()
    if mode not in SUPPORTED_VISUAL_MODES:
        return {
            "ok": False,
            "blocked": True,
            "reason": f"unsupported_visual_mode:{mode or 'missing'}",
            "requested_mode": mode,
            "actual_mode": "",
            "route": "",
            "generation_mode": "",
            "fallback_used": False,
        }
    gen = map_mode_to_generation_mode(mode)
    if mode == MODE_IMAGE:
        route = ROUTE_IMAGE
        provider = preferred_provider or "pollinations"
    elif mode == MODE_IMAGE_WITH_MOTION:
        route = ROUTE_IMAGE_WITH_MOTION
        provider = preferred_provider or "fallback_image_video"
    else:
        route = ROUTE_VIDEO
        provider = preferred_provider or "agnes"

    caps = PROVIDER_CAPABILITIES.get(provider, frozenset())
    fallback_used = False
    fallback_reason = ""
    actual = mode
    capability = "OK"
    if mode not in caps:
        if allow_fallback and mode == MODE_VIDEO and MODE_IMAGE_WITH_MOTION in caps:
            # Explicit policy only when allow_fallback — document honesty
            actual = MODE_IMAGE_WITH_MOTION
            route = ROUTE_IMAGE_WITH_MOTION
            fallback_used = True
            fallback_reason = f"provider_{provider}_lacks_VIDEO"
            capability = "FALLBACK"
            gen = map_mode_to_generation_mode(actual)
        elif allow_fallback and mode == MODE_IMAGE_WITH_MOTION and MODE_IMAGE in caps:
            actual = MODE_IMAGE
            route = ROUTE_IMAGE
            fallback_used = True
            fallback_reason = f"provider_{provider}_lacks_IMAGE_WITH_MOTION"
            capability = "FALLBACK"
            gen = map_mode_to_generation_mode(actual)
        else:
            return {
                "ok": False,
                "blocked": True,
                "reason": f"provider_capability_mismatch:requested={mode}:provider={provider}",
                "requested_mode": mode,
                "actual_mode": "",
                "route": route,
                "provider": provider,
                "generation_mode": gen.value,
                "fallback_used": False,
                "capability_status": "BLOCKED",
            }

    # Mandatory VIDEO must not silently become IMAGE
    if mode == MODE_VIDEO and actual == MODE_IMAGE and not allow_fallback:
        return {
            "ok": False,
            "blocked": True,
            "reason": "mandatory_VIDEO_cannot_downgrade_to_IMAGE",
            "requested_mode": mode,
            "actual_mode": actual,
            "route": route,
            "provider": provider,
            "generation_mode": gen.value,
            "fallback_used": fallback_used,
            "capability_status": "BLOCKED",
        }

    return {
        "ok": True,
        "blocked": False,
        "requested_mode": mode,
        "actual_mode": actual,
        "route": route,
        "provider": provider,
        "generation_mode": gen.value,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "capability_status": capability,
    }


def build_generation_payload_from_scene(
    scene: dict[str, Any],
    *,
    job_id: str = "",
    scene_index: int = 0,
    narration: str = "",
    product_name: str = "",
    element: str = "",
    niche: str = "",
    preferred_provider: str = "",
    allow_fallback: bool = True,
    apply_harden: bool = True,
    customer_id: str = "",
    channel_id: str = "",
    language_entitlement: str = "",
    generation_id: str = "",
    legacy_compat: bool = False,
) -> dict[str, Any]:
    """Compose structured GenerationPayload from C05-GA aligned scene."""
    from pipeline.trs_facade import resolve_canonical_visual_prompt

    sc = dict(scene or {})
    resolved = resolve_canonical_visual_prompt(sc, narration=narration or str(sc.get("narration") or ""))
    canonical = str(resolved.get("prompt") or "").strip()
    mode = str(sc.get("visual_mode") or "").strip().upper()
    if not mode:
        return {
            "ok": False,
            "blocked": True,
            "reason": "missing_visual_mode",
            "paid_api_calls": 0,
        }
    if mode not in SUPPORTED_VISUAL_MODES:
        return {
            "ok": False,
            "blocked": True,
            "reason": f"unsupported_visual_mode:{mode}",
            "paid_api_calls": 0,
        }

    dialogue_id = str(sc.get("dialogue_id") or sc.get("c05s_dialogue_id") or "").strip()
    beat_id = str(sc.get("c05s_visual_beat_id") or "").strip()
    if not dialogue_id:
        return {"ok": False, "blocked": True, "reason": "missing_dialogue_id", "paid_api_calls": 0}
    if not beat_id and str(sc.get("visual_direction_source") or "").upper() == "C05-S":
        return {"ok": False, "blocked": True, "reason": "missing_beat_id", "paid_api_calls": 0}
    if not canonical:
        return {"ok": False, "blocked": True, "reason": "missing_canonical_prompt", "paid_api_calls": 0}

    cust = str(customer_id or sc.get("customer_id") or sc.get("owner_id") or "").strip()
    ch = str(channel_id or sc.get("channel_id") or "").strip()
    lang = str(language_entitlement or sc.get("language_entitlement") or sc.get("language") or "").strip()
    gen_id = str(generation_id or "").strip() or _fp(
        {"job": job_id, "dialogue": dialogue_id, "beat": beat_id, "mode": mode, "prompt": canonical[:120]}
    )

    route_info = resolve_provider_route(mode, preferred_provider=preferred_provider, allow_fallback=allow_fallback)
    if route_info.get("blocked"):
        return {**route_info, "ok": False, "paid_api_calls": 0}

    timing = dict(sc.get("visual_timing") or {})
    coverage = dict(sc.get("visual_coverage") or {})
    intent = sc.get("c05s_scene_intent") if isinstance(sc.get("c05s_scene_intent"), dict) else {}
    character_state = dict(sc.get("character_state") or {})
    if not character_state.get("identity") and sc.get("actors"):
        character_state["identity"] = list(sc.get("actors") or [])[0]
    relationships = list(sc.get("required_relationships") or intent.get("relations") or [])
    entities = list(intent.get("entities") or [])
    neg = list(intent.get("negative_constraints") or [])
    if sc.get("compiled_negative_prompt"):
        neg.append(str(sc.get("compiled_negative_prompt")))

    harden_info = {
        "canonical_prompt": canonical,
        "provider_prompt": canonical,
        "integrity": {"ok": True, "blocks": [], "warnings": []},
        "required_phrases": [],
        "restored_phrases": [],
    }
    if apply_harden:
        harden_info = harden_provider_prompt_preserving_semantics(
            canonical,
            scene=sc,
            narration=narration or str(sc.get("narration") or ""),
            product_name=product_name,
            element=element or str(sc.get("element") or ""),
            niche=niche,
            duration_sec=float((timing or {}).get("duration_sec") or 0.0),
        )
        if harden_info["integrity"].get("blocked"):
            return {
                "ok": False,
                "blocked": True,
                "reason": "semantic_integrity_after_hardening",
                "integrity": harden_info["integrity"],
                "paid_api_calls": 0,
            }

    adapter = {
        ROUTE_IMAGE: "fallback_image_video",
        ROUTE_IMAGE_WITH_MOTION: "fallback_image_video",
        ROUTE_VIDEO: "agnes_bridge",
    }.get(str(route_info.get("route") or ""), str(route_info.get("provider") or ""))

    payload = GenerationPayload(
        job_id=job_id,
        scene_id=int(sc.get("scene_index") if sc.get("scene_index") is not None else scene_index),
        dialogue_id=dialogue_id,
        beat_id=beat_id,
        canonical_scene_id=str(sc.get("canonical_scene_id") or "").strip(),
        script_id=str(sc.get("script_id") or "").strip(),
        customer_id=cust,
        channel_id=ch,
        generation_id=gen_id,
        language_entitlement=lang,
        visual_mode=mode,
        generation_mode=str(route_info.get("generation_mode") or ""),
        canonical_prompt=canonical,
        provider_prompt=str(harden_info.get("provider_prompt") or canonical),
        negative_constraints=[str(x) for x in neg if x],
        required_entities=[e if isinstance(e, dict) else {"label": str(e)} for e in entities],
        relationships=[r if isinstance(r, dict) else {} for r in relationships],
        character_state=character_state,
        object_state=[str(o) for o in (sc.get("required_objects") or [])],
        location_identity=str(sc.get("location") or intent.get("location") or ""),
        environment_state=dict(sc.get("environment_state") or {"environment": sc.get("environment")}),
        camera=str(sc.get("camera_intent") or intent.get("shot_type") or ""),
        framing=str(sc.get("framing") or intent.get("framing") or ""),
        lighting=str(sc.get("lighting_intent") or (intent.get("continuity_refs") or {}).get("lighting") or ""),
        atmosphere=str(sc.get("atmosphere") or ""),
        emotion=str(sc.get("emotion") or sc.get("emotional_intent") or ""),
        shot_purpose=str(intent.get("shot_purpose") or ""),
        timing=timing,
        coverage=coverage,
        continuity_fingerprint=str(sc.get("continuity_fingerprint") or sc.get("scene_intent_fingerprint") or ""),
        continuity_refs=dict(sc.get("continuity_refs") or intent.get("continuity_refs") or {}),
        previous_beat_id=str(sc.get("previous_beat_id") or ""),
        next_beat_id=str(sc.get("next_beat_id") or ""),
        transition_intent=str(sc.get("transition_intent") or timing.get("transition") or ""),
        visual_bible_id=str(intent.get("visual_bible_id") or ""),
        route=str(route_info.get("route") or ""),
        requested_mode=str(route_info.get("requested_mode") or mode),
        actual_mode=str(route_info.get("actual_mode") or mode),
        fallback_used=bool(route_info.get("fallback_used")),
        fallback_reason=str(route_info.get("fallback_reason") or ""),
        provider_name=str(route_info.get("provider") or ""),
        adapter=adapter,
        capability_status=str(route_info.get("capability_status") or "OK"),
        legacy_compat=bool(legacy_compat),
        provenance={
            "source": "C05-GA+canonical_prompt_compiler",
            "resolver_source": resolved.get("source"),
            "prompt_authority": sc.get("prompt_authority") or resolved.get("source"),
            "harden_restored": harden_info.get("restored_phrases") or [],
            "legacy_compat": bool(legacy_compat),
            "visual_contract_fingerprint": _fp(
                {
                    "mode": mode,
                    "bible": intent.get("visual_bible_id"),
                    "coverage": coverage,
                }
            ),
        },
        metadata={
            "visual_direction_source": sc.get("visual_direction_source"),
            "c05s_binding_method": sc.get("c05s_binding_method"),
        },
    )
    payload.provenance["prompt_fingerprint"] = payload.prompt_fingerprint
    payload.provenance["alignment_fingerprint"] = payload.alignment_fingerprint
    payload.provenance["payload_fingerprint"] = payload.payload_fingerprint

    return {
        "ok": True,
        "blocked": False,
        "payload": payload.to_dict(),
        "route": route_info,
        "resolved": resolved,
        "harden": {
            "restored_phrases": harden_info.get("restored_phrases"),
            "integrity": harden_info.get("integrity"),
        },
        "paid_api_calls": 0,
    }


def payload_to_visual_request_spec(
    payload: dict[str, Any] | GenerationPayload,
    *,
    provider: str = "",
    model: str = "",
    size: str = "1080x1920",
    duration_sec: float = 0.0,
) -> VisualRequestSpec:
    """Translate structured payload → existing VisualRequestSpec (BUILD-03 identity)."""
    p = payload.to_dict() if isinstance(payload, GenerationPayload) else dict(payload or {})
    if "payload" in p and isinstance(p.get("payload"), dict):
        p = p["payload"]
    mode_val = str(p.get("generation_mode") or GenerationMode.IMAGE_GENERATION.value)
    try:
        gen_mode = GenerationMode(mode_val)
    except Exception:
        gen_mode = map_mode_to_generation_mode(str(p.get("actual_mode") or p.get("visual_mode") or MODE_IMAGE))
    timing = p.get("timing") if isinstance(p.get("timing"), dict) else {}
    dur = float(duration_sec or timing.get("duration_sec") or 0.0)
    meta = {
        "beat_id": p.get("beat_id") or "",
        "visual_mode": p.get("visual_mode") or "",
        "requested_mode": p.get("requested_mode") or "",
        "actual_mode": p.get("actual_mode") or "",
        "route": p.get("route") or "",
        "location_identity": p.get("location_identity") or "",
        "character_identity": (p.get("character_state") or {}).get("identity") or "",
        "object_state": list(p.get("object_state") or []),
        "relationships": list(p.get("relationships") or []),
        "coverage": p.get("coverage") or {},
        "timing": timing,
        "continuity_fingerprint": p.get("continuity_fingerprint") or "",
        "alignment_fingerprint": (p.get("provenance") or {}).get("alignment_fingerprint") or "",
        "prompt_fingerprint": (p.get("provenance") or {}).get("prompt_fingerprint") or "",
        "payload_fingerprint": (p.get("provenance") or {}).get("payload_fingerprint") or "",
        "fallback_used": bool(p.get("fallback_used")),
        "fallback_reason": p.get("fallback_reason") or "",
        "capability_status": p.get("capability_status") or "",
        "canonical_prompt": p.get("canonical_prompt") or "",
        "negative_constraints": list(p.get("negative_constraints") or []),
        "customer_id": p.get("customer_id") or "",
        "channel_id": p.get("channel_id") or "",
        "generation_id": p.get("generation_id") or "",
        "adapter": p.get("adapter") or "",
        "language_entitlement": p.get("language_entitlement") or "",
        "camera": p.get("camera") or "",
        "lighting": p.get("lighting") or "",
        "legacy_compat": bool(p.get("legacy_compat")),
    }
    return VisualRequestSpec(
        job_id=str(p.get("job_id") or "job"),
        scene_id=int(p.get("scene_id") or 0),
        visual_plan_id=str(p.get("beat_id") or p.get("dialogue_id") or "plan"),
        provider=str(provider or p.get("provider_name") or "mock"),
        model=str(model or "default"),
        generation_mode=gen_mode,
        prompt=str(p.get("provider_prompt") or p.get("canonical_prompt") or ""),
        visual_prompt=str(p.get("canonical_prompt") or ""),
        dialogue_id=str(p.get("dialogue_id") or ""),
        canonical_scene_id=str(p.get("canonical_scene_id") or ""),
        script_id=str(p.get("script_id") or ""),
        size=size,
        duration_sec=dur,
        segment_id=str(p.get("beat_id") or ""),
        metadata=meta,
    )


def translate_payload_for_agnes(payload: dict[str, Any] | GenerationPayload) -> dict[str, Any]:
    """Agnes adapter translation — provider-specific fields stay here."""
    p = payload.to_dict() if isinstance(payload, GenerationPayload) else dict(payload or {})
    if "payload" in p and isinstance(p.get("payload"), dict):
        p = p["payload"]
    mode = str(p.get("actual_mode") or p.get("visual_mode") or MODE_VIDEO).upper()
    # Agnes is video-primary; IMAGE routes should not pretend to be Agnes video
    if mode == MODE_IMAGE:
        return {
            "ok": False,
            "blocked": True,
            "reason": "agnes_does_not_serve_IMAGE_use_image_route",
            "provider": "agnes",
            "capability_limitation": "IMAGE_NOT_SUPPORTED",
            "preserved_in_provenance": True,
        }
    agnes_body = {
        "provider": "agnes",
        "model": "agnes-video-v2.0",
        "prompt": p.get("provider_prompt") or p.get("canonical_prompt") or "",
        "canonical_prompt": p.get("canonical_prompt") or "",
        "duration_hint": float((p.get("timing") or {}).get("duration_sec") or 5.0),
        "dialogue_id": p.get("dialogue_id") or "",
        "beat_id": p.get("beat_id") or "",
        "scene_id": p.get("scene_id"),
        "generation_mode": p.get("generation_mode"),
        "requested_mode": p.get("requested_mode"),
        "actual_mode": mode,
        "location": p.get("location_identity") or "",
        "character": (p.get("character_state") or {}).get("identity") or "",
        "relationships": p.get("relationships") or [],
        "camera": p.get("camera") or "",
        "lighting": p.get("lighting") or "",
        "unsupported_fields_not_sent": [],
        "capability_limitations": [],
    }
    # Honest: structured entities may not be a first-class Agnes API field
    if p.get("required_entities") or p.get("coverage"):
        agnes_body["unsupported_fields_not_sent"].extend(["required_entities_structured", "coverage_structured"])
        agnes_body["capability_limitations"].append("STRUCTURED_ENTITY_API_ABSENT")
        agnes_body["preserved_in_canonical_provenance"] = True
    return {"ok": True, "blocked": False, "agnes_request": agnes_body, "paid_api_calls": 0}


def inspect_generation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Observability without secrets."""
    p = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    return {
        "requested_mode": p.get("requested_mode"),
        "actual_mode": p.get("actual_mode"),
        "provider_name": p.get("provider_name"),
        "route": p.get("route"),
        "dialogue_id": p.get("dialogue_id"),
        "beat_id": p.get("beat_id"),
        "scene_id": p.get("scene_id"),
        "canonical_prompt_fingerprint": (p.get("provenance") or {}).get("prompt_fingerprint"),
        "provider_prompt_fingerprint": _fp(p.get("provider_prompt") or ""),
        "alignment_fingerprint": (p.get("provenance") or {}).get("alignment_fingerprint"),
        "fallback_used": p.get("fallback_used"),
        "fallback_reason": p.get("fallback_reason"),
        "capability_status": p.get("capability_status"),
        "has_secrets": bool(re.search(r"(?i)(api[_-]?key|secret|token)\s*[:=]", json.dumps(p))),
        "paid_api_calls": 0,
    }


def plan_image_beats_for_fallback(
    beats: Sequence[dict[str, Any]],
    *,
    requested_mode: str = MODE_VIDEO,
    actual_mode: str = MODE_IMAGE,
) -> dict[str, Any]:
    """C05-GP Step 9: VIDEO→IMAGE fallback uses semantic beat boundaries, not N-second splits.

    Compatible visual beats may share one image; material differences require new images.
    """
    if str(requested_mode).upper() != MODE_VIDEO or str(actual_mode).upper() not in {
        MODE_IMAGE,
        MODE_IMAGE_WITH_MOTION,
    }:
        return {
            "ok": True,
            "beats_required": [],
            "note": "not_a_video_to_image_fallback",
            "paid_api_calls": 0,
        }
    required: list[dict[str, Any]] = []
    prev_key = None
    for i, beat in enumerate(beats or []):
        b = dict(beat or {})
        key = (
            str(b.get("location") or "").strip().lower(),
            str(b.get("subject") or b.get("character") or "").strip().lower(),
            str(b.get("action") or b.get("narration") or "")[:80].strip().lower(),
            str(b.get("dialogue_id") or "").strip(),
            str(b.get("c05s_visual_beat_id") or b.get("beat_id") or "").strip(),
        )
        material = key != prev_key
        if material or not required:
            required.append(
                {
                    "image_index": len(required),
                    "beat_index": i,
                    "dialogue_id": key[3],
                    "beat_id": key[4],
                    "reuse_previous": False,
                    "reason": "material_visual_difference" if prev_key is not None else "first_beat",
                }
            )
            prev_key = key
        else:
            required.append(
                {
                    "image_index": required[-1]["image_index"],
                    "beat_index": i,
                    "dialogue_id": key[3],
                    "beat_id": key[4],
                    "reuse_previous": True,
                    "reason": "visually_compatible_hold",
                }
            )
    return {
        "ok": True,
        "requested_mode": requested_mode,
        "actual_mode": actual_mode,
        "beats_required": required,
        "unique_images": len({x["image_index"] for x in required}),
        "policy": "semantic_beat_boundaries",
        "paid_api_calls": 0,
    }


def assert_generation_payload_ready(result: dict[str, Any]) -> dict[str, Any]:
    if not result.get("ok"):
        return {
            "ok": False,
            "blocked": True,
            "blocks": [str(result.get("reason") or "payload_blocked")],
            "paid_api_calls": 0,
        }
    p = result.get("payload") or {}
    blocks: list[str] = []
    if not p.get("visual_mode"):
        blocks.append("missing_visual_mode")
    if not p.get("dialogue_id"):
        blocks.append("missing_dialogue_id")
    if not p.get("canonical_prompt"):
        blocks.append("missing_canonical_prompt")
    if str(p.get("requested_mode")) == MODE_VIDEO and str(p.get("actual_mode")) == MODE_IMAGE and not p.get("fallback_used"):
        blocks.append("silent_VIDEO_to_IMAGE_downgrade")
    return {"ok": not blocks, "blocked": bool(blocks), "blocks": blocks, "paid_api_calls": 0}


# ---------------------------------------------------------------------------
# C05-GX — Generation execution & beat materialization (composition only)
# ---------------------------------------------------------------------------

LAYER_INTENT = "INTENT"
LAYER_PROMPT = "PROMPT"
LAYER_PROVIDER_REQUEST = "PROVIDER_REQUEST"
LAYER_OBSERVED = "OBSERVED"


def scrub_secrets(obj: Any) -> Any:
    """Remove secret-like values from serializable structures."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if re.search(r"(?i)(api[_-]?key|secret|token|password|authorization)", str(k)):
                out[k] = "***REDACTED***"
            else:
                out[k] = scrub_secrets(v)
        return out
    if isinstance(obj, list):
        return [scrub_secrets(x) for x in obj]
    if isinstance(obj, str) and re.search(r"(?i)(api[_-]?key|sk-[a-zA-Z0-9]{8,}|Bearer\s+\S+)", obj):
        return "***REDACTED***"
    return obj


def semantic_compatibility_key(beat: dict[str, Any]) -> dict[str, str]:
    """Identity key for adaptive multi-beat asset reuse (not list index)."""
    b = dict(beat or {})
    rels = b.get("required_relationships") or b.get("relationships") or []
    rel_s = "|".join(
        sorted(
            f"{(r or {}).get('relation_type')}:{(r or {}).get('source_id')}:{(r or {}).get('target_id')}"
            if isinstance(r, dict)
            else str(r)
            for r in rels
        )
    )
    objs = b.get("required_objects") or b.get("object_state") or []
    if isinstance(objs, dict):
        objs = list(objs.values())
    obj_s = "|".join(sorted(str(x).strip().lower() for x in objs if str(x).strip()))
    return {
        "dialogue_id": str(b.get("dialogue_id") or "").strip(),
        "beat_id": str(b.get("c05s_visual_beat_id") or b.get("beat_id") or "").strip(),
        "location": str(b.get("location") or b.get("location_identity") or "").strip().lower(),
        "character": str(
            b.get("subject")
            or b.get("character")
            or (b.get("character_state") or {}).get("identity")
            or ""
        )
        .strip()
        .lower(),
        "character_state": str(
            (b.get("character_state") or {}).get("state")
            or (b.get("character_state") or {}).get("pose")
            or b.get("action")
            or ""
        )
        .strip()
        .lower(),
        "objects": obj_s,
        "relationship": rel_s.lower(),
        "camera": str(b.get("camera") or b.get("camera_intent") or "").strip().lower(),
        "lighting": str(b.get("lighting") or b.get("lighting_intent") or "").strip().lower(),
        "visual_mode": str(b.get("visual_mode") or b.get("requested_mode") or "").strip().upper(),
        "coverage": str((b.get("visual_coverage") or b.get("coverage") or {}).get("overall") or "").strip().lower()
        if isinstance(b.get("visual_coverage") or b.get("coverage"), dict)
        else "",
    }


def beats_are_visually_compatible(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Return whether beat B can reuse asset from beat A."""
    ka, kb = semantic_compatibility_key(a), semantic_compatibility_key(b)
    mismatches: list[str] = []
    for field in ("location", "character", "character_state", "objects", "relationship", "visual_mode"):
        if ka.get(field) and kb.get(field) and ka[field] != kb[field]:
            mismatches.append(field)
    for field in ("camera", "lighting"):
        if ka.get(field) and kb.get(field) and ka[field] != kb[field]:
            mismatches.append(field)
    if bool(ka.get("relationship")) != bool(kb.get("relationship")) and (ka.get("relationship") or kb.get("relationship")):
        if "relationship" not in mismatches:
            mismatches.append("relationship")
    ok = not mismatches
    return {
        "compatible": ok,
        "mismatches": mismatches,
        "preserve_location": ka.get("location") == kb.get("location") or not kb.get("location"),
        "preserve_character": ka.get("character") == kb.get("character") or not kb.get("character"),
        "paid_api_calls": 0,
    }


def materialize_visual_beats(
    beats: Sequence[dict[str, Any]],
    *,
    requested_mode: str = MODE_VIDEO,
    allow_reuse: bool = True,
    retrieval_by_beat: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Convert planned visual beats into generation units (dialogue_id/beat_id authority).

    Never uses list index as sole binding. Adaptive reuse when semantics compatible.
    Optional retrieval_by_beat attaches Phase 6B candidate hints without approving publishability.
    """
    units: list[dict[str, Any]] = []
    prev: Optional[dict[str, Any]] = None
    prev_asset_index = -1
    ambiguous = False
    retrieval_by_beat = dict(retrieval_by_beat or {})
    for i, raw in enumerate(beats or []):
        b = dict(raw or {})
        dialogue_id = str(b.get("dialogue_id") or "").strip()
        beat_id = str(b.get("c05s_visual_beat_id") or b.get("beat_id") or "").strip()
        if not dialogue_id or not beat_id:
            ambiguous = True
            return {
                "ok": False,
                "blocked": True,
                "reason": "ambiguous_dialogue_or_beat_identity",
                "beat_index": i,
                "paid_api_calls": 0,
            }
        timing = dict(b.get("visual_timing") or b.get("timing") or {})
        hold = float(timing.get("duration_sec") or timing.get("hold_sec") or 0.0)
        start = float(timing.get("start_sec") or timing.get("start") or 0.0)
        end = float(timing.get("end_sec") or timing.get("end") or (start + hold if hold else 0.0))
        reuse = False
        reason = "new_asset_required"
        if allow_reuse and prev is not None:
            compat = beats_are_visually_compatible(prev, b)
            if compat["compatible"]:
                reuse = True
                reason = "semantic_compatible_hold"
                asset_index = prev_asset_index
            else:
                reason = "incompatible:" + ",".join(compat["mismatches"])
                asset_index = prev_asset_index + 1
                prev_asset_index = asset_index
        else:
            asset_index = 0 if prev_asset_index < 0 else prev_asset_index + 1
            prev_asset_index = asset_index
            reason = "first_beat" if not units else reason

        unit = {
            "dialogue_id": dialogue_id,
            "beat_id": beat_id,
            "scene_id": b.get("scene_id") if b.get("scene_id") is not None else b.get("scene_index"),
            "asset_index": asset_index,
            "asset_id": "",  # filled when materialized
            "reuse_previous": reuse,
            "reason": reason,
            "start": start,
            "duration": hold,
            "end": end,
            "expected_hold_duration_sec": hold,
            "transition_intent": str(b.get("transition_intent") or timing.get("transition") or ""),
            "location": semantic_compatibility_key(b)["location"],
            "relationship": semantic_compatibility_key(b)["relationship"],
            "coverage": b.get("visual_coverage") or b.get("coverage") or {},
            "requested_mode": str(requested_mode or b.get("visual_mode") or "").upper(),
            "visual_mode": str(b.get("visual_mode") or requested_mode or "").upper(),
        }
        if beat_id in retrieval_by_beat:
            from pipeline.retrieval.bridge import apply_retrieval_to_materialization_unit

            unit = apply_retrieval_to_materialization_unit(unit, retrieval_by_beat[beat_id])
        units.append(unit)
        prev = b

    return {
        "ok": True,
        "blocked": False,
        "units": units,
        "unique_assets": len({u["asset_index"] for u in units}),
        "policy": "semantic_beat_compatibility",
        "binding": "dialogue_id+beat_id",
        "paid_api_calls": 0,
        "retrieval_hints_attached": bool(retrieval_by_beat),
        "retrieval_is_not_publishability": True,
    }


def inspect_provider_request_integrity(
    *,
    intent: dict[str, Any],
    canonical_prompt: str,
    provider_prompt: str,
    provider_request: dict[str, Any],
    observed: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Execution-boundary inspection — request integrity only (not artifact compliance).

    Distinguishes INTENT / PROMPT / PROVIDER_REQUEST / OBSERVED layers.
    """
    blocks: list[str] = []
    warnings: list[str] = []
    intent = dict(intent or {})
    prov = dict(provider_request or {})
    prompt_l = (provider_prompt or "").lower()
    canon_l = (canonical_prompt or "").lower()

    for key in ("dialogue_id", "beat_id", "scene_id", "visual_mode"):
        if not intent.get(key) and intent.get(key) != 0:
            blocks.append(f"intent_missing:{key}")

    # PROVIDER_REQUEST must carry identity
    for key in ("dialogue_id", "beat_id", "visual_mode"):
        if intent.get(key) and not (prov.get(key) or (prov.get("metadata") or {}).get(key)):
            # allow nested agnes_request
            nested = prov.get("agnes_request") or prov.get("payload") or {}
            if not (nested.get(key) or (isinstance(nested.get("metadata"), dict) and nested["metadata"].get(key))):
                blocks.append(f"provider_request_missing:{key}")

    # Semantic phrases from intent must survive provider prompt
    scene_like = {
        "required_relationships": intent.get("relationships") or intent.get("required_relationships") or [],
        "location": intent.get("location_identity") or intent.get("location") or "",
        "actors": [((intent.get("character_state") or {}).get("identity") or "")],
        "required_objects": intent.get("object_state") or intent.get("required_objects") or [],
        "visual_mode": intent.get("visual_mode") or "",
        "character_state": intent.get("character_state") or {},
    }
    phrases = extract_required_semantic_phrases(scene_like, canonical_prompt)
    for p in phrases:
        if p and p in canon_l and p not in prompt_l:
            blocks.append(f"prompt_lost:{p}")

    # Relation corruption
    if "beside" in canon_l and "beside" not in prompt_l and "located at" in prompt_l:
        blocks.append("relationship_corrupted_beside_to_located_at")

    # Continuity / camera / lighting / coverage / timing presence in INTENT
    if intent.get("continuity_fingerprint") and not (
        prov.get("continuity_fingerprint") or (prov.get("metadata") or {}).get("continuity_fingerprint")
    ):
        warnings.append("continuity_not_in_provider_request_fields")
    for field in ("camera", "lighting", "coverage", "timing"):
        if intent.get(field) and field not in prov and field not in (prov.get("metadata") or {}):
            # may be prompt-only — warn, not always block
            if field in ("coverage", "timing") and not intent.get(field):
                continue
            warnings.append(f"{field}_prompt_or_meta_only")

    # OBSERVED layer is never claimed PASS here
    obs = dict(observed or {})
    observed_layer = {
        "status": "UNKNOWN" if not obs else "RECORDED",
        "note": "request_integrity_only_not_artifact_compliance",
        "fields": scrub_secrets(obs),
    }

    layers = {
        LAYER_INTENT: scrub_secrets(
            {
                "dialogue_id": intent.get("dialogue_id"),
                "beat_id": intent.get("beat_id"),
                "scene_id": intent.get("scene_id"),
                "visual_mode": intent.get("visual_mode"),
                "location": intent.get("location_identity") or intent.get("location"),
                "entities": intent.get("required_entities") or intent.get("character_state"),
                "relationships": intent.get("relationships"),
                "camera": intent.get("camera"),
                "lighting": intent.get("lighting"),
                "coverage": intent.get("coverage"),
                "timing": intent.get("timing"),
                "continuity": intent.get("continuity_fingerprint"),
            }
        ),
        LAYER_PROMPT: {
            "canonical_prompt_fp": _fp(canonical_prompt or ""),
            "provider_prompt_fp": _fp(provider_prompt or ""),
            "canonical_excerpt": (canonical_prompt or "")[:160],
            "provider_excerpt": (provider_prompt or "")[:160],
        },
        LAYER_PROVIDER_REQUEST: scrub_secrets(prov),
        LAYER_OBSERVED: observed_layer,
    }

    return {
        "ok": not blocks,
        "blocked": bool(blocks),
        "blocks": blocks,
        "warnings": warnings,
        "layers": layers,
        "claim_artifact_compliance": False,
        "paid_api_calls": 0,
    }


def validate_customer_ownership(
    *,
    payload: dict[str, Any],
    expected_customer_id: str = "",
    expected_channel_id: str = "",
    language_entitlement: str = "",
    allowed_languages: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """C02/C04 isolation at generation boundary — no secrets."""
    p = payload.get("payload") if isinstance(payload.get("payload"), dict) else dict(payload or {})
    blocks: list[str] = []
    cust = str(p.get("customer_id") or "").strip()
    ch = str(p.get("channel_id") or "").strip()
    exp_c = str(expected_customer_id or "").strip()
    exp_ch = str(expected_channel_id or "").strip()
    if exp_c and cust and cust != exp_c:
        blocks.append("customer_ownership_mismatch")
    if exp_ch and ch and ch != exp_ch:
        blocks.append("channel_ownership_mismatch")
    if exp_c and not cust:
        blocks.append("missing_customer_id_on_payload")
    if exp_ch and not ch:
        blocks.append("missing_channel_id_on_payload")
    lang = str(language_entitlement or p.get("language_entitlement") or "").strip()
    if allowed_languages is not None and lang:
        allowed = {str(x).strip().lower() for x in allowed_languages if str(x).strip()}
        if allowed and lang.lower() not in allowed:
            blocks.append("language_entitlement_invalid")
    return {
        "ok": not blocks,
        "blocked": bool(blocks),
        "blocks": blocks,
        "customer_id": cust,
        "channel_id": ch,
        "paid_api_calls": 0,
    }


def record_execution_provenance(
    payload: dict[str, Any],
    *,
    asset_id: str = "",
    source_asset_id: str = "",
    derived_asset_id: str = "",
    fallback_used: Optional[bool] = None,
    fallback_reason: str = "",
    actual_mode: str = "",
    adapter: str = "",
    timing: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Traceability record — not a quality score."""
    p = payload.get("payload") if isinstance(payload.get("payload"), dict) else dict(payload or {})
    fb = bool(p.get("fallback_used")) if fallback_used is None else bool(fallback_used)
    rec = {
        "generation_id": p.get("generation_id") or "",
        "scene_id": p.get("scene_id"),
        "dialogue_id": p.get("dialogue_id") or "",
        "beat_id": p.get("beat_id") or "",
        "requested_mode": p.get("requested_mode") or p.get("visual_mode") or "",
        "actual_mode": actual_mode or p.get("actual_mode") or "",
        "provider": p.get("provider_name") or "",
        "adapter": adapter or p.get("adapter") or "",
        "asset_id": asset_id,
        "source_asset_id": source_asset_id,
        "derived_asset_id": derived_asset_id or asset_id,
        "payload_fingerprint": (p.get("provenance") or {}).get("payload_fingerprint") or _fp(
            {
                "dialogue_id": p.get("dialogue_id"),
                "beat_id": p.get("beat_id"),
                "mode": p.get("visual_mode"),
                "canonical": p.get("canonical_prompt"),
            }
        ),
        "fallback": fb,
        "fallback_reason": fallback_reason or p.get("fallback_reason") or "",
        "timing": timing or p.get("timing") or {},
        "coverage": p.get("coverage") or {},
        "customer_id": p.get("customer_id") or "",
        "channel_id": p.get("channel_id") or "",
        "native_video_claimed": bool(
            str(actual_mode or p.get("actual_mode") or "").upper() == MODE_VIDEO and not fb
        ),
        "paid_api_calls": 0,
    }
    return scrub_secrets(rec)


def assert_execution_ready(
    *,
    payload_result: dict[str, Any],
    integrity: Optional[dict[str, Any]] = None,
    ownership: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Fail-closed gate before provider execution."""
    blocks: list[str] = []
    ready = assert_generation_payload_ready(payload_result)
    if ready.get("blocked"):
        blocks.extend(ready.get("blocks") or [])
    if integrity and integrity.get("blocked"):
        blocks.extend(integrity.get("blocks") or [])
    if ownership and ownership.get("blocked"):
        blocks.extend(ownership.get("blocks") or [])
    p = (payload_result or {}).get("payload") or {}
    timing = p.get("timing") if isinstance(p.get("timing"), dict) else {}
    dur = float(timing.get("duration_sec") or 0.0)
    if dur < 0:
        blocks.append("invalid_timing_negative")
    if str(p.get("requested_mode")) == MODE_VIDEO and str(p.get("actual_mode")) == MODE_IMAGE and not p.get("fallback_used"):
        blocks.append("silent_VIDEO_to_IMAGE_downgrade")
    return {
        "ok": not blocks,
        "blocked": bool(blocks),
        "blocks": blocks,
        "paid_api_calls": 0,
    }


def mark_runtime_fallback(
    payload: dict[str, Any],
    *,
    actual_mode: str,
    fallback_reason: str,
    source_asset_id: str = "",
    derived_asset_id: str = "",
) -> dict[str, Any]:
    """Update payload honesty when runtime falls back (e.g. Agnes fail → image clip)."""
    p = dict(payload or {})
    if "payload" in p and isinstance(p["payload"], dict):
        inner = dict(p["payload"])
        wrapper = True
    else:
        inner = p
        wrapper = False
    requested = str(inner.get("requested_mode") or inner.get("visual_mode") or "")
    inner["fallback_used"] = True
    inner["fallback_reason"] = fallback_reason
    inner["actual_mode"] = actual_mode
    inner["capability_status"] = "FALLBACK"
    inner["adapter"] = inner.get("adapter") or "fallback_image_video"
    prov = dict(inner.get("provenance") or {})
    prov["runtime_fallback"] = True
    prov["source_asset_id"] = source_asset_id
    prov["derived_asset_id"] = derived_asset_id
    prov["native_video_claimed"] = False
    inner["provenance"] = prov
    if wrapper:
        out = dict(payload)
        out["payload"] = inner
        return out
    return inner


def sync_provider_prompt_after_mutation(
    payload: dict[str, Any],
    *,
    new_provider_prompt: str,
    scene: dict[str, Any],
) -> dict[str, Any]:
    """Re-validate semantic integrity when prompt is mutated after payload build (preflight)."""
    p = dict(payload or {})
    inner = dict(p.get("payload") or p)
    canonical = str(inner.get("canonical_prompt") or "")
    integrity = validate_semantic_integrity(
        canonical_prompt=canonical,
        provider_prompt=new_provider_prompt,
        scene=scene,
        visual_mode=str(inner.get("visual_mode") or ""),
    )
    if integrity.get("blocked"):
        return {"ok": False, "blocked": True, "integrity": integrity, "payload": inner, "paid_api_calls": 0}
    inner["provider_prompt"] = new_provider_prompt
    prov = dict(inner.get("provenance") or {})
    prov["prompt_fingerprint"] = _fp({"canonical": canonical, "provider": new_provider_prompt})
    prov["post_payload_prompt_mutation"] = True
    inner["provenance"] = prov
    if "payload" in p:
        p["payload"] = inner
        p["ok"] = True
        return p
    return {"ok": True, "blocked": False, "payload": inner, "integrity": integrity, "paid_api_calls": 0}


# ---------------------------------------------------------------------------
# C05-MR — Materialization & reuse closure (composition only)
# ---------------------------------------------------------------------------

def resolve_visual_mode_for_scene(scene: dict[str, Any]) -> dict[str, Any]:
    """Deterministic visual_mode resolution — no silent legacy invent.

    Sources (priority):
      1. explicit visual_mode
      2. C05-S beat / GenerationMode mapping already stamped
      3. generation_mode enum on scene
    """
    sc = dict(scene or {})
    mode = str(sc.get("visual_mode") or "").strip().upper()
    if mode in SUPPORTED_VISUAL_MODES:
        return {"ok": True, "visual_mode": mode, "source": "explicit", "paid_api_calls": 0}
    # From directed beat dicts if present
    for beat in sc.get("c05s_visual_beats") or sc.get("visual_beats") or []:
        if isinstance(beat, dict):
            bm = str(beat.get("visual_mode") or "").strip().upper()
            if bm in SUPPORTED_VISUAL_MODES:
                return {"ok": True, "visual_mode": bm, "source": "c05s_visual_beat", "paid_api_calls": 0}
    gen = str(sc.get("generation_mode") or "").strip().upper()
    if gen == GenerationMode.IMAGE_GENERATION.value:
        return {"ok": True, "visual_mode": MODE_IMAGE, "source": "generation_mode", "paid_api_calls": 0}
    if gen == GenerationMode.IMAGE_WITH_MOTION.value:
        return {"ok": True, "visual_mode": MODE_IMAGE_WITH_MOTION, "source": "generation_mode", "paid_api_calls": 0}
    if gen in {GenerationMode.TEXT_TO_VIDEO.value, GenerationMode.IMAGE_TO_VIDEO.value}:
        return {"ok": True, "visual_mode": MODE_VIDEO, "source": "generation_mode", "paid_api_calls": 0}
    # C05-V style hints without inventing: only if visual_direction_source is C05-S/C05-V
    src = str(sc.get("visual_direction_source") or "").upper()
    if src in {"C05-S", "C05-V"} and sc.get("c05s_visual_beat_id"):
        # Bound C05-S beat without mode is a contract defect → fail closed
        return {
            "ok": False,
            "blocked": True,
            "reason": "c05s_beat_missing_visual_mode",
            "visual_mode": "",
            "paid_api_calls": 0,
        }
    return {
        "ok": False,
        "blocked": True,
        "reason": "visual_mode_unresolvable",
        "visual_mode": "",
        "paid_api_calls": 0,
    }


def attach_scene_beat_context(
    scene: dict[str, Any],
    beats: Sequence[dict[str, Any]],
    *,
    dialogue_id: str = "",
) -> dict[str, Any]:
    """Attach planned visual beats to a scene (first-class context). Does not invent semantics."""
    sc = dict(scene or {})
    did = str(dialogue_id or sc.get("dialogue_id") or sc.get("c05s_dialogue_id") or "").strip()
    relevant: list[dict[str, Any]] = []
    for raw in beats or []:
        b = dict(raw or {})
        b_did = str(
            b.get("dialogue_id")
            or b.get("dialogue_segment_id")
            or ""
        ).strip()
        # Prefer dialogue-scoped beats; if no dialogue filter, keep all with ids
        if did and b_did and b_did != did and b.get("dialogue_segment_id") != did:
            # also match via segment linkage fields
            if str(b.get("c05s_dialogue_id") or "") != did:
                continue
        if not str(b.get("beat_id") or b.get("c05s_visual_beat_id") or "").strip():
            continue
        # Normalize identity fields
        if did and not b.get("dialogue_id"):
            b["dialogue_id"] = did
        if not b.get("c05s_visual_beat_id") and b.get("beat_id"):
            b["c05s_visual_beat_id"] = b["beat_id"]
        relevant.append(b)
    sc["c05s_visual_beats"] = relevant
    if relevant and not sc.get("c05s_visual_beat_id"):
        sc["c05s_visual_beat_id"] = relevant[0].get("c05s_visual_beat_id") or relevant[0].get("beat_id")
    if relevant and not sc.get("visual_mode"):
        vm = str(relevant[0].get("visual_mode") or "").strip().upper()
        if vm in SUPPORTED_VISUAL_MODES:
            sc["visual_mode"] = vm
    return sc


def assert_beat_scene_binding(
    *,
    dialogue_id: str,
    beat_id: str,
    scene_id: Any,
    expected_dialogue_id: str = "",
    expected_beat_id: str = "",
) -> dict[str, Any]:
    """Fail-closed when beat/scene identity is ambiguous or conflicts."""
    blocks: list[str] = []
    if not str(dialogue_id or "").strip():
        blocks.append("missing_dialogue_id")
    if not str(beat_id or "").strip():
        blocks.append("missing_beat_id")
    if scene_id is None or str(scene_id).strip() == "":
        blocks.append("missing_scene_id")
    exp_d = str(expected_dialogue_id or "").strip()
    exp_b = str(expected_beat_id or "").strip()
    if exp_d and str(dialogue_id).strip() != exp_d:
        blocks.append("dialogue_id_scene_conflict")
    if exp_b and str(beat_id).strip() != exp_b:
        blocks.append("beat_id_scene_conflict")
    return {"ok": not blocks, "blocked": bool(blocks), "blocks": blocks, "paid_api_calls": 0}


def assert_customer_scoped_asset_reuse(
    *,
    requester_customer_id: str,
    asset_customer_id: str,
    requester_channel_id: str = "",
    asset_channel_id: str = "",
    globally_shareable: bool = False,
) -> dict[str, Any]:
    """Default: customer-scoped reuse only. Cross-customer match must never reuse."""
    if globally_shareable:
        return {"ok": True, "blocked": False, "blocks": [], "paid_api_calls": 0}
    blocks: list[str] = []
    req_c = str(requester_customer_id or "").strip()
    asset_c = str(asset_customer_id or "").strip()
    if req_c and asset_c and req_c != asset_c:
        blocks.append("cross_customer_reuse_forbidden")
    req_ch = str(requester_channel_id or "").strip()
    asset_ch = str(asset_channel_id or "").strip()
    if req_ch and asset_ch and req_ch != asset_ch:
        blocks.append("cross_channel_reuse_forbidden")
    return {"ok": not blocks, "blocked": bool(blocks), "blocks": blocks, "paid_api_calls": 0}


def enrich_materialization_lineage(
    units: Sequence[dict[str, Any]],
    *,
    generation_id: str = "",
    payload_fingerprint: str = "",
    provider: str = "",
    requested_mode: str = "",
    actual_mode: str = "",
    fallback: bool = False,
    fallback_reason: str = "",
    asset_ids: Optional[dict[int, str]] = None,
) -> list[dict[str, Any]]:
    """Attach request/asset lineage to materialization units."""
    out: list[dict[str, Any]] = []
    asset_ids = dict(asset_ids or {})
    for u in units or []:
        row = dict(u)
        idx = int(row.get("asset_index") or 0)
        row["generation_id"] = generation_id
        row["payload_fingerprint"] = payload_fingerprint
        row["provider"] = provider
        row["requested_mode"] = requested_mode or row.get("requested_mode") or ""
        row["actual_mode"] = actual_mode or row.get("actual_mode") or row.get("requested_mode") or ""
        row["fallback"] = bool(fallback)
        row["fallback_reason"] = fallback_reason
        if idx in asset_ids:
            row["asset_id"] = asset_ids[idx]
        elif row.get("reuse_previous") and out:
            # inherit prior unit asset_id when reusing
            for prev in reversed(out):
                if int(prev.get("asset_index") or -1) == idx and prev.get("asset_id"):
                    row["asset_id"] = prev["asset_id"]
                    break
        out.append(row)
    return out


def p04_observed_status() -> dict[str, Any]:
    """C05-MR does not claim media semantic observation."""
    return {
        "layer": "OBSERVED",
        "status": "UNKNOWN",
        "note": "C05-MR_materialization_only_not_VLM_ASR",
        "claim_pass": False,
        "paid_api_calls": 0,
    }


def is_legacy_compat_allowed(scene: dict[str, Any]) -> dict[str, Any]:
    """LEGACY_COMPAT only for explicitly marked historical fixtures — outside canonical production."""
    sc = dict(scene or {})
    marked = bool(sc.get("legacy_compat")) or str(sc.get("visual_direction_source") or "").upper() == "LEGACY_COMPAT"
    fixture = bool(sc.get("historical_fixture") or sc.get("amp_legacy_fixture"))
    if marked and fixture:
        return {
            "allowed": True,
            "canonical": False,
            "note": "explicit_historical_fixture_only",
            "paid_api_calls": 0,
        }
    return {
        "allowed": False,
        "canonical": True,
        "note": "canonical_production_requires_visual_mode",
        "paid_api_calls": 0,
    }


def idempotent_image_clip_via_build03(
    *,
    work_dir: Any,
    payload: dict[str, Any],
    out_path: Any,
    provider_fn,
    size: str = "1080x1920",
    duration_sec: float = 0.0,
) -> dict[str, Any]:
    """Route image/motion clip generation through BUILD-03 execute_visual_request (sole idempotency)."""
    from pathlib import Path

    from pipeline.idempotency.visual_provenance import load_visual_provenance
    from pipeline.idempotency.visual_request import compute_visual_fingerprint
    from pipeline.idempotency.visual_runtime import execute_visual_request

    work_dir = Path(work_dir)
    out_path = Path(out_path)
    p = dict(payload or {})
    scope = assert_customer_scoped_asset_reuse(
        requester_customer_id=str(p.get("customer_id") or ""),
        asset_customer_id=str(p.get("customer_id") or ""),
        requester_channel_id=str(p.get("channel_id") or ""),
        asset_channel_id=str(p.get("channel_id") or ""),
    )
    if scope.get("blocked"):
        return {"ok": False, "blocked": True, "blocks": scope.get("blocks"), "paid_api_calls": 0}

    spec = payload_to_visual_request_spec(
        p,
        provider=str(p.get("provider_name") or "fallback_image_video"),
        size=size,
        duration_sec=duration_sec,
    )
    fp = compute_visual_fingerprint(spec)
    prior = load_visual_provenance(work_dir, fp)
    if prior:
        prior_cust = str(
            ((prior.get("provenance") or {}).get("customer_id"))
            or ((prior.get("spec") or {}).get("metadata") or {}).get("customer_id")
            or ""
        )
        cross = assert_customer_scoped_asset_reuse(
            requester_customer_id=str(p.get("customer_id") or ""),
            asset_customer_id=prior_cust,
            requester_channel_id=str(p.get("channel_id") or ""),
            asset_channel_id=str(
                ((prior.get("provenance") or {}).get("channel_id"))
                or ((prior.get("spec") or {}).get("metadata") or {}).get("channel_id")
                or ""
            ),
        )
        if cross.get("blocked"):
            return {
                "ok": False,
                "blocked": True,
                "blocks": cross.get("blocks"),
                "fingerprint": fp,
                "paid_api_calls": 0,
            }

    result = execute_visual_request(work_dir, spec, out_path, provider_fn=provider_fn)
    return {
        "ok": bool(result.success and result.path and result.path.is_file()),
        "blocked": False,
        "path": result.path,
        "action": result.action,
        "fingerprint": result.fingerprint,
        "asset_id": result.asset_id,
        "reused": result.action == "reuse",
        "provider_invocations": result.provider_invocations,
        "provenance_path": result.provenance_path,
        "paid_api_calls": 0,
    }
