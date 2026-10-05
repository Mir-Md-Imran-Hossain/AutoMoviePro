"""C05-V — Visual Intelligence / Image-First foundation (orchestration only).

Composes existing authorities:
  - domain.scene_intent.SceneIntent
  - pipeline.multimodal_consistency.prompt_compiler
  - pipeline.visual_semantic.continuity.ContinuityTracker
  - pipeline.idempotency.visual_request.GenerationMode / VisualRequestSpec
  - pipeline.fallback_image_video (IMAGE_WITH_MOTION capability)
  - Artifact Verification / BUILD-04F (observation boundary — not replaced)

Does NOT create a second generation, quality, continuity, or prompt engine.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from domain.scene_intent import SceneIntent
from pipeline.idempotency.visual_request import GenerationMode
from pipeline.multimodal_consistency.prompt_compiler import CompiledPrompt, compile_provider_prompt
from pipeline.visual_semantic.continuity import ContinuityConstraints, ContinuityTracker
from pipeline.visual_semantic.scene_intent import intent_fingerprint

# Customer-facing / contract scene visual modes (C05-V)
MODE_IMAGE = "IMAGE"
MODE_IMAGE_WITH_MOTION = "IMAGE_WITH_MOTION"
MODE_VIDEO = "VIDEO"
SUPPORTED_VISUAL_MODES = frozenset({MODE_IMAGE, MODE_IMAGE_WITH_MOTION, MODE_VIDEO})

SEED_UNSUPPORTED = "SEED_UNSUPPORTED"
IMAGE_MOTION_AVAILABLE = "AVAILABLE"  # via pipeline.fallback_image_video
IMAGE_MOTION_STATUS = IMAGE_MOTION_AVAILABLE

# Continuity declaration vocabulary (maps onto ContinuityTracker; not a second engine)
MUST_PERSIST = "MUST_PERSIST"
MUST_CHANGE = "MUST_CHANGE"
MUST_NOT_CHANGE = "MUST_NOT_CHANGE"
MUST_APPEAR = "MUST_APPEAR"
MUST_NOT_APPEAR = "MUST_NOT_APPEAR"

_SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+")


class VisualModeDecision(str, Enum):
    IMAGE = MODE_IMAGE
    IMAGE_WITH_MOTION = MODE_IMAGE_WITH_MOTION
    VIDEO = MODE_VIDEO


@dataclass
class VisualBible:
    """Provider-neutral stable visual identity — NOT a quality score or generation engine."""

    bible_id: str
    version: str = "1"
    subject_identity: str = ""
    character_identity: str = ""
    object_identity: str = ""
    environment: str = ""
    location: str = ""
    architecture: str = ""
    wardrobe: str = ""
    props: str = ""
    era: str = ""
    geography: str = ""
    visual_style: str = ""
    lighting: str = ""
    color_direction: str = ""
    camera_language: str = ""
    framing: str = ""
    visual_realism: str = ""
    reference_asset_ids: list[str] = field(default_factory=list)
    negative_constraints: list[str] = field(default_factory=list)
    provider_neutral_constraints: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisualBible":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in (data or {}).items() if k in known}
        if "reference_asset_ids" in clean and not isinstance(clean["reference_asset_ids"], list):
            clean["reference_asset_ids"] = list(clean["reference_asset_ids"] or [])
        if "negative_constraints" in clean and not isinstance(clean["negative_constraints"], list):
            clean["negative_constraints"] = list(clean["negative_constraints"] or [])
        if "provider_neutral_constraints" in clean and not isinstance(
            clean["provider_neutral_constraints"], list
        ):
            clean["provider_neutral_constraints"] = list(clean["provider_neutral_constraints"] or [])
        if "metadata" in clean and not isinstance(clean["metadata"], dict):
            clean["metadata"] = {}
        return cls(**clean)


@dataclass
class SceneVisualDelta:
    """Scene-specific visual changes relative to the Visual Bible."""

    must_appear: list[str] = field(default_factory=list)
    must_not_appear: list[str] = field(default_factory=list)
    must_persist: list[str] = field(default_factory=list)
    must_change: list[str] = field(default_factory=list)
    must_not_change: list[str] = field(default_factory=list)
    action: str = ""
    composition: str = ""
    camera_intent: str = ""
    environment_delta: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SceneVisualDelta":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in (data or {}).items() if k in known}
        for list_key in (
            "must_appear",
            "must_not_appear",
            "must_persist",
            "must_change",
            "must_not_change",
        ):
            if list_key in clean and not isinstance(clean[list_key], list):
                clean[list_key] = list(clean[list_key] or [])
        return cls(**clean)


@dataclass
class SceneVisualContract:
    """Canonical scene visual contract: VisualBible + SceneIntent + delta + mode."""

    contract_id: str
    version: str
    scene_id: str
    dialogue_id: str
    visual_bible_id: str
    visual_bible_version: str
    visual_mode: str
    mode_reason: str
    delta: SceneVisualDelta
    intent_fingerprint: str = ""
    prompt_fingerprint: str = ""
    continuity_declarations: list[dict[str, str]] = field(default_factory=list)
    localized_visual_text: list[dict[str, Any]] = field(default_factory=list)
    lineage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _now() -> str:
    return datetime.now().isoformat()


def _fp(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def sanitize_visual_metadata(obj: Any) -> Any:
    """Strip secret-like values from visual metadata projections."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if any(x in kl for x in ("password", "api_key", "token", "secret", "authorization")):
                out[k] = "[redacted]"
            else:
                out[k] = sanitize_visual_metadata(v)
        return out
    if isinstance(obj, list):
        return [sanitize_visual_metadata(x) for x in obj]
    if isinstance(obj, str) and _SECRET_RE.search(obj):
        return _SECRET_RE.sub(r"\1=[redacted]", obj)
    return obj


def create_visual_bible(
    *,
    bible_id: str,
    version: str = "1",
    **fields: Any,
) -> VisualBible:
    if not (bible_id or "").strip():
        raise ValueError("bible_id_required")
    now = _now()
    data = {k: v for k, v in fields.items() if v is not None}
    bible = VisualBible(
        bible_id=bible_id.strip(),
        version=str(version or "1"),
        created_at=now,
        updated_at=now,
        **{k: v for k, v in data.items() if k in VisualBible.__dataclass_fields__ and k not in ("bible_id", "version", "created_at", "updated_at")},
    )
    validate_visual_bible(bible)
    return bible


def validate_visual_bible(bible: VisualBible) -> None:
    if not bible.bible_id.strip():
        raise ValueError("bible_id_required")
    if not str(bible.version).strip():
        raise ValueError("version_required")
    # At least one identity anchor required
    anchors = [
        bible.subject_identity,
        bible.character_identity,
        bible.object_identity,
        bible.environment,
        bible.location,
        bible.visual_style,
    ]
    if not any(str(a or "").strip() for a in anchors):
        raise ValueError("visual_bible_identity_required")


def bump_visual_bible_version(bible: VisualBible, *, fields: Optional[dict[str, Any]] = None) -> VisualBible:
    data = bible.to_dict()
    if fields:
        data.update(fields)
    try:
        ver = int(str(bible.version).strip() or "1")
        next_ver = str(ver + 1)
    except Exception:
        next_ver = f"{bible.version}.1"
    data["version"] = next_ver
    data["updated_at"] = _now()
    if not data.get("created_at"):
        data["created_at"] = data["updated_at"]
    out = VisualBible.from_dict(data)
    validate_visual_bible(out)
    return out


def decide_visual_mode(
    *,
    primary_action: str = "",
    camera_motion: str = "",
    requires_transformation: bool = False,
    static_sufficient: bool = False,
    controlled_motion_helps: bool = False,
    explicit_mode: str = "",
    narration: str = "",
    element: str = "",
    prefer_image_fallback: bool = False,
    visual_change_candidate: bool = True,
    beat_index: int = 0,
    total_beats: int = 1,
) -> dict[str, str]:
    """Explainable IMAGE / IMAGE_WITH_MOTION / VIDEO decision — VIDEO primary (industrial)."""
    from pipeline.media_mode_engine import decide_media_mode

    decision = decide_media_mode(
        primary_action=primary_action,
        camera_motion=camera_motion,
        narration=narration,
        element=element,
        requires_transformation=requires_transformation,
        static_sufficient=static_sufficient,
        controlled_motion_helps=controlled_motion_helps,
        explicit_mode=explicit_mode,
        prefer_image_fallback=prefer_image_fallback,
        visual_change_candidate=visual_change_candidate,
        beat_index=beat_index,
        total_beats=total_beats,
    )
    return {
        "mode": str(decision.get("mode") or MODE_VIDEO),
        "reason": str(decision.get("reason") or "default_video_primary_agnes"),
        "ok": str(decision.get("ok") or "true"),
        "image_authorized": str(bool(decision.get("image_authorized"))).lower(),
        "agnes_required": str(bool(decision.get("agnes_required", True))).lower(),
    }


def map_mode_to_generation_mode(visual_mode: str) -> GenerationMode:
    m = (visual_mode or "").strip().upper()
    if m == MODE_IMAGE:
        return GenerationMode.IMAGE_GENERATION
    if m == MODE_IMAGE_WITH_MOTION:
        return GenerationMode.IMAGE_WITH_MOTION
    if m == MODE_VIDEO:
        return GenerationMode.TEXT_TO_VIDEO
    raise ValueError(f"unsupported_visual_mode:{m}")


def image_motion_capability() -> dict[str, str]:
    """Existing controlled image-motion authority status."""
    try:
        from pipeline.fallback_image_video import build_image_video_fallback  # noqa: F401

        return {
            "status": IMAGE_MOTION_AVAILABLE,
            "authority": "pipeline.fallback_image_video.build_image_video_fallback",
            "note": "Ken Burns / zoompan controlled motion — not a second render engine",
        }
    except Exception:
        return {
            "status": "IMAGE_MOTION_NOT_IMPLEMENTED",
            "authority": "",
            "note": "no image-motion authority importable",
        }


def seed_status_for_provider(provider: str, seed: Optional[int] = None) -> dict[str, Any]:
    """Honest seed handling — never fabricate cross-provider determinism."""
    p = (provider or "").strip().lower()
    # Known: mock/fallback image paths support seed; Agnes does not
    supports = p in {"mock", "fallback", "pollinations", "image_fallback", "mock_visual"}
    if not supports:
        return {
            "seed": None,
            "status": SEED_UNSUPPORTED,
            "provider": p,
            "cross_provider_determinism": False,
            "note": "seed unsupported or unknown for provider — not fabricated",
        }
    return {
        "seed": seed,
        "status": "SEED_SUPPORTED" if seed is not None else "SEED_SUPPORTED_UNSET",
        "provider": p,
        "cross_provider_determinism": False,
        "note": "identical seed does not guarantee identical output across models/providers",
    }


def derive_scene_seed(base_seed: int, scene_index: int) -> int:
    """Deterministic derived seed for supported providers only."""
    if base_seed is None:
        raise ValueError("base_seed_required")
    # Stable derivation — not a claim of semantic identity
    h = hashlib.sha256(f"{int(base_seed)}:{int(scene_index)}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) % (2**31 - 1)


def apply_bible_to_intent(intent: SceneIntent, bible: VisualBible, delta: SceneVisualDelta, visual_mode: str) -> SceneIntent:
    """Inherit Visual Bible into SceneIntent without rebuilding identity from scratch."""
    data = intent.model_dump()
    data["visual_bible_id"] = bible.bible_id
    data["visual_bible_version"] = bible.version
    data["visual_mode"] = visual_mode
    data["scene_visual_delta"] = delta.to_dict()

    # Inherit stable identity when scene fields empty
    if not (data.get("location") or "").strip() and bible.location:
        data["location"] = bible.location
    if not (data.get("environment") or "").strip() and bible.environment:
        data["environment"] = bible.environment
    if bible.wardrobe and not (data.get("continuity_refs") or {}).get("wardrobe"):
        refs = dict(data.get("continuity_refs") or {})
        refs["wardrobe"] = bible.wardrobe
        data["continuity_refs"] = refs
    if bible.lighting:
        refs = dict(data.get("continuity_refs") or {})
        refs.setdefault("lighting", bible.lighting)
        data["continuity_refs"] = refs
    if bible.camera_language:
        refs = dict(data.get("continuity_refs") or {})
        refs.setdefault("camera_language", bible.camera_language)
        data["continuity_refs"] = refs
    if bible.visual_style:
        meta = dict(data.get("metadata") or {})
        meta.setdefault("style", bible.visual_style)
        data["metadata"] = meta
    if bible.character_identity and not data.get("actors"):
        data["actors"] = [bible.character_identity]
    if bible.subject_identity and not (data.get("summary") or "").strip():
        data["summary"] = bible.subject_identity

    # Apply delta constraints onto SceneIntent fields
    if delta.action and not (data.get("primary_action") or "").strip():
        data["primary_action"] = delta.action
    if delta.camera_intent and not (data.get("camera_motion") or "").strip():
        data["camera_motion"] = delta.camera_intent
    if delta.environment_delta:
        data["environment"] = f"{data.get('environment') or ''} {delta.environment_delta}".strip()
    if delta.must_appear:
        req = list(data.get("required_objects") or [])
        for x in delta.must_appear:
            if x not in req:
                req.append(x)
        data["required_objects"] = req
    if delta.must_not_appear:
        forb = list(data.get("forbidden_objects") or [])
        for x in delta.must_not_appear:
            if x not in forb:
                forb.append(x)
        data["forbidden_objects"] = forb
    if bible.negative_constraints:
        neg = list(data.get("negative_constraints") or [])
        for x in bible.negative_constraints:
            if x not in neg:
                neg.append(x)
        data["negative_constraints"] = neg
    if bible.provider_neutral_constraints:
        neg = list(data.get("negative_constraints") or [])
        for x in bible.provider_neutral_constraints:
            if x not in neg:
                neg.append(x)
        data["negative_constraints"] = neg

    return SceneIntent.model_validate(data)


def detect_delta_contradictions(delta: SceneVisualDelta) -> list[str]:
    issues = []
    appear = set(x.strip().lower() for x in delta.must_appear if x.strip())
    not_appear = set(x.strip().lower() for x in delta.must_not_appear if x.strip())
    overlap = appear & not_appear
    if overlap:
        issues.append(f"must_appear_and_must_not_appear:{','.join(sorted(overlap))}")
    persist = set(x.strip().lower() for x in delta.must_persist if x.strip())
    change = set(x.strip().lower() for x in delta.must_change if x.strip())
    both = persist & change
    if both:
        issues.append(f"must_persist_and_must_change:{','.join(sorted(both))}")
    return issues


def continuity_declarations_from_delta(delta: SceneVisualDelta) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for x in delta.must_persist:
        out.append({"kind": MUST_PERSIST, "target": x})
    for x in delta.must_change:
        out.append({"kind": MUST_CHANGE, "target": x})
    for x in delta.must_not_change:
        out.append({"kind": MUST_NOT_CHANGE, "target": x})
    for x in delta.must_appear:
        out.append({"kind": MUST_APPEAR, "target": x})
    for x in delta.must_not_appear:
        out.append({"kind": MUST_NOT_APPEAR, "target": x})
    return out


def build_scene_visual_contract(
    *,
    bible: VisualBible,
    intent: SceneIntent,
    delta: Optional[SceneVisualDelta] = None,
    visual_mode: str = "",
    mode_reason: str = "",
    contract_version: str = "1",
) -> SceneVisualContract:
    validate_visual_bible(bible)
    delta = delta or SceneVisualDelta()
    contradictions = detect_delta_contradictions(delta)
    if contradictions:
        raise ValueError("visual_delta_contradiction:" + ";".join(contradictions))

    if not visual_mode:
        decision = decide_visual_mode(
            primary_action=intent.primary_action or delta.action,
            camera_motion=intent.camera_motion or delta.camera_intent,
        )
        if decision.get("ok") != "true":
            raise ValueError(decision.get("reason") or "visual_mode_undecided")
        visual_mode = decision["mode"]
        mode_reason = mode_reason or decision["reason"]
    else:
        visual_mode = visual_mode.strip().upper()
        if visual_mode not in SUPPORTED_VISUAL_MODES:
            raise ValueError(f"unsupported_visual_mode:{visual_mode}")
        mode_reason = mode_reason or f"explicit_mode:{visual_mode}"

    enriched = apply_bible_to_intent(intent, bible, delta, visual_mode)
    fp = intent_fingerprint(enriched)
    contract_id = f"svc-{enriched.scene_id}-{enriched.dialogue_id}-{contract_version}"
    return SceneVisualContract(
        contract_id=contract_id,
        version=str(contract_version),
        scene_id=enriched.scene_id,
        dialogue_id=enriched.dialogue_id,
        visual_bible_id=bible.bible_id,
        visual_bible_version=bible.version,
        visual_mode=visual_mode,
        mode_reason=mode_reason,
        delta=delta,
        intent_fingerprint=fp,
        continuity_declarations=continuity_declarations_from_delta(delta),
        localized_visual_text=list(enriched.localized_visual_text or []),
        lineage={
            "visual_bible_id": bible.bible_id,
            "visual_bible_version": bible.version,
            "scene_contract_version": str(contract_version),
            "intent_fingerprint": fp,
        },
    )


def compile_visual_prompt(
    *,
    bible: VisualBible,
    intent: SceneIntent,
    delta: Optional[SceneVisualDelta] = None,
    visual_mode: str = "",
) -> dict[str, Any]:
    """Use existing canonical prompt compiler — never introduce a second compiler."""
    contract = build_scene_visual_contract(
        bible=bible, intent=intent, delta=delta, visual_mode=visual_mode
    )
    enriched = apply_bible_to_intent(intent, bible, delta or SceneVisualDelta(), contract.visual_mode)
    compiled: CompiledPrompt = compile_provider_prompt(enriched)
    provenance = {
        "visual_bible_id": bible.bible_id,
        "visual_bible_version": bible.version,
        "scene_contract_id": contract.contract_id,
        "scene_contract_version": contract.version,
        "intent_fingerprint": contract.intent_fingerprint,
        "prompt_fingerprint": _fp({"positive": compiled.positive, "negative": compiled.negative}),
        "visual_mode": contract.visual_mode,
        "compiler": "pipeline.multimodal_consistency.prompt_compiler.compile_provider_prompt",
        "legacy_prompt_engineering_authority": False,
    }
    return {
        "ok": True,
        "compiled": compiled.to_dict(),
        "contract": contract.to_dict(),
        "intent": enriched.model_dump(),
        "provenance": provenance,
        "generation_mode": map_mode_to_generation_mode(contract.visual_mode).value,
    }


def validate_pre_visual_generation(
    *,
    bible: VisualBible,
    intent: SceneIntent,
    delta: Optional[SceneVisualDelta] = None,
    visual_mode: str = "",
    provider: str = "",
    seed: Optional[int] = None,
    tracker: Optional[ContinuityTracker] = None,
    reference_asset_ids: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Fail-closed preflight before paid provider calls."""
    issues: list[str] = []
    try:
        validate_visual_bible(bible)
    except ValueError as exc:
        issues.append(str(exc))

    delta = delta or SceneVisualDelta()
    issues.extend(detect_delta_contradictions(delta))

    mode_info = decide_visual_mode(
        primary_action=intent.primary_action or delta.action,
        camera_motion=intent.camera_motion or delta.camera_intent,
        explicit_mode=visual_mode,
    )
    if mode_info.get("ok") != "true":
        issues.append(mode_info.get("reason") or "unsupported_mode")
        mode = ""
    else:
        mode = mode_info["mode"]

    # Required subject / objects
    if not (intent.actors or bible.character_identity or bible.subject_identity or intent.entities):
        issues.append("required_subject_missing")
    for obj in delta.must_appear:
        # presence declared — OK; contradiction already checked
        if not obj.strip():
            issues.append("empty_must_appear")

    # Localization-independent: bible must not embed language as identity
    for field_name in ("subject_identity", "character_identity", "environment", "visual_style"):
        val = str(getattr(bible, field_name, "") or "")
        if re.search(r"(?i)\b(translate|subtitle|narration language)\b", val):
            issues.append(f"bible_language_leak:{field_name}")

    # Provider / mode support
    if mode == MODE_IMAGE_WITH_MOTION:
        cap = image_motion_capability()
        if cap.get("status") != IMAGE_MOTION_AVAILABLE:
            issues.append("IMAGE_MOTION_NOT_IMPLEMENTED")
    try:
        if mode:
            map_mode_to_generation_mode(mode)
    except ValueError as exc:
        issues.append(str(exc))

    seed_info = seed_status_for_provider(provider, seed)
    if seed is not None and seed_info.get("status") == SEED_UNSUPPORTED:
        issues.append("seed_requested_but_unsupported")

    # ContinuityTracker remains authority for pre-gen continuity
    if tracker is not None:
        try:
            constraints = ContinuityConstraints(
                mandatory=bool(delta.must_persist or delta.must_not_change),
                required_character=bible.character_identity or (intent.actors[0] if intent.actors else ""),
                required_location=bible.location or intent.location,
                required=[x for x in delta.must_persist if x.strip()],
            )
            cont_issues = tracker.validate_pre_generation(intent, constraints=constraints)
            critical = [
                i
                for i in (cont_issues or [])
                if getattr(i, "severity", "").upper() in ("CRITICAL", "ERROR", "BLOCK")
            ]
            if critical:
                issues.append("continuity_preflight_blocked")
                for i in critical[:5]:
                    issues.append(f"continuity:{getattr(i, 'code', 'issue')}")
        except Exception as exc:
            issues.append(f"continuity_preflight_error:{type(exc).__name__}")

    # Reference assets — IDs only (no duplication)
    refs = list(reference_asset_ids or bible.reference_asset_ids or [])
    for rid in refs:
        if not str(rid).strip():
            issues.append("invalid_reference_asset_id")

    blocked = bool(issues)
    return sanitize_visual_metadata(
        {
            "ok": not blocked,
            "blocked": blocked,
            "issues": issues,
            "visual_mode": mode,
            "mode_reason": mode_info.get("reason"),
            "seed": seed_info,
            "image_motion": image_motion_capability(),
            "continuity_authority": "pipeline.visual_semantic.continuity.ContinuityTracker",
            "quality_observation_boundary": "artifact_verification + BUILD-04F (not this module)",
            "reference_asset_ids": refs,
        }
    )


def localization_safe_bible_check(
    master: VisualBible,
    language_a_bible: VisualBible,
    language_b_bible: VisualBible,
) -> dict[str, Any]:
    """Visual identity must remain equivalent across languages (bible core fields)."""
    core_fields = (
        "subject_identity",
        "character_identity",
        "object_identity",
        "environment",
        "location",
        "architecture",
        "wardrobe",
        "props",
        "era",
        "geography",
        "visual_style",
        "lighting",
        "color_direction",
        "camera_language",
        "framing",
        "visual_realism",
    )
    diffs = []
    for f in core_fields:
        a = str(getattr(language_a_bible, f, "") or "")
        b = str(getattr(language_b_bible, f, "") or "")
        m = str(getattr(master, f, "") or "")
        if a != m or b != m:
            diffs.append(f)
    return {
        "ok": not diffs,
        "equivalent": not diffs,
        "differing_fields": diffs,
        "note": "narration/subtitle/localized_visual_text may change; Visual Bible core must not",
    }


def mark_localized_visual_text(text: str, language: str) -> dict[str, Any]:
    """Explicit marker — never silently translate visual text inside prompts."""
    return {
        "text": str(text or ""),
        "language": str(language or "").strip().lower(),
        "kind": "LOCALIZED_VISUAL_TEXT",
        "note": "must not alter unrelated visual identity",
    }


def build_visual_lineage(
    *,
    bible: VisualBible,
    contract: SceneVisualContract,
    provider: str = "",
    model: str = "",
    seed_info: Optional[dict[str, Any]] = None,
    reference_asset_ids: Optional[Sequence[str]] = None,
    prompt_fingerprint: str = "",
) -> dict[str, Any]:
    """Lineage metadata for existing artifact/provenance stores — no second asset DB."""
    return sanitize_visual_metadata(
        {
            "visual_bible_id": bible.bible_id,
            "visual_bible_version": bible.version,
            "scene_contract_id": contract.contract_id,
            "scene_contract_version": contract.version,
            "scene_id": contract.scene_id,
            "dialogue_id": contract.dialogue_id,
            "visual_mode": contract.visual_mode,
            "prompt_fingerprint": prompt_fingerprint or contract.prompt_fingerprint,
            "intent_fingerprint": contract.intent_fingerprint,
            "provider": provider,
            "model": model,
            "seed": seed_info or seed_status_for_provider(provider),
            "reference_asset_ids": list(reference_asset_ids or bible.reference_asset_ids or []),
            "asset_database": "existing_visual_provenance_only",
        }
    )


def agnes_integration_status() -> dict[str, Any]:
    """How Agnes consumes IMAGE / IMAGE_WITH_MOTION / VIDEO decisions later."""
    try:
        from pipeline.idempotency import agnes_bridge  # noqa: F401

        present = True
        path = "pipeline.idempotency.agnes_bridge"
    except Exception:
        present = False
        path = ""
    return {
        "agnes_adapter_present": present,
        "adapter": path,
        "mode_mapping": {
            MODE_IMAGE: GenerationMode.IMAGE_GENERATION.value,
            MODE_IMAGE_WITH_MOTION: GenerationMode.IMAGE_WITH_MOTION.value,
            MODE_VIDEO: GenerationMode.TEXT_TO_VIDEO.value,
        },
        "note": "C05-V declares mode; existing provider selection consumes GenerationMode — Agnes not rewritten",
        "offline_tests": "deterministic mocks only; paid APIs = 0",
    }
