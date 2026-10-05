"""Concrete retrieval slot planner — AMP-owned OpenMontage-style scene discipline."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[A-Za-z0-9]{3,}", text or "") if t.lower() not in {
        "the", "and", "for", "with", "from", "this", "that", "into", "over", "under"
    }]


def _concrete_slot_description(
    *,
    topic: str,
    narration: str,
    element: str,
    keywords: Sequence[str],
) -> str:
    kws = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    nouns = kws[:3] or _tokens(topic)[:3] or _tokens(narration)[:3]
    subject = " ".join(nouns) if nouns else (topic or element or "subject")
    el = (element or "beat").strip().lower()
    # Location-scout phrasing (searchable)
    action = {
        "intro": "slow cinematic push-in establishing hero",
        "discovery": "revealing detail with controlled camera move",
        "technique": "macro process detail, continuous motion",
        "legacy": "wide atmospheric hold then gentle drift",
        "outro": "closing hero plate with subtle Ken Burns drift",
        "context": "environmental wide into subject emphasis",
    }.get(el, "cinematic continuous motion matching spoken claim")
    narr_bit = " ".join((narration or "").split()[:12]).strip()
    if narr_bit:
        return f"{subject}: {narr_bit} — {action}"
    return f"{subject} — {action}, documentary lighting, exact subject on screen"


def _search_queries(topic: str, narration: str, keywords: Sequence[str], element: str) -> List[str]:
    base = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    topic_toks = _tokens(topic)[:4]
    narr_toks = _tokens(narration)[:4]
    q1 = " ".join((base[:2] or topic_toks[:2] or ["documentary"]) + [element or "cinematic"]).strip()
    q2 = " ".join((topic_toks[:3] or base[:3] or narr_toks[:3])).strip() or q1
    q3 = " ".join((narr_toks[:3] or topic_toks[:2] or ["b-roll"]) + ["documentary footage"]).strip()
    # Dedupe preserve order
    out: List[str] = []
    for q in (q1, q2, q3):
        ql = q.lower()
        if ql and ql not in {x.lower() for x in out}:
            out.append(q)
    return out[:3]


def enrich_plan_with_montage_slots(plan: Dict[str, Any] | None) -> Dict[str, Any]:
    """Attach montage_slot to every scene (concrete description + queries + hero)."""
    plan = dict(plan or {})
    topic = str(plan.get("topic") or plan.get("title") or "").strip()
    scenes = list(plan.get("scenes") or [])
    n = len(scenes)
    # Hero beats: first + a mid payoff (OpenMontage-style ≥2 heroes)
    hero_idxs = {0}
    if n >= 3:
        hero_idxs.add(min(n - 1, max(1, n // 2)))
    if n >= 5:
        hero_idxs.add(min(n - 2, 2))

    out: List[Dict[str, Any]] = []
    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            out.append(sc)
            continue
        row = dict(sc)
        narr = str(row.get("narration") or row.get("text") or "").strip()
        element = str(row.get("element") or "beat").strip()
        kws = row.get("keyword_triggers") or []
        if not isinstance(kws, list):
            kws = [str(kws)]
        existing = row.get("montage_slot") if isinstance(row.get("montage_slot"), dict) else {}
        desc = str(existing.get("slot_description") or "").strip() or _concrete_slot_description(
            topic=topic,
            narration=narr,
            element=element,
            keywords=kws,
        )
        queries = existing.get("search_queries") or row.get("search_queries")
        if not isinstance(queries, list) or len(queries) < 2:
            queries = _search_queries(topic, narr, kws, element)
        hero = bool(existing.get("hero")) if "hero" in existing else (i in hero_idxs)
        preferred = str(existing.get("preferred_sources") or row.get("preferred_sources") or "agnes,pexels").strip()
        slot = {
            "slot_description": desc,
            "search_queries": [str(q).strip() for q in queries if str(q).strip()][:3],
            "hero": hero,
            "preferred_sources": preferred,
            "beat_index": i,
        }
        row["montage_slot"] = slot
        row["search_queries"] = list(slot["search_queries"])
        row["hero"] = hero
        # Strengthen visual_query for retrieval/Agnes when thin
        if not str(row.get("visual_query") or "").strip() or len(str(row.get("visual_query")).split()) < 3:
            row["visual_query"] = slot["search_queries"][0] if slot["search_queries"] else topic
        # Keep exact_ai_video_prompt grounded in concrete slot language
        exact = str(row.get("exact_ai_video_prompt") or "").strip()
        if exact and "slot:" not in exact.lower():
            row["exact_ai_video_prompt"] = f"{exact} Visual slot: {desc}."
        elif not exact:
            row["exact_ai_video_prompt"] = (
                f"cinematic documentary shot of {desc}, continuous motion, "
                f"exact subject on screen, no burned captions, no talking-head"
            )
        out.append(row)
    plan["scenes"] = out
    meta = dict(plan.get("metadata") or {})
    meta["montage_slots_enriched"] = True
    meta["montage_brain_version"] = "amp_montage_brain_v1"
    plan["metadata"] = meta
    return plan


def slot_search_queries_for_scene(scene: Dict[str, Any] | None, *, topic: str = "") -> List[str]:
    sc = dict(scene or {})
    slot = sc.get("montage_slot") if isinstance(sc.get("montage_slot"), dict) else {}
    qs = slot.get("search_queries") or sc.get("search_queries") or []
    if isinstance(qs, list) and qs:
        return [str(q).strip() for q in qs if str(q).strip()][:4]
    return _search_queries(
        topic or str(sc.get("product_name") or ""),
        str(sc.get("narration") or ""),
        sc.get("keyword_triggers") or [],
        str(sc.get("element") or ""),
    )
