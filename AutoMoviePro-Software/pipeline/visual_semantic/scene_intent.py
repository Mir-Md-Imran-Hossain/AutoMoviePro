"""Build SceneIntent from existing Scene / dialogue sources."""
from __future__ import annotations

import re
from typing import Any, Optional

from domain.scene import Scene, VisualPlan
from domain.scene_intent import AudioIntent, LocalizationIntent, SceneIntent, SubtitleIntent, TemporalAction


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]{3,}", (text or "").lower())


def _extract_primary_action(narration: str, shot_action: str = "") -> str:
    if shot_action.strip():
        return shot_action.strip()
    narr = (narration or "").strip()
    for pat in (
        r"\b(drinks?|drinking)\b",
        r"\b(eats?|eating)\b",
        r"\b(cuts?|cutting)\b",
        r"\b(walks?|walking)\b",
        r"\b(sits?|sitting)\b",
        r"\b(stands?|standing)\b",
        r"\b(holds?|holding)\b",
    ):
        m = re.search(pat, narr.lower())
        if m:
            return m.group(1)
    return narr.split(".")[0].strip()[:120] if narr else ""


def build_scene_intent_from_dialogue(
    *,
    scene_id: str,
    dialogue_id: str,
    narration: str,
    script_id: str = "",
    visual_prompt: str = "",
    visual_query: str = "",
    shot: Optional[dict[str, Any]] = None,
    visual_evidence: Optional[dict[str, Any]] = None,
    continuity: Optional[dict[str, Any]] = None,
    continuity_expected: bool = True,
    narrative_change_allowed: bool = False,
    **extra: Any,
) -> SceneIntent:
    """Derive SceneIntent from dialogue + visual plan fields (shared semantic source)."""
    shot = shot or {}
    ev = visual_evidence or {}
    cont = continuity or {}
    primary = _extract_primary_action(narration, str(shot.get("action") or ""))
    summary = (narration or "").strip()[:300]
    location = str(shot.get("environment") or cont.get("location") or "").strip()
    posture = str(cont.get("posture") or shot.get("posture") or "").strip()
    required = [str(x).strip().lower() for x in (ev.get("must_show") or []) if str(x).strip()]
    forbidden = [str(x).strip().lower() for x in (ev.get("must_not_show") or []) if str(x).strip()]
    optional = [str(x).strip().lower() for x in (ev.get("should_show") or []) if str(x).strip()]

    # Infer required objects from primary action (heuristic, labeled in metadata)
    action_objects = {
        "drink": ["tea", "cup", "mug"],
        "drinking": ["tea", "cup", "mug"],
        "eat": ["food", "plate"],
        "eating": ["food", "plate"],
        "cut": ["knife", "vegetable", "vegetables"],
        "cutting": ["knife", "vegetable", "vegetables"],
    }
    pa_lower = primary.lower()
    for key, objs in action_objects.items():
        if key in pa_lower:
            for o in objs:
                if o not in required:
                    required.append(o)

    action_order: list[TemporalAction] = []
    ordered_verbs = re.findall(
        r"\b(pick up|pickup|drink|drinks|drinking|put down|putdown|eat|eating|cut|cutting)\b",
        narration.lower(),
    )
    for i, verb in enumerate(ordered_verbs):
        action_order.append(TemporalAction(action=verb, order=i, relation="sequential"))

    from pipeline.multimodal_consistency.entity_grounding import infer_phone_camera_entities

    entities, relations = infer_phone_camera_entities(narration, str(shot.get("subject") or ""))
    neg_constraints: list[str] = []
    if entities:
        neg_constraints.extend(["external DSLR camera", "broadcast camera", "cinema camera"])

    return SceneIntent(
        scene_id=scene_id,
        dialogue_id=dialogue_id,
        script_id=script_id,
        summary=summary,
        primary_action=primary,
        entities=entities,
        relations=relations,
        negative_constraints=neg_constraints,
        actors=[str(shot.get("subject") or "subject").strip()] if shot.get("subject") else [],
        location=location,
        environment=location,
        posture=posture,
        interaction_surface=str(cont.get("interaction_surface") or "").strip(),
        required_objects=required[:12],
        optional_objects=optional[:12],
        forbidden_objects=forbidden[:12],
        emotional_intent=str(extra.get("emotional_intent") or "").strip(),
        visual_emphasis=str(visual_prompt or visual_query or "")[:200],
        action_order=action_order,
        continuity_expected=continuity_expected,
        continuity_refs=dict(cont),
        narrative_change_allowed=narrative_change_allowed,
        audio_intent=AudioIntent(
            language=str(extra.get("language") or "en"),
            emotion=str(extra.get("emotion") or ""),
            duration_target_sec=extra.get("duration_target_sec"),
        ),
        subtitle_intent=SubtitleIntent(language=str(extra.get("language") or "en")),
        localization_intent=LocalizationIntent(
            source_language=str(extra.get("language") or "en"),
            semantic_events=ordered_verbs,
        ),
        metadata={"builder": "dialogue_shared_source", "heuristic": True},
    )


def build_scene_intent_from_scene(scene: Scene) -> SceneIntent:
    """Build SceneIntent from canonical Scene + VisualPlan."""
    vp: Optional[VisualPlan] = scene.visual_plan
    narr = scene.primary_claim or ""
    shot_dict: dict[str, Any] = {}
    ev_dict: dict[str, Any] = {}
    cont: dict[str, Any] = {}
    vprompt = ""
    if vp:
        shot_dict = vp.shot.model_dump() if hasattr(vp.shot, "model_dump") else dict(vp.shot)  # type: ignore[arg-type]
        ev_dict = vp.evidence.model_dump() if hasattr(vp.evidence, "model_dump") else {}
        cont = dict(vp.continuity or {})
        vprompt = str(vp.prompt_reference or "")
    scene_id = str(scene.legacy_scene_id if scene.legacy_scene_id is not None else scene.scene_index)
    return build_scene_intent_from_dialogue(
        scene_id=scene_id,
        dialogue_id=str(scene.dialogue_id or ""),
        narration=narr,
        script_id=str(scene.script_id or ""),
        visual_prompt=vprompt,
        shot=shot_dict,
        visual_evidence=ev_dict,
        continuity=cont,
    )


def intent_fingerprint(intent: SceneIntent) -> str:
    from pipeline.idempotency.fingerprint import hash_text

    payload = "|".join(
        [
            intent.scene_id,
            intent.dialogue_id,
            intent.primary_action.lower(),
            intent.location.lower(),
            intent.posture.lower(),
            intent.purpose.lower(),
            intent.shot_type.lower(),
            intent.shot_purpose.lower(),
            ",".join(sorted(intent.required_objects)),
            ",".join(sorted(intent.forbidden_objects)),
            ",".join(sorted(intent.negative_constraints))[:400],
        ]
    )
    return hash_text(payload)[:16]
