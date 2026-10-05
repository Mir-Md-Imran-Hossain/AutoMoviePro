"""Stage discipline + prompt contracts (AMP-owned; OpenMontage-inspired methodology)."""
from __future__ import annotations

from typing import Any, Dict, List

MONTAGE_BRAIN_VERSION = "amp_montage_brain_v1"


def montage_stage_manifest(*, video_type: str = "short") -> Dict[str, Any]:
    """Executive production stages — mirror OM discipline without AGPL code."""
    vt = (video_type or "short").lower()
    return {
        "name": "amp-documentary-montage",
        "version": MONTAGE_BRAIN_VERSION,
        "video_type": vt,
        "policy": "retrieval_aware_video_primary",
        "stages": [
            {
                "id": "idea",
                "job": "One thematic question + tone + duration + retention spine",
                "success": ["concrete_topic", "curiosity_gap", "seo_title_angle"],
            },
            {
                "id": "scene_plan",
                "job": "Concrete visual SLOTS (noun+adjective+action) with 2–3 search queries each",
                "success": ["slot_queries", "hero_slots>=2", "no_abstract_labels"],
            },
            {
                "id": "assets",
                "job": "Fill slots: Agnes VIDEO primary; stock retrieval when query-matched; Ken Burns only if authorized",
                "success": ["visual_mode_provenance", "asset_or_generation_path"],
            },
            {
                "id": "edit",
                "job": "Arrange beats by narrative role; no flat encyclopedia chains; payoff cadence",
                "success": ["retention_roles", "continuity_bridge"],
            },
            {
                "id": "compose",
                "job": "Mux audio+picture; aspect lock; no black tails; ship gates",
                "success": ["duration_contract", "av_sync", "publishability"],
            },
            {
                "id": "review",
                "job": "Prompt-compliance + semantic coverage + observation gates",
                "success": ["PROMPT_COMPLIANCE_AUDIT", "no_silent_image_downgrade"],
            },
        ],
        "openmontage_agpl_imported": False,
        "note": "Methodology inspired by public OpenMontage docs; AMP-owned implementation only",
    }


def montage_discipline_prompt_block(*, max_seconds: int = 60, video_type: str = "short") -> str:
    """Inject into director/script API prompts — location-scout language, not stock labels."""
    return f"""
DOCUMENTARY MONTAGE DISCIPLINE (AMP montage brain — mandatory):
Think like a location scout, NOT a stock librarian.
- Bad slot: "space mood montage" / "science B-roll"
- Good slot: "gold hexagonal JWST mirror segment catching infrared under sunshield shadow, slow push-in"

For EVERY scene you MUST output (in quality_notes or fields):
1) slot_description: concrete nouns + adjectives + camera action (searchable)
2) search_queries: 2–3 short English queries for stock/AI retrieval
3) hero: true for at least 2 beats in a {video_type} (~{max_seconds}s) film
4) preferred_sources: agnes|pexels|nasa_ref|local (Agnes VIDEO is default primary)

Asset rule:
- Prefer real matched footage / Agnes VIDEO for motion beats.
- IMAGE_WITH_MOTION (Ken Burns) only for static plates (map, document, endcard, calligraphy).
- Never fill the whole film with stills.

Edit rule:
- Arrange beats as question → evidence → payoff → new question.
- Each beat introduces NEW visual information matching the spoken claim.
""".strip()


def montage_compose_checklist(plan: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Deterministic pre-compose checklist (observation, not publish authority)."""
    plan = dict(plan or {})
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    issues: List[str] = []
    hero = 0
    with_queries = 0
    video_modes = 0
    for s in scenes:
        slot = s.get("montage_slot") if isinstance(s.get("montage_slot"), dict) else {}
        if slot.get("hero") or s.get("hero"):
            hero += 1
        qs = slot.get("search_queries") or s.get("search_queries") or []
        if isinstance(qs, list) and len([q for q in qs if str(q).strip()]) >= 2:
            with_queries += 1
        mode = str(s.get("visual_mode") or "").upper()
        if mode == "VIDEO" or not mode:
            video_modes += 1
        desc = str(slot.get("slot_description") or s.get("visual_prompt") or "")
        if desc and len(desc.split()) < 4:
            issues.append("abstract_or_thin_slot_description")
    if scenes and hero < min(2, len(scenes)):
        issues.append("hero_slots_below_2")
    if scenes and with_queries < max(1, len(scenes) // 2):
        issues.append("insufficient_search_queries_on_slots")
    if scenes and video_modes == 0:
        issues.append("no_video_primary_beats")
    return {
        "ok": not issues,
        "issues": issues,
        "hero_count": hero,
        "slots_with_queries": with_queries,
        "video_mode_count": video_modes,
        "scene_count": len(scenes),
        "version": MONTAGE_BRAIN_VERSION,
    }
