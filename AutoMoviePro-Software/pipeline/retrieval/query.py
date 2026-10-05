"""Build retrieval queries from C05-S DirectedVisualBeat — keep entities/relations."""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence, Union

from pipeline.retrieval.common import HEURISTIC


def _as_beat_dict(beat: Any) -> dict[str, Any]:
    if beat is None:
        return {}
    if isinstance(beat, Mapping):
        return dict(beat)
    if hasattr(beat, "to_dict"):
        return dict(beat.to_dict())
    return dict(getattr(beat, "__dict__", {}) or {})


def _entity_labels(ents: Sequence[Any]) -> list[str]:
    out: list[str] = []
    for e in ents or []:
        if isinstance(e, Mapping):
            lab = str(e.get("label") or e.get("name") or e.get("identity") or "").strip()
        else:
            lab = str(getattr(e, "label", "") or getattr(e, "name", "") or "").strip()
        if lab and lab not in out:
            out.append(lab)
    return out


def _relation_phrases(rels: Sequence[Any]) -> list[str]:
    out: list[str] = []
    for r in rels or []:
        if isinstance(r, Mapping):
            a = str(r.get("subject") or r.get("from_entity") or r.get("a") or "").strip()
            rel = str(r.get("relation") or r.get("predicate") or r.get("type") or "").strip()
            b = str(r.get("object") or r.get("to_entity") or r.get("b") or "").strip()
        else:
            a = str(getattr(r, "subject", "") or getattr(r, "from_entity", "") or "").strip()
            rel = str(getattr(r, "relation", "") or getattr(r, "predicate", "") or "").strip()
            b = str(getattr(r, "object", "") or getattr(r, "to_entity", "") or "").strip()
        phrase = " ".join(x for x in (a, rel, b) if x).strip()
        if phrase and phrase not in out:
            out.append(phrase)
    return out


def build_retrieval_query(
    beat: Any,
    *,
    scene_intent: Optional[Mapping[str, Any]] = None,
    visual_contract: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """
    Compose a rich natural-language query from directed beat fields.
    Must not collapse to a single location token when entities/relations exist.
    """
    b = _as_beat_dict(beat)
    intent = dict(scene_intent or {})
    contract = dict(visual_contract or {})

    char = dict(b.get("character_state") or {})
    loc = dict(b.get("location_state") or {})
    env = dict(b.get("environment_state") or {})

    subject = (
        str(char.get("identity") or char.get("subject") or "").strip()
        or (str((intent.get("actors") or [""])[0]).strip() if intent.get("actors") else "")
    )
    action = str(char.get("action") or intent.get("primary_action") or "").strip()
    location = str(loc.get("location") or intent.get("location") or "").strip()
    environment = str(env.get("environment") or intent.get("environment") or "").strip()
    camera = str(b.get("camera_intent") or intent.get("shot_type") or "").strip()
    lighting = str(b.get("lighting_intent") or "").strip()
    emotion = str(b.get("emotional_visual_intent") or intent.get("emotional_intent") or "").strip()
    composition = str(b.get("composition") or intent.get("framing") or "").strip()

    entities = _entity_labels(b.get("required_entities") or intent.get("entities") or [])
    objects = [str(x).strip() for x in (b.get("required_objects") or intent.get("required_objects") or []) if str(x).strip()]
    relationships = _relation_phrases(b.get("relationships") or intent.get("relations") or [])

    # Visual contract may carry must_appear
    if contract:
        must = contract.get("must_appear") or (contract.get("delta") or {}).get("must_appear") or []
        for m in must:
            s = str(m).strip()
            if s and s not in objects:
                objects.append(s)

    parts: list[str] = []
    if subject and action and any(relationships):
        # Prefer relationship-aware sentence
        parts.append(f"{subject} {relationships[0]}")
        if location:
            parts.append(f"at {location}" if not location.lower().startswith(("at ", "in ", "outside")) else location)
    elif subject and action:
        parts.append(f"{subject} {action}")
        if objects:
            parts.append(f"with {', '.join(objects[:4])}")
        if location:
            parts.append(f"at {location}" if not location.lower().startswith(("at ", "in ", "outside", "beside")) else location)
    else:
        if subject:
            parts.append(subject)
        if action:
            parts.append(action)
        for rel in relationships[:2]:
            parts.append(rel)
        for o in objects[:4]:
            parts.append(o)
        if location:
            parts.append(location)

    if environment and environment.lower() not in " ".join(parts).lower():
        parts.append(environment)
    if camera:
        parts.append(f"camera {camera.lower()}")
    if lighting:
        parts.append(f"lighting {lighting}")
    if emotion:
        parts.append(f"mood {emotion}")
    if composition:
        parts.append(composition)

    query_text = " ".join(p for p in parts if p).strip()
    # Guard: never allow location-only when richer fields exist
    location_only = bool(location) and query_text.lower().strip() in {
        location.lower(),
        f"at {location.lower()}",
        f"in {location.lower()}",
    }
    rich_available = bool(subject or action or entities or relationships or objects)
    if location_only and rich_available:
        # Force enrichment
        enrich = [subject, action] + entities[:3] + relationships[:2] + objects[:3]
        query_text = " ".join(x for x in enrich if x)
        if location:
            query_text = f"{query_text} at {location}".strip()

    visual_mode = str(b.get("visual_mode") or intent.get("visual_mode") or "IMAGE").upper()
    preferred_media = "video" if visual_mode == "VIDEO" else "image"

    return {
        "query_text": query_text,
        "subject": subject,
        "entities": entities,
        "relationships": relationships,
        "objects": objects,
        "action": action,
        "location": location,
        "environment": environment,
        "camera": camera,
        "lighting": lighting,
        "emotion": emotion,
        "composition": composition,
        "visual_mode": visual_mode,
        "preferred_media_type": preferred_media,
        "beat_id": str(b.get("beat_id") or ""),
        "scene_id": str(b.get("scene_id") or intent.get("scene_id") or ""),
        "confidence": HEURISTIC,
        "location_only_blocked": bool(rich_available),
        "schema": "amp_retrieval_query_v1",
    }
