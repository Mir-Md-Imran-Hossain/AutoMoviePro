from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


DIRECTOR_SYSTEM = """
You are AutoMovie Pro Industrial Niche Director — elite short/long-form cinematic showrunner.
Your job: world-class, SEO-honest, retention-first English master scripts.
The SCRIPT is the soul of the video — never flat encyclopedia narration.
Every video MUST:
1. 0–3s PATTERN INTERRUPT: Scroll-stopping hook that poses an anomaly, high-stakes question, or counterintuitive claim.
2. STRICTLY FORBIDDEN IN SPOKEN DIALOGUE: "Welcome back", "In this video", "Hello everyone", "Hey guys", "Without further ado", "Let's dive in", "Delve", "Landscape", "Tapestry", "Game-changer", "Revolutionize", dictionary definitions, academic preambles, and empty subscribe pleas.
3. 15–20s CURIOSITY CADENCE: Re-hook with contrast or new tension ("What most viewers overlook", "Why this changes the outcome", "Look what happens next").
4. TIMED PAYOFFS & CLOSED ENDING: Settle the core curiosity loop with evidence before closing on a definitive takeaway.
5. 100% VISUAL-DIALOGUE MATCH: Every spoken entity, mechanism, or scene MUST have tightly matched B-roll prompts and queries.
Spoken language: natural, conversational English (the locked picture+audio MASTER).
Product/model names stay in English. Do NOT write Bangla/Hindi/Urdu/Tamil/Malayalam
narration — those languages are added later by replacing audio and subtitles only.
For gadget niches: NEVER pick a product already on the BLOCKLIST.
Return STRICT JSON only — no markdown.
"""

ELEMENT_GUIDE = """
Element → dialogue job → footage must show:
- intro: PATTERN INTERRUPT hook + open loop + product/topic identity → hero establish shot
- design: build, materials, ports, buttons, colors → macro pans (NEW info / re-hook)
- display: brightness, scroll, outdoor → screen ON with real UI
- camera: lenses, samples, night → camera module macro OR sample metaphor
- processor: speed, heat, gaming → chipset / performance B-roll
- battery: endurance, charge speed → charging cable, battery %
- sound: speakers/earbuds ANC, bass → earbuds, case, waveform
- fit / case / software / price / pros_cons: match spoken claim with a fresh takeaway
- outro: CLOSE the main open loop + memorable closing noun (not empty CTA)
- context / discovery / technique / legacy: non-gadget story beats with question→evidence→payoff
- hook / metaphor / reveal: keyword-driven cinematic metaphor that advances retention
Pick ONLY elements that fit the niche. Never force camera on earbuds.
"""

NICHE_STYLE_PACKS = {
    "gadget": {
        "grade": "premium studio rim light, clean desk, sharp macro product",
        "metaphors": "exact device hero, ports, screen UI, charging glow",
        "faces": "no talking-head; hands OK only if product is clear; prefer product-only",
        "forbidden": "generic wrong phone, city lifestyle without product, lip-sync avatar",
    },
    "science": {
        "grade": "teal/cyan cinematic lab grade, high contrast, shallow DOF",
        "metaphors": "molecular glass, chemical plume, macro flame, egg under heat, lab glassware",
        "faces": "silent cinematic humans OK; no talking-head lip-sync",
        "forbidden": "cartoon science, stock office filler, watermarks",
    },
    "mystery": {
        "grade": "dark teal-green eerie grade, dramatic side light",
        "metaphors": "locked book, sealed object, fire vs invulnerable shell, fog, sealed vault",
        "faces": "silent cinematic humans OK; no talking-head lip-sync",
        "forbidden": "jump-scare horror faces, meme overlays",
    },
    "history": {
        "grade": "desaturated filmic documentary grade, textured period light",
        "metaphors": "maps, relics, parchment, ruins silhouettes, artifact macros",
        "faces": "silent cinematic period humans OK; no talking-head",
        "forbidden": "modern phones in frame, anachronistic logos",
    },
    "islamic": {
        "grade": "warm golden serene ambient light, respectful spiritual mood",
        "metaphors": "calligraphy textures, mosque architecture exteriors, open book pages, light rays — faceless",
        "faces": "strictly faceless metaphors; no talking-head; no idols",
        "forbidden": "idols, disrespectful imagery, lip-sync avatar",
    },
    "motivation": {
        "grade": "warm sunrise cinematic lifestyle grade, shallow DOF",
        "metaphors": "notebook, city walk, clock, rising light, focused workspace",
        "faces": "silent cinematic humans OK; no talking-head lip-sync",
        "forbidden": "empty slogan overlays, meme text, stock handshake spam",
    },
    "health": {
        "grade": "clean clinical soft daylight, calm teal accents",
        "metaphors": "fresh food macros, water glass, stretch silhouette, sleep room",
        "faces": "faceless or distant silhouettes preferred; no medical gore",
        "forbidden": "miracle-cure claims visuals, graphic surgery",
    },
    "news": {
        "grade": "neutral documentary grade, crisp contrast",
        "metaphors": "maps, city B-roll, press room, timeline graphics as physical props",
        "faces": "crowd/wide shots OK; no fabricated politician lip-sync",
        "forbidden": "deepfake faces, sensational gore",
    },
    "finance": {
        "grade": "cool corporate blue cinematic grade",
        "metaphors": "coins, charts as physical paper, city skyline night, vault door",
        "faces": "faceless hands OK; no talking-head guru",
        "forbidden": "guaranteed-profit overlays, crypto moon memes",
    },
    "nature": {
        "grade": "natural earth tones, golden hour wildlife grade",
        "metaphors": "animal hero, biome wide shot, macro leaf/water, weather",
        "faces": "animals primary; humans only as tiny scale if needed",
        "forbidden": "zoo cage cruelty focus, text watermarks",
    },
    "true_crime": {
        "grade": "desaturated noir documentary, cold side light",
        "metaphors": "case files, evidence table, empty street night, clock, sealed door",
        "faces": "silhouettes only; never glorify violence",
        "forbidden": "graphic gore, exploitative victim close-ups",
    },
}


def niche_style_pack(niche: str, style_family: str = "") -> Dict[str, str]:
    fam = (style_family or "").strip().lower()
    if fam in NICHE_STYLE_PACKS:
        return NICHE_STYLE_PACKS[fam]
    n = (niche or "").lower()
    if any(x in n for x in ("islam", "deen", "quran", "muslim")):
        return NICHE_STYLE_PACKS["islamic"]
    if any(x in n for x in ("science", "physics", "chem", "space", "বিজ্ঞান")):
        return NICHE_STYLE_PACKS["science"]
    if any(x in n for x in ("true crime", "serial", "forensic", "murder")):
        return NICHE_STYLE_PACKS["true_crime"]
    if any(x in n for x in ("myster", "horror", "unexplain", "secret", "রহস্য")):
        return NICHE_STYLE_PACKS["mystery"]
    if any(x in n for x in ("histor", "war", "civilization", "ancient", "ইতিহাস")):
        return NICHE_STYLE_PACKS["history"]
    if any(x in n for x in ("motivat", "habit", "mindset", "self help")):
        return NICHE_STYLE_PACKS["motivation"]
    if any(x in n for x in ("health", "fitness", "nutrition", "sleep")):
        return NICHE_STYLE_PACKS["health"]
    if any(x in n for x in ("news", "geopolit", "politics")):
        return NICHE_STYLE_PACKS["news"]
    if any(x in n for x in ("financ", "invest", "crypto", "money")):
        return NICHE_STYLE_PACKS["finance"]
    if any(x in n for x in ("nature", "wildlife", "animal", "ocean")):
        return NICHE_STYLE_PACKS["nature"]
    if any(x in n for x in ("gadget", "tech", "phone", "review", "গ্যাজেট")):
        return NICHE_STYLE_PACKS["gadget"]
    return NICHE_STYLE_PACKS["history"]


def plan_niche_production(
    *,
    niche: str,
    channel_name: str,
    video_type: str,
    topic: str = "",
    research_notes: str = "",
    google_api_keys: Optional[List[str]] = None,
    openrouter_api: str = "",
    openrouter_keys: Optional[List[str]] = None,
    max_seconds: int = 120,
    blocked_products: Optional[List[str]] = None,
    channel_specials: Optional[Dict[str, str]] = None,
    niche_id: Optional[int] = None,
    niche_pack: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Strong AI setup for a niche:
    - pick/confirm a NON-DUPLICATE topic for this niche (Nish.Md topic prompt)
    - write English dialogue scenes matched to niche video prompt + style pack
    - for each dialogue: visual_query + visual_prompt + quality bar
    - lock English master (localization is a later pipeline stage)
    """
    from pipeline.nish_catalog import resolve_niche

    pack = niche_pack or resolve_niche(
        {"niche": niche, "niche_id": niche_id} if niche_id else niche
    )
    niche_name = str(pack.get("name") or niche or "Custom")
    family = str(pack.get("style_family") or "")
    topic_gen = str(pack.get("topic_generation_prompt") or "").strip()
    video_tmpl = str(pack.get("video_prompt") or "").strip()
    video_type_blurb = str(pack.get("video_type") or "").strip()

    from pipeline.duration_budget import scene_count_instruction

    scene_n = scene_count_instruction(max_seconds, video_type)
    blocked = blocked_products or []
    block_txt = "\n".join(f"- {b}" for b in blocked) if blocked else "(none)"
    specials = channel_specials or {}
    from pipeline.master_lang import (
        DIRECTOR_MASTER_LANGUAGE_RULES,
        lock_english_master_plan,
        rewrite_master_language_instructions,
    )

    specials = {
        k: rewrite_master_language_instructions(str(v or ""))
        for k, v in specials.items()
    }
    style = niche_style_pack(niche_name, family)
    is_gadget = family == "gadget" or style is NICHE_STYLE_PACKS["gadget"]
    topic_placeholder = topic.strip() if topic.strip() else "{topic}"
    video_prompt_filled = (
        video_tmpl.replace("{topic}", topic_placeholder)
        if video_tmpl
        else "(use niche style pack + AV rules below)"
    )
    from pipeline.prompt_engineering import (
        director_av_sync_rules,
        director_json_scene_example,
        industrial_topic_selection_rules,
    )

    av_rules = director_av_sync_rules(max_seconds=max_seconds, video_type=video_type)
    json_ex = director_json_scene_example(video_type=video_type).replace(
        "{style_pack}", family or ("gadget" if is_gadget else "history")
    ).replace("{nish_id}", str(int(pack.get("id") or 0)))
    try:
        from pipeline.montage_brain import montage_discipline_prompt_block

        montage_rules = montage_discipline_prompt_block(
            max_seconds=max_seconds, video_type=video_type
        )
    except Exception:
        montage_rules = ""
    prompt = f"""
{DIRECTOR_SYSTEM}

{montage_rules}

{DIRECTOR_MASTER_LANGUAGE_RULES}

Channel: {channel_name}
Niche ID: {pack.get("id") or niche_id or "custom"}
Niche: {niche_name}
Niche video type blurb: {video_type_blurb or "n/a"}
Style family: {family or "auto"}
Video type: {video_type} (HARD max {max_seconds}s spoken+visual runtime)
Forced topic (if any): {topic or "AUTO-SELECT"}
Research notes: {research_notes or "none"}
Channel video special: {specials.get("video_special") or video_type_blurb or "cinematic English documentary niche"}
Generation special: {specials.get("generation_special") or "one concrete claim per scene; seamless visual continuity; retention re-hooks every beat"}
Title/desc special: {specials.get("title_desc_special") or "SEO+CTR: concrete entity + curiosity angle + year; honest title promise"}

{industrial_topic_selection_rules()}

NISH TOPIC GENERATION PROMPT (follow when Forced topic is AUTO-SELECT):
{topic_gen or "Pick a viral SEO topic for this niche with high curiosity, concrete specificity, and a clear retention spine (hook → reveal → payoff)."}

NISH VIDEO PROMPT TEMPLATE (apply to EVERY scene; substitute the chosen topic for {{topic}}):
{video_prompt_filled}

NICHE STYLE PACK (must follow):
- Color grade: {style["grade"]}
- Metaphor vocabulary: {style["metaphors"]}
- Face policy: {style["faces"]}
- Forbidden: {style["forbidden"]}

BLOCKLIST — NEVER choose these products/topics or near-duplicates:
{block_txt}

{ELEMENT_GUIDE}

TOPIC RULES (strict):
1) Topic MUST be one concrete subject for niche "{niche_name}".
2) Gadget niches: exact product/model name required — NOT generic ("best phones").
3) Non-gadget niches: one concrete story/fact/topic title (not a vague listicle).
4) If Forced topic is set, use it ONLY if it is NOT on the blocklist and fits the niche.
5) If Forced topic is empty or blocked, AUTO-SELECT using the NISH TOPIC GENERATION PROMPT + industrial topic rules.
6) After choosing topic, rewrite every scene's exact_ai_video_prompt from the NISH VIDEO PROMPT TEMPLATE.
7) Chosen topic MUST support a retention spine you can state in analysis.retention_spine.

Need {scene_n}. First scene element=intro (pattern interrupt), last=outro (loop close).

{av_rules}

Honor Audio/Video Generation Prompt guidance from the Nish template (tone, continuity).
Total spoken length must fit ~{int(max_seconds * 0.92)} seconds across ALL scenes (more beats, not longer sentences).
CRITICAL API OUTPUT STANDARD: industrial-grade retention + SEO — flat/encyclopedia scripts are failures.

{json_ex}
"""
    data = None
    from pipeline.llm_router import (
        chat_text,
        extract_json_object,
        mark_google_pool_exhausted,
    )

    try:
        from pipeline.prompt_engineering import system_for_purpose

        hit = chat_text(
            prompt,
            purpose="script",
            system=system_for_purpose("director", json_mode=True, video_type=video_type),
            google_api_keys=google_api_keys or [],
            openrouter_api=openrouter_api,
            openrouter_keys=openrouter_keys,
            json_mode=True,
        )
        data = json.loads(extract_json_object(hit["text"]))
        data["director_provider"] = hit.get("provider")
        data["nish_id"] = int(pack.get("id") or 0)
        data["nish_name"] = niche_name
    except Exception as exc:
        logger.warning("director llm_router failed: %s", str(exc)[:200])
        if "limit: 0" in str(exc) or "free_tier" in str(exc):
            mark_google_pool_exhausted("director")
        data = None

    if data is None:
        data = _fallback_plan(
            niche,
            topic,
            video_type,
            max_seconds,
            channel_name,
            blocked_products=blocked,
        )

    data["video_type"] = video_type
    data["max_seconds"] = max_seconds
    data.setdefault("topic", topic or niche)
    data.setdefault("scenes", [])

    # If AI returned a blocked/duplicate topic, force fallback to a fresh product
    chosen = str(data.get("topic") or "").strip()
    if blocked and chosen and _is_blocked(chosen, blocked):
        logger.warning("Director returned blocked topic %r — forcing fresh fallback", chosen)
        data = _fallback_plan(
            niche,
            "",
            video_type,
            max_seconds,
            channel_name,
            blocked_products=blocked,
        )

    clean = []
    for s in data["scenes"]:
        if not isinstance(s, dict):
            continue
        narr = str(s.get("narration") or "").strip()
        if not narr:
            continue
        element = str(s.get("element") or "feature").strip().lower()
        vq = str(s.get("visual_query") or "").strip()
        vp = str(s.get("visual_prompt") or "").strip()
        if not vq:
            vq = f"{data['topic']} {element} product close up"
        if not vp:
            vp = f"cinematic {element} shot of {data['topic']}, studio lighting, sharp detail"
        kws = s.get("keyword_triggers") or []
        if not isinstance(kws, list):
            kws = [str(kws)]
        kws = [str(k).strip() for k in kws if str(k).strip()]
        if not kws:
            kws = _default_keywords(element, str(data.get("topic") or ""))
        topic_name = str(data.get("topic") or "")
        if topic_name and topic_name.lower() not in " ".join(kws).lower():
            kws = [topic_name] + kws
        exact = str(s.get("exact_ai_video_prompt") or "").strip()
        if not exact:
            exact = (
                f"vertical 9:16 cinematic {element} of {topic_name}. Keyword visuals: {', '.join(kws)}. "
                f"{style['grade']}. No burned captions, no watermark, no talking-head."
            )
        try:
            from pipeline.prompt_hardening import preflight_keyword_prompt

            pre = preflight_keyword_prompt(
                exact, keywords=kws, narration=narr, product_name=topic_name
            )
            exact = str(pre.get("fixed_prompt") or exact)
        except Exception:
            pass
        try:
            start_hint = float(s.get("start_hint_s") if s.get("start_hint_s") is not None else 0)
        except Exception:
            start_hint = 0.0
        try:
            end_hint = float(s.get("end_hint_s") if s.get("end_hint_s") is not None else start_hint + 8)
        except Exception:
            end_hint = start_hint + 8
        clean.append(
            {
                "element": element,
                "start_hint_s": start_hint,
                "end_hint_s": end_hint,
                "narration": narr,
                "keyword_triggers": kws,
                "exact_ai_video_prompt": exact,
                "visual_query": vq,
                "visual_prompt": vp,
                "retention_role": str(s.get("retention_role") or "").strip(),
                "open_loop": str(s.get("open_loop") or "").strip(),
                "payoff_for": str(s.get("payoff_for") or "").strip(),
                "quality_notes": str(
                    s.get("quality_notes") or "cinematic, sharp, keyword-matched, retention-aware, no watermark"
                ).strip(),
            }
        )
    data["scenes"] = clean or _enrich_scene_fields(
        _fallback_plan(
            niche, topic, video_type, max_seconds, channel_name, blocked_products=blocked
        )["scenes"],
        str(data.get("topic") or topic or niche),
        niche,
    )
    data.setdefault("analysis", {})
    if isinstance(data["analysis"], dict):
        data["analysis"].setdefault("style_pack", style)
    try:
        from pipeline.creative_production.script_quality import (
            enforce_dialogue_window_on_plan,
            enforce_opening_hook_on_plan,
            enforce_retention_cadence_on_plan,
        )
        from pipeline.media_mode_engine import enforce_video_primary_on_plan
        from pipeline.retention_architecture import attach_retention_to_plan

        data = enforce_opening_hook_on_plan(data)
        data = enforce_retention_cadence_on_plan(data)
        data = enforce_dialogue_window_on_plan(data)
        data = attach_retention_to_plan(data)
        data = enforce_video_primary_on_plan(data)
        from pipeline.montage_brain import apply_montage_brain_to_plan

        data = apply_montage_brain_to_plan(data, video_type=video_type)
    except Exception as exc:
        logger.warning("retention/hook/media-mode/montage enforce soft-fail: %s", exc)

    locked = lock_english_master_plan(
        data,
        google_api_keys=google_api_keys,
        openrouter_keys=openrouter_keys,
    )
    # FIX: LLM critic enabled when API keys are available — catches AI-sounding language
    # and subtle retention failures that rule-based checks miss.
    has_keys = bool((google_api_keys or []) or (openrouter_keys or []))
    try:
        from pipeline.creative_production.prompt_compliance_auditor import (
            PromptComplianceError,
            audit_script_prompt_compliance,
        )

        audit = audit_script_prompt_compliance(
            locked,
            job_id=str(locked.get("topic") or niche_name or "director")[:48],
            enable_llm_critic=has_keys,  # FIX: enabled when keys available
            repair=True,
            fail_closed=True,
            google_api_keys=google_api_keys,
            openrouter_keys=openrouter_keys,
        )
        locked = audit.get("plan") or locked
        score = audit.get("overall_score") or 0
        if score < 65:
            logger.warning(
                "prompt_compliance: LOW SCORE %s/100 for topic=%r — issues: %s",
                score,
                locked.get("topic"),
                audit.get("issues") or [],
            )
        locked["prompt_compliance"] = {
            "verdict": audit.get("verdict"),
            "overall_score": score,
            "industrial_grade": audit.get("industrial_grade"),
            "contract_version": audit.get("contract_version"),
            "repairs_applied": audit.get("repairs_applied") or [],
            "llm_critic_used": has_keys,
        }
    except PromptComplianceError:
        raise
    except Exception as exc:
        logger.warning("prompt compliance audit soft-fail in director: %s", exc)
    return locked


def _default_keywords(element: str, topic: str) -> List[str]:
    el = (element or "feature").lower()
    base = {
        "intro": ["hero", "unboxing", "product"],
        "design": ["macro", "chassis", "finish"],
        "display": ["screen", "brightness", "scroll"],
        "camera": ["lens", "macro", "camera module"],
        "battery": ["charging", "cable", "battery"],
        "sound": ["earbuds", "audio", "waveform"],
        "processor": ["chipset", "performance", "gaming"],
        "outro": ["hero", "spotlight", "endcard"],
        "hook": ["metaphor", "reveal", "cinematic"],
    }.get(el, [el, "cinematic", "close-up"])
    if topic:
        return [topic.split()[0], *base][:5]
    return base


def _enrich_scene_fields(
    scenes: List[Dict[str, Any]],
    topic: str,
    niche: str,
) -> List[Dict[str, Any]]:
    style = niche_style_pack(niche)
    out = []
    for i, s in enumerate(scenes):
        if not isinstance(s, dict):
            continue
        element = str(s.get("element") or "feature").strip().lower()
        vp = str(s.get("visual_prompt") or "").strip()
        kws = s.get("keyword_triggers") or _default_keywords(element, topic)
        if not isinstance(kws, list):
            kws = [str(kws)]
        kws = [str(k).strip() for k in kws if str(k).strip()]
        exact = str(s.get("exact_ai_video_prompt") or "").strip()
        if not exact:
            exact = (
                f"{vp or f'cinematic {element} of {topic}'}. "
                f"Keyword visuals: {', '.join(kws)}. {style['grade']}. "
                "No text, no watermark, no subtitles, no talking-head."
            )
        row = dict(s)
        row["keyword_triggers"] = kws
        row["exact_ai_video_prompt"] = exact
        row.setdefault("start_hint_s", float(i * 6))
        row.setdefault("end_hint_s", float(i * 6 + 8))
        out.append(row)
    return out


def _is_blocked(topic: str, blocked: List[str]) -> bool:
    try:
        from pipeline.product_registry import is_same_product

        return any(is_same_product(topic, b) for b in blocked)
    except Exception:
        t = topic.lower()
        return any(b.lower() in t or t in b.lower() for b in blocked if b)


def _pick_fresh_product(topic: str, niche: str, blocked: List[str]) -> str:
    pool = [
        "Google Pixel 9a",
        "OnePlus 13",
        "Xiaomi 15",
        "Sony WF-1000XM5",
        "Apple Watch Series 11",
        "DJI Osmo Pocket 3",
        "Steam Deck OLED",
        "Meta Quest 3S",
        "Samsung Galaxy Watch Ultra",
        "Anker Soundcore Liberty 4 Pro",
        "Asus ROG Ally X",
        "GoPro Hero 13 Black",
        "Lenovo Legion Go S",
        "CMF Phone 2 Pro",
        "Realme GT 7 Pro",
    ]
    if topic and not _is_blocked(topic, blocked):
        return topic
    for p in pool:
        if not _is_blocked(p, blocked):
            return p
    # last resort: append variant marker unlikely to collide
    return f"CMF Buds 2 Plus"


def _pick_history_topic(topic: str, niche: str, blocked: List[str]) -> str:
    pool = [
        "Lost Library of Alexandria",
        "Terracotta Army of Qin",
        "Gobekli Tepe temples",
        "Moche sacrifice rituals",
        "Antikythera Mechanism",
        "Nazca Lines desert glyphs",
        "Great Pyramid of Khufu",
        "Indus Valley seals",
        "Minoan palace of Knossos",
        "Olmec colossal heads",
        "Angkor Wat hydraulic system",
        "Chaco Canyon skywatchers",
    ]
    if topic and not _is_blocked(topic, blocked):
        # Reject gadget-like seeds even if caller passed them
        tl = topic.lower()
        if not any(
            x in tl
            for x in (
                "sony",
                "iphone",
                "samsung",
                "xiaomi",
                "earbuds",
                "pixel",
                "galaxy",
                "buds",
            )
        ):
            return topic
    for p in pool:
        if not _is_blocked(p, blocked):
            return p
    return f"{pool[0]} — new excavation notes"


def _fallback_history_plan(
    niche: str,
    topic: str,
    video_type: str,
    max_seconds: int,
    channel_name: str,
    blocked: Optional[List[str]] = None,
) -> Dict[str, Any]:
    from pipeline.dialogue_uniqueness import HISTORY_ELEMENTS

    subject = _pick_history_topic(topic or "", niche, blocked or [])
    beats = [
        (
            "intro",
            f"Tonight we dig into {subject} — a vanished world still rewriting what we think we know.",
            f"{subject} archaeological site aerial documentary",
            f"cinematic aerial of {subject} ruins at golden hour, documentary grade",
        ),
        (
            "context",
            f"Centuries before modern cities, people at {subject} engineered belief, power, and survival into stone.",
            f"{subject} ancient civilization historical context",
            f"atmospheric reconstruction vibe for {subject}, continuous camera drift",
        ),
        (
            "discovery",
            f"When excavators uncovered {subject}, every tool mark forced a harder question about who built it.",
            f"{subject} excavation trench artifacts",
            f"close documentary shot of excavation soil layers near {subject}",
        ),
        (
            "technique",
            f"The technique behind {subject} was not luck — measured cuts, aligned skies, and patient labor.",
            f"{subject} stone carving masonry technique",
            f"macro stone joints and tooling marks at {subject}",
        ),
        (
            "culture",
            f"Culture around {subject} left rituals, symbols, and social ranks you can still read in the ruins.",
            f"{subject} ritual artifacts temple culture",
            f"museum-lit artifacts tied to {subject}, slow push-in",
        ),
        (
            "mystery",
            f"And the mystery of {subject} remains: how much of the story is still buried under sand and silence?",
            f"{subject} unsolved archaeological mystery",
            f"foggy dawn over unfinished excavation of {subject}",
        ),
        (
            "outro",
            f"If {subject} surprised you, stay with {channel_name} — the next dig may rewrite the map again.",
            f"{subject} final wide cinematic ruins endcard",
            f"wide endcard hold over {subject} ruins, soft spotlight",
        ),
    ]
    if video_type == "short":
        beats = beats[:5] + [beats[-1]]
    scenes = [
        {
            "element": el,
            "narration": narr,
            "visual_query": vq,
            "visual_prompt": vp,
            "quality_notes": "history documentary beat — no modern gadgets",
        }
        for el, narr, vq, vp in beats
    ]
    title = f"{subject}: What Archaeology Still Can't Explain"
    return {
        "topic": subject,
        "title": title,
        "description": f"{title}\n\n#AncientHistory #Archaeology #Documentary",
        "tags": [subject, niche, "ancient history", "archaeology", "2026"],
        "scenes": _pad_scenes_to_budget(scenes, max_seconds, video_type, subject, niche=niche),
        "director_provider": "fallback_history_director",
        "style_family": "history",
        "max_seconds": max_seconds,
        "video_type": video_type,
    }


def _fallback_space_science_plan(
    niche: str,
    topic: str,
    video_type: str,
    max_seconds: int,
    channel_name: str,
) -> Dict[str, Any]:
    """Documentary fallback for space/science niches — never archaeology/gadget templates."""
    subject = (topic or "deep-space exploration").strip() or "deep-space exploration"
    beats = [
        (
            "intro",
            f"Most people think {subject} is just pretty pictures — the instruments prove otherwise. Watch this.",
            f"{subject} spacecraft documentary hero",
            f"cinematic documentary view of spacecraft hardware for {subject}, deep space backdrop",
        ),
        (
            "context",
            f"Artemis II sends a crewed Orion around the Moon on a free-return path, proving the stack before landing attempts.",
            f"Orion capsule SLS stack Artemis II",
            f"Orion capsule atop SLS, documentary lighting, no fictional UI",
        ),
        (
            "heat_shield",
            f"Orion's heat shield must survive lunar-return plasma; engineers treat every tile and seam as a life-critical surface.",
            f"Orion heat shield ablative tiles close up",
            f"close documentary shot of Orion heat shield tiles and seams",
        ),
        (
            "boosters",
            f"Twin solid rocket boosters and core engines lift the crew clear of Earth before the translunar injection burn.",
            f"SLS solid rocket booster launch documentary",
            f"SLS boosters igniting at liftoff, documentary telephoto clarity",
        ),
        (
            "trajectory",
            f"The free-return trajectory loops around the Moon and brings Orion home even if the main engine stays quiet.",
            f"Moon free-return trajectory diagram space documentary",
            f"clear lunar free-return path visualization, calm educational motion",
        ),
        (
            "payoff",
            f"That combination — heat shield, boosters, and free-return geometry — is why Artemis II flies humans around the Moon again.",
            f"Orion approaching Moon limb documentary",
            f"Orion approaching the lunar limb, high-contrast documentary grade",
        ),
        (
            "outro",
            f"If {subject} changed how you see crewed lunar flight, stay with {channel_name} for the next deep-space briefing.",
            f"{subject} final wide space documentary endcard",
            f"wide endcard over cislunar space with soft spotlight hold",
        ),
    ]
    if video_type == "short":
        beats = beats[:5] + [beats[-1]]
    scenes = [
        {
            "element": el,
            "narration": narr,
            "visual_query": vq,
            "visual_prompt": vp,
            "quality_notes": "space science documentary beat — real mission hardware",
        }
        for el, narr, vq, vp in beats
    ]
    title = f"{subject}: Crewed Lunar Flight Explained"
    return {
        "topic": subject,
        "title": title,
        "description": f"{title}\n\n#SpaceScience #Artemis #Documentary",
        "tags": [subject, niche, "space science", "artemis", "2026"],
        "scenes": _pad_scenes_to_budget(scenes, max_seconds, video_type, subject, niche=niche),
        "director_provider": "fallback_space_science_director",
        "style_family": "science",
        "max_seconds": max_seconds,
        "video_type": video_type,
    }


def _niche_is_space_science(niche: str) -> bool:
    n = (niche or "").lower()
    return any(
        tok in n
        for tok in (
            "space",
            "science",
            "astronomy",
            "nasa",
            "cosmos",
            "astrophys",
            "planet",
            "rocket",
            "satellite",
        )
    )


def _detect_niche_family(niche: str, topic: str = "") -> str:
    combined = f"{niche} {topic}".lower()
    if any(x in combined for x in ("islam", "deen", "quran", "muslim", "hadith", "sunnah")):
        return "islamic"
    if any(x in combined for x in ("financ", "invest", "crypto", "money", "wealth", "stock", "trading", "budget")):
        return "finance"
    if any(x in combined for x in ("health", "fitness", "nutrition", "diet", "sleep", "workout", "gym", "medical", "doctor")):
        return "health"
    if any(x in combined for x in ("motivat", "habit", "mindset", "discipline", "self help", "productivity", "stoic")):
        return "motivation"
    if any(x in combined for x in ("space", "astronomy", "nasa", "cosmos", "astrophys", "physics", "science", "chemistry", "biology", "বিজ্ঞান")):
        return "science"
    if any(x in combined for x in ("true crime", "serial", "forensic", "murder", "detective", "investigation", "case file")):
        return "true_crime"
    if any(x in combined for x in ("myster", "horror", "unexplain", "secret", "paranormal", "strange", "রহস্য")):
        return "mystery"
    if any(x in combined for x in ("nature", "wildlife", "animal", "ocean", "predator", "jungle", "safari")):
        return "nature"
    if any(x in combined for x in ("news", "geopolit", "politics", "economy", "world affairs")):
        return "news"
    if any(x in combined for x in ("gadget", "phone", "review", "tech", "laptop", "earbuds", "smartphone", "গ্যাজেট")):
        return "gadget"
    if any(x in combined for x in ("histor", "war", "civilization", "ancient", "archaeolog", "empire", "battle", "ইতিহাস")):
        return "history"
    return "general"


def _fallback_islamic_plan(
    niche: str,
    topic: str,
    video_type: str,
    max_seconds: int,
    channel_name: str,
) -> Dict[str, Any]:
    subject = (topic or "Patience in Adversity").strip() or "Patience in Adversity"
    beats = [
        (
            "intro",
            f"When hardship strikes without warning, the immediate reaction defines what happens next. Here is the timeless lesson from {subject}.",
            f"warm golden lantern illuminating open pages in tranquil courtyard",
            f"serene cinematic ambient glow on handcrafted manuscript desk, faceless, warm golden atmospheric light",
        ),
        (
            "context",
            f"Throughout classical Islamic history, every major test was met not with despair, but with deliberate steadfastness.",
            f"timeless Islamic architectural archways with geometric stone carvings",
            f"slow cinematic push along tranquil historic stone colonnade, sunlight filtering through carved geometric screens",
        ),
        (
            "lesson",
            f"True strength lies in controlling the tongue and heart when emotional pressure peaks. Patience is not passive waiting; it is active resolve.",
            f"serene desert dawn with clear horizon and rising soft morning sun",
            f"contemplative desert landscape at dawn, serene golden dunes, gentle morning wind, cinematic depth of field",
        ),
        (
            "reflection",
            f"Classical scholars recorded how humility in knowledge and steadfast intentions turn difficult trials into enduring wisdom.",
            f"calligraphic manuscript textures and inkwell in soft lamp light",
            f"macro shot of classical calligraphy textures, natural wood desk, soft warm rim light, respectful spiritual mood",
        ),
        (
            "payoff",
            f"That profound composure — trusting the divine decree while taking righteous action — remains the true shield against modern chaos.",
            f"peaceful courtyard with calm reflective pool and open sky",
            f"wide cinematic view of peaceful courtyard water reflection, tranquil sky, soft atmospheric lighting",
        ),
        (
            "outro",
            f"Hold firmly to that reminder as you navigate today. Stay connected with {channel_name} for more timeless reflections.",
            f"serene endcard silhouette against gentle sunset sky",
            f"wide peaceful endcard hold over tranquil horizon, gentle ambient sunset glow",
        ),
    ]
    if video_type == "short":
        beats = beats[:5] + [beats[-1]]
    scenes = [
        {
            "element": el,
            "narration": narr,
            "visual_query": vq,
            "visual_prompt": vp,
            "quality_notes": "serene spiritual mood, faceless, respectful lighting, no idols",
        }
        for el, narr, vq, vp in beats
    ]
    title = f"{subject}: The Timeless Lesson in Steadfastness"
    return {
        "topic": subject,
        "title": title,
        "description": f"{title}\n\n#IslamicWisdom #Reflections #SpiritualGrowth",
        "tags": [subject, niche, "islamic history", "wisdom", "reflection"],
        "scenes": _pad_scenes_to_budget(scenes, max_seconds, video_type, subject, niche=niche),
        "director_provider": "fallback_islamic_director",
        "style_family": "islamic",
        "max_seconds": max_seconds,
        "video_type": video_type,
    }


def _fallback_finance_plan(
    niche: str,
    topic: str,
    video_type: str,
    max_seconds: int,
    channel_name: str,
) -> Dict[str, Any]:
    subject = (topic or "Index Fund Compounding").strip() or "Index Fund Compounding"
    beats = [
        (
            "intro",
            f"Most investors lose money not because of bad stocks, but because of emotional timing. Here is how {subject} changes the math.",
            f"financial charts and ticker displays in modern trading floor",
            f"cinematic high contrast trading terminal screens with analytical charts, dark background, cool corporate blue light",
        ),
        (
            "context",
            f"Over decades, market volatility tempts people to sell at bottoms and buy at peaks, quietly erasing lifetime compounding.",
            f"time lapse of bustling financial district skyscrapers at twilight",
            f"dramatic wide angle time lapse of glass financial towers at blue hour, streak of traffic lights below",
        ),
        (
            "mechanism",
            f"When you hold broad, low-cost assets systematically, you capture the collective productivity of the global economy without single-company collapse risk.",
            f"macro shot of mint coins and structured ledger notebook",
            f"shallow depth of field shot of stacked coins and clean ledger paper under directional studio light",
        ),
        (
            "discipline",
            f"The real advantage is not predicting the next crisis — it is maintaining liquid cash reserves so you never have to sell at a loss.",
            f"hands analyzing clean financial statements on minimalist wooden desk",
            f"faceless professional analyzing paper balance sheets, clean minimalist desk, cool natural daylight",
        ),
        (
            "payoff",
            f"Consistency outlasts speculation. Small, disciplined contributions compound into financial independence while market timers burn out.",
            f"exponential growth curve displayed on glass monitor with confident lighting",
            f"smooth cinematic push toward clean upward trendline visualization on sleek glass display",
        ),
        (
            "outro",
            f"Build your financial fortress with rules, not emotions. Stay with {channel_name} for the next wealth blueprint.",
            f"modern office window overlooking expansive city skyline",
            f"wide endcard view through executive window overlooking twilight skyline, confident calm tone",
        ),
    ]
    if video_type == "short":
        beats = beats[:5] + [beats[-1]]
    scenes = [
        {
            "element": el,
            "narration": narr,
            "visual_query": vq,
            "visual_prompt": vp,
            "quality_notes": "cool corporate blue grade, clean charts, faceless, no get-rich-quick memes",
        }
        for el, narr, vq, vp in beats
    ]
    title = f"{subject}: The Mathematical Truth Most Investors Ignore"
    return {
        "topic": subject,
        "title": title,
        "description": f"{title}\n\n#PersonalFinance #Investing #WealthBuilding",
        "tags": [subject, niche, "investing", "finance", "wealth"],
        "scenes": _pad_scenes_to_budget(scenes, max_seconds, video_type, subject, niche=niche),
        "director_provider": "fallback_finance_director",
        "style_family": "finance",
        "max_seconds": max_seconds,
        "video_type": video_type,
    }


def _fallback_health_plan(
    niche: str,
    topic: str,
    video_type: str,
    max_seconds: int,
    channel_name: str,
) -> Dict[str, Any]:
    subject = (topic or "Deep Sleep Optimization").strip() or "Deep Sleep Optimization"
    beats = [
        (
            "intro",
            f"You can do everything right in your diet, but if you ignore {subject}, your biological recovery stalls. Here is the science.",
            f"macro water droplets on fresh vibrant green leaves and citrus",
            f"crisp clinical macro shot of pure water droplets on fresh organic produce, soft teal morning light",
        ),
        (
            "context",
            f"Modern artificial lighting and late-night digital screens delay melatonin release, keeping cellular stress levels artificially elevated.",
            f"dim bedroom with soft warm ambient nightstand illumination",
            f"atmospheric bedroom interior with warm low-level amber lighting, calm peaceful atmosphere, no harsh glare",
        ),
        (
            "mechanism",
            f"During deep restorative cycles, your glymphatic system clears metabolic waste from brain tissue while growth hormones repair muscle fibers.",
            f"microscopic cellular visualization glowing with calm blue energy",
            f"abstract cellular biology visualization, gentle luminescent fluid motion, scientific documentary clarity",
        ),
        (
            "protocol",
            f"Getting direct natural sunlight within thirty minutes of waking sets your master circadian clock, anchoring energy throughout the entire day.",
            f"person silhouette walking outside in golden early morning sunlight",
            f"faceless outdoor silhouette walking in crisp morning light, warm golden sunrise, energetic healthy lifestyle vibe",
        ),
        (
            "payoff",
            f"Prioritizing consistent recovery windows restores hormone balance, sharpens cognitive focus, and builds durable long-term vitality.",
            f"glass of fresh water beside clean athletic training gear",
            f"clean still life of clear glass water bottle on athletic wooden bench, bright natural daylight",
        ),
        (
            "outro",
            f"Small biological adjustments deliver massive compound returns. Subscribe to {channel_name} for your daily health protocol.",
            f"panoramic view of calm nature trail under morning sky",
            f"wide peaceful endcard hold over sunlit nature trail, uplifting health documentary grade",
        ),
    ]
    if video_type == "short":
        beats = beats[:5] + [beats[-1]]
    scenes = [
        {
            "element": el,
            "narration": narr,
            "visual_query": vq,
            "visual_prompt": vp,
            "quality_notes": "clean clinical daylight, teal accents, faceless silhouettes, no miracle-cure claims",
        }
        for el, narr, vq, vp in beats
    ]
    title = f"{subject}: The Biological Protocol That Changes Everything"
    return {
        "topic": subject,
        "title": title,
        "description": f"{title}\n\n#HealthAndWellness #Biohacking #Longevity",
        "tags": [subject, niche, "health", "wellness", "science"],
        "scenes": _pad_scenes_to_budget(scenes, max_seconds, video_type, subject, niche=niche),
        "director_provider": "fallback_health_director",
        "style_family": "health",
        "max_seconds": max_seconds,
        "video_type": video_type,
    }


def _fallback_motivation_plan(
    niche: str,
    topic: str,
    video_type: str,
    max_seconds: int,
    channel_name: str,
) -> Dict[str, Any]:
    subject = (topic or "Daily Execution Systems").strip() or "Daily Execution Systems"
    beats = [
        (
            "intro",
            f"Waiting for motivation is why most people abandon their goals before day thirty. Here is how {subject} rewires the process.",
            f"minimalist notebook and fountain pen on clean dark oak desk",
            f"cinematic close up of structured handwritten notebook on wooden desk, moody side lighting, focused mindset atmosphere",
        ),
        (
            "context",
            f"Feelings are volatile and unreliable. High performers do not wait to feel inspired; they design environments where action is automatic.",
            f"early morning athlete lacing up running shoes in dim light",
            f"faceless close up of athlete tying laces in quiet dawn light, determination and quiet discipline, shallow DOF",
        ),
        (
            "mechanism",
            f"When you eliminate friction between you and your work, resistance drops. The secret is protecting ninety uninterrupted minutes every single day.",
            f"sand timer steadily flowing with fine grain on focused workspace",
            f"macro shot of minimalist hourglass sand steadily flowing, soft focused office background, calm precision",
        ),
        (
            "friction",
            f"Every distraction you allow robs you of momentum. Defend your attention like your future depends on it, because it does.",
            f"clean organized workspace with coffee steam rising in quiet morning",
            f"warm morning light illuminating steam from single coffee cup beside clean keyboard, distraction-free environment",
        ),
        (
            "payoff",
            f"Ruthless consistency compounds quietly in the dark until the results become impossible for the world to ignore.",
            f"city skyline at dawn with golden sun breaking through clouds",
            f"inspirational wide shot of city waking up at dawn, sun rays cutting through misty horizon, cinematic grade",
        ),
        (
            "outro",
            f"Do not negotiate with your routine today. Stay disciplined, and keep building with {channel_name}.",
            f"focused workstation hold with golden hour spotlight",
            f"wide endcard hold on quiet focused workstation with warm evening glow, motivating clean aesthetic",
        ),
    ]
    if video_type == "short":
        beats = beats[:5] + [beats[-1]]
    scenes = [
        {
            "element": el,
            "narration": narr,
            "visual_query": vq,
            "visual_prompt": vp,
            "quality_notes": "warm sunrise cinematic lifestyle grade, shallow DOF, faceless focus, no empty hype text",
        }
        for el, narr, vq, vp in beats
    ]
    title = f"{subject}: Why Discipline Beats Motivation Every Time"
    return {
        "topic": subject,
        "title": title,
        "description": f"{title}\n\n#Discipline #Mindset #Productivity",
        "tags": [subject, niche, "motivation", "discipline", "mindset"],
        "scenes": _pad_scenes_to_budget(scenes, max_seconds, video_type, subject, niche=niche),
        "director_provider": "fallback_motivation_director",
        "style_family": "motivation",
        "max_seconds": max_seconds,
        "video_type": video_type,
    }


def _fallback_nature_plan(
    niche: str,
    topic: str,
    video_type: str,
    max_seconds: int,
    channel_name: str,
) -> Dict[str, Any]:
    subject = (topic or "Deep Sea Predator Tactics").strip() or "Deep Sea Predator Tactics"
    beats = [
        (
            "intro",
            f"In the harshest environments on Earth, survival is not about brute strength. Here is how {subject} mastered the extreme.",
            f"wide cinematic aerial of dense misty rainforest canopy",
            f"sweeping aerial 4k drone shot of lush mist rising over ancient tropical canopy, early morning golden light",
        ),
        (
            "context",
            f"When resources become scarce, species adapt specialized sensory equipment that borders on biological engineering.",
            f"macro shot of predator eye with sharp iris focus",
            f"extreme close up of wild predator eye contracting in changing light, hyper detailed iris textures, natural documentary grade",
        ),
        (
            "adaptation",
            f"From thermal insulation to silent acoustic hunting, every muscle movement is calibrated to conserve vital metabolic energy.",
            f"slow motion predator tracking prey through tall savannah grass",
            f"telephoto documentary shot of predator moving silently through golden savannah grass, shallow depth of field",
        ),
        (
            "balance",
            f"Keystone predators preserve ecosystem equilibrium, preventing any single species from overrunning the delicate habitat.",
            f"dramatic wide shot of wildlife herd moving across river crossing",
            f"grand wide angle migration across shallow river rapids, splashing water caught in high shutter speed",
        ),
        (
            "payoff",
            f"Millions of years of evolutionary pressure created a balance so precise that modern engineers still copy its mechanics.",
            f"sunbeams piercing deep ocean water with solitary marine life",
            f"underwater cinematic shot of god rays penetrating deep blue ocean depths, serene solitary marine silhouette",
        ),
        (
            "outro",
            f"The wild operates on laws of ruthless efficiency and balance. Stay with {channel_name} for the next wildlife investigation.",
            f"majestic sunset over untamed wilderness horizon",
            f"wide endcard view over wild mountain ridge at golden sunset, breathtaking documentary mood",
        ),
    ]
    if video_type == "short":
        beats = beats[:5] + [beats[-1]]
    scenes = [
        {
            "element": el,
            "narration": narr,
            "visual_query": vq,
            "visual_prompt": vp,
            "quality_notes": "earth tones, natural wildlife grade, authentic animal behavior, no zoo cages",
        }
        for el, narr, vq, vp in beats
    ]
    title = f"{subject}: Evolutionary Survival at the Extreme"
    return {
        "topic": subject,
        "title": title,
        "description": f"{title}\n\n#NatureDocumentary #Wildlife #Evolution",
        "tags": [subject, niche, "wildlife", "nature", "animals"],
        "scenes": _pad_scenes_to_budget(scenes, max_seconds, video_type, subject, niche=niche),
        "director_provider": "fallback_nature_director",
        "style_family": "nature",
        "max_seconds": max_seconds,
        "video_type": video_type,
    }


def _fallback_true_crime_plan(
    niche: str,
    topic: str,
    video_type: str,
    max_seconds: int,
    channel_name: str,
) -> Dict[str, Any]:
    subject = (topic or "The Overlooked Timeline Discrepancy").strip() or "The Overlooked Timeline Discrepancy"
    beats = [
        (
            "intro",
            f"For over twenty years, detectives believed this case was solved — until an overlooked timeline contradiction reopened everything in {subject}.",
            f"detective case file folder stamped confidential under desk lamp",
            f"atmospheric desk under harsh desk lamp, weathered case files and typed reports, noir documentary grade",
        ),
        (
            "context",
            f"Initial police dispatches recorded conflicting timestamps between witness 911 calls and physical evidence recovered at the scene.",
            f"empty city street at night under amber streetlights and light rain",
            f"gritty urban street corner in light rain, wet asphalt reflecting amber streetlights, cinematic tension",
        ),
        (
            "anomaly",
            f"When forensic investigators re-examined the physical artifacts, microscopic trace evidence proved the primary suspect could not have been present.",
            f"macro forensic analysis tools and evidence packaging",
            f"close documentary shot of clean forensic tweezers and sealed evidence envelopes on stainless steel table",
        ),
        (
            "turning_point",
            f"A buried telephone log recovered from telecom archives placed the actual movements six miles away at the critical hour.",
            f"analog telecom logs and reel to reel tape equipment in storage",
            f"vintage archival records and magnetic audio reels in dimly lit record room, cold shadows",
        ),
        (
            "payoff",
            f"The revelation shattered the prosecution theory, proving how easily confirmation bias can misdirect an entire investigation.",
            f"sealed courthouse door in morning mist",
            f"imposing courthouse stone steps in early morning fog, slow cinematic push in, dramatic documentary resolution",
        ),
        (
            "outro",
            f"The truth always leaves traces if you are willing to look. Stay with {channel_name} for the next unsolved forensic breakdown.",
            f"lonely streetlamp silhouette at dusk",
            f"wide noir endcard hold on quiet misty road under solitary lamp, thoughtful quiet resolution",
        ),
    ]
    if video_type == "short":
        beats = beats[:5] + [beats[-1]]
    scenes = [
        {
            "element": el,
            "narration": narr,
            "visual_query": vq,
            "visual_prompt": vp,
            "quality_notes": "noir documentary grade, cold shadows, faceless silhouettes, no graphic gore",
        }
        for el, narr, vq, vp in beats
    ]
    title = f"{subject}: The Evidence That Reopened the Case"
    return {
        "topic": subject,
        "title": title,
        "description": f"{title}\n\n#TrueCrime #Forensics #ColdCase",
        "tags": [subject, niche, "true crime", "forensics", "investigation"],
        "scenes": _pad_scenes_to_budget(scenes, max_seconds, video_type, subject, niche=niche),
        "director_provider": "fallback_true_crime_director",
        "style_family": "true_crime",
        "max_seconds": max_seconds,
        "video_type": video_type,
    }


def _fallback_mystery_plan(
    niche: str,
    topic: str,
    video_type: str,
    max_seconds: int,
    channel_name: str,
) -> Dict[str, Any]:
    subject = (topic or "The Uncharted Sound Anomaly").strip() or "The Uncharted Sound Anomaly"
    beats = [
        (
            "intro",
            f"Deep sensors recorded an unexplained signal that acoustic models said was impossible. Here is what we know about {subject}.",
            f"mysterious foggy ocean horizon under dark twilight sky",
            f"cinematic dark teal ocean horizon engulfed in dense eerie fog, cold dramatic side lighting, high tension",
        ),
        (
            "context",
            f"Hydrophones thousands of miles apart picked up the frequency simultaneously, ruling out local equipment malfunction.",
            f"hydrophone sonar monitoring waveforms on analog oscilloscopes",
            f"vintage green phosphor oscilloscope screen showing erratic waveform spikes, dark research vessel interior",
        ),
        (
            "anomaly",
            f"Oceanographers initially blamed tectonic fractures, but the harmonic pattern displayed deliberate modulation unlike any known earthquake.",
            f"sonar bathymetric ocean floor map with deep trench contour lines",
            f"detailed digital bathymetry map of undersea trench, glowing contour lines on deep ocean abyss",
        ),
        (
            "investigation",
            f"Expeditions sent remote submersibles into the coordinates, finding unusual thermal plumes rising from seabed fissures.",
            f"robotic deep sea submersible lights illuminating hydrothermal vents",
            f"deep sea exploration rover illuminating volcanic mineral spires, swirling thermal fluid in pitch black water",
        ),
        (
            "payoff",
            f"Decades later, the signal remains officially unclassified — a stark reminder that our oceans hold secrets deeper than our technology.",
            f"abyssal underwater chasm fading into total blackness",
            f"haunting wide shot into the oceanic abyss, distant particulate drifting through faint spotlight beam",
        ),
        (
            "outro",
            f"The unexplained is rarely fiction; it is nature waiting to be understood. Follow {channel_name} as we explore the unknown.",
            f"lone research vessel silhouette on distant foggy horizon",
            f"wide moody endcard hold on distant research ship lights through thick evening sea fog",
        ),
    ]
    if video_type == "short":
        beats = beats[:5] + [beats[-1]]
    scenes = [
        {
            "element": el,
            "narration": narr,
            "visual_query": vq,
            "visual_prompt": vp,
            "quality_notes": "dark teal green eerie grade, dramatic mystery lighting, no cheesy horror monsters",
        }
        for el, narr, vq, vp in beats
    ]
    title = f"{subject}: The Phenomenon Science Cannot Explain"
    return {
        "topic": subject,
        "title": title,
        "description": f"{title}\n\n#UnexplainedMysteries #DeepSea #ScienceMystery",
        "tags": [subject, niche, "mystery", "unexplained", "science"],
        "scenes": _pad_scenes_to_budget(scenes, max_seconds, video_type, subject, niche=niche),
        "director_provider": "fallback_mystery_director",
        "style_family": "mystery",
        "max_seconds": max_seconds,
        "video_type": video_type,
    }


def _fallback_news_plan(
    niche: str,
    topic: str,
    video_type: str,
    max_seconds: int,
    channel_name: str,
) -> Dict[str, Any]:
    subject = (topic or "Global Semiconductor Supply Chains").strip() or "Global Semiconductor Supply Chains"
    beats = [
        (
            "intro",
            f"Behind the diplomatic headlines, a critical economic shift is unfolding. Here is the real story behind {subject}.",
            f"modern logistics container port with cranes active at dusk",
            f"crisp neutral documentary shot of automated container terminal cranes operating under industrial lights at dusk",
        ),
        (
            "context",
            f"International trade agreements and resource access are forcing nations to reorganize their manufacturing independence.",
            f"global shipping route map illuminated across digital globe",
            f"clean geographic map visualization displaying maritime supply bottlenecks, high contrast documentary style",
        ),
        (
            "economic_impact",
            f"When critical transit corridors face disruption, consumer prices and factory outputs thousands of miles away react in days.",
            f"modern industrial factory floor with automated assembly systems",
            f"clean automated manufacturing line, robotic arms moving with precision, neutral documentary lighting",
        ),
        (
            "strategic_pivot",
            f"Policymakers are deploying hundreds of billions in strategic subsidies to build regional redundancy before the next shock hits.",
            f"press briefing room with international flags and microphones",
            f"formal press briefing podium with microphones, clean diplomatic aesthetic, crisp documentary contrast",
        ),
        (
            "payoff",
            f"The outcome of this restructuring will determine economic leverage and industrial leadership for the next generation.",
            f"cargo freighter navigating wide open maritime channel",
            f"impressive aerial view of massive container ship cutting through open ocean waters at sunrise",
        ),
        (
            "outro",
            f"Global economics move silently until the impact hits your doorstep. Stay ahead of the curve with {channel_name}.",
            f"skyline of major global commerce hub at twilight",
            f"wide endcard view over illuminated international trade hub skyline at twilight, thoughtful informative tone",
        ),
    ]
    if video_type == "short":
        beats = beats[:5] + [beats[-1]]
    scenes = [
        {
            "element": el,
            "narration": narr,
            "visual_query": vq,
            "visual_prompt": vp,
            "quality_notes": "neutral documentary grade, crisp contrast, no deepfakes, no sensational gore",
        }
        for el, narr, vq, vp in beats
    ]
    title = f"{subject}: The Strategic Power Shift Explained"
    return {
        "topic": subject,
        "title": title,
        "description": f"{title}\n\n#GlobalEconomy #Geopolitics #SupplyChain",
        "tags": [subject, niche, "news", "geopolitics", "economy"],
        "scenes": _pad_scenes_to_budget(scenes, max_seconds, video_type, subject, niche=niche),
        "director_provider": "fallback_news_director",
        "style_family": "news",
        "max_seconds": max_seconds,
        "video_type": video_type,
    }


def _fallback_gadget_plan(
    niche: str,
    topic: str,
    video_type: str,
    max_seconds: int,
    channel_name: str,
    blocked: Optional[List[str]] = None,
) -> Dict[str, Any]:
    product = _pick_fresh_product(topic, niche, blocked or [])
    if video_type == "short":
        scenes = [
            {
                "element": "intro",
                "narration": f"Most people buying {product} miss the one trade-off that changes everything after two weeks. Look closely.",
                "visual_query": f"{product} product hero shot unboxing table",
                "visual_prompt": f"cinematic hero shot of {product} on dark desk, rim light, shallow depth of field",
                "quality_notes": "clean hero product shot, sharp focus",
            },
            {
                "element": "design",
                "narration": "Pick it up and the chassis tells the story — weight balance, tactile button travel, and everyday grip.",
                "visual_query": f"{product} design close up body finish buttons",
                "visual_prompt": f"macro orbit around {product} chassis, premium materials, studio light",
                "quality_notes": "macro design details, no watermark",
            },
            {
                "element": _primary_feature_element(product),
                "narration": _primary_feature_line(product),
                "visual_query": _primary_feature_query(product),
                "visual_prompt": _primary_feature_prompt(product),
                "quality_notes": "element-matched footage only",
            },
            {
                "element": "battery",
                "narration": "Battery drain and thermal limits decide daily comfort — sustained gaming heats the frame fast.",
                "visual_query": f"{product} charging battery cable close up",
                "visual_prompt": f"{product} plugged in charging on night desk, soft glow",
                "quality_notes": "charging close-up",
            },
            {
                "element": "outro",
                "narration": f"Before spending a single dollar on {product}, weigh that trade-off carefully. Stay with {channel_name} for the next breakdown.",
                "visual_query": f"{product} final hero lifestyle endcard",
                "visual_prompt": f"final hero hold of {product}, soft spotlight endcard energy",
                "quality_notes": "outro product hold",
            },
        ]
    else:
        scenes = [
            {
                "element": "intro",
                "narration": f"On paper, {product} looks like an easy recommendation. But after extensive testing, two flaws surface.",
                "visual_query": f"{product} cinematic unboxing intro",
                "visual_prompt": f"cinematic unboxing intro of {product}",
                "quality_notes": "strong intro establish",
            },
            {
                "element": "design",
                "narration": "First, ergonomics and build. Weight distribution, tactile button travel, and matte frame finish in daily hand feel.",
                "visual_query": f"{product} design details buttons ports",
                "visual_prompt": f"detail montage of {product} ports buttons finish",
                "quality_notes": "detail pans",
            },
            {
                "element": "display" if not _is_audio_wearable(product) else "fit",
                "narration": (
                    "Fit and ear canal seal — how securely it stays during movement and whether pressure builds over two hours."
                    if _is_audio_wearable(product)
                    else "The display: peak outdoor brightness, color calibration accuracy, and whether touch response stays smooth under sun."
                ),
                "visual_query": (
                    "wireless earbuds in ear fit close up"
                    if _is_audio_wearable(product)
                    else "smartphone amoled display close up scrolling content"
                ),
                "visual_prompt": (
                    "person wearing earbuds comfort close-up"
                    if _is_audio_wearable(product)
                    else "bright phone display content scrolling cinematic"
                ),
                "quality_notes": "element-matched",
            },
            {
                "element": "camera" if not _is_audio_wearable(product) else "case",
                "narration": (
                    "Case ergonomics and pocketability — hinge resistance, magnetic snap, and durability against daily pocket friction."
                    if _is_audio_wearable(product)
                    else "Camera optics: daylight dynamic range, edge distortion, and noise reduction behavior in low light."
                ),
                "visual_query": (
                    "earbuds charging case open close"
                    if _is_audio_wearable(product)
                    else "smartphone camera lens module macro"
                ),
                "visual_prompt": (
                    "earbuds case opening cinematic"
                    if _is_audio_wearable(product)
                    else "macro camera lenses on phone glowing ring"
                ),
                "quality_notes": "macro / case detail",
            },
            {
                "element": "processor" if not _is_audio_wearable(product) else "sound",
                "narration": (
                    "Sound tuning: frequency separation, active noise cancellation thresholds, and vocal clarity in noisy environments."
                    if _is_audio_wearable(product)
                    else "Chipset performance under sustained heat: benchmark numbers mean nothing if thermal throttling drops frames in thirty minutes."
                ),
                "visual_query": (
                    "earbuds speakers sound wave music lifestyle"
                    if _is_audio_wearable(product)
                    else "mobile processor chipset circuit board close up"
                ),
                "visual_prompt": (
                    "audio wave visualization with earbuds"
                    if _is_audio_wearable(product)
                    else "futuristic chipset glow animation for phone SoC"
                ),
                "quality_notes": "performance or audio metaphor",
            },
            {
                "element": "battery",
                "narration": "Battery endurance and charging curve — high refresh rates and active cellular connection test real-world stamina.",
                "visual_query": f"{product} charging fast charge cable close up",
                "visual_prompt": f"device charging with glowing cable cinematic {product}",
                "quality_notes": "charging scene",
            },
            {
                "element": "price",
                "narration": "Pricing reality — it justifies the cost only if these specific hardware strengths match your everyday workflow.",
                "visual_query": f"{product} retail box value product shot",
                "visual_prompt": f"premium product value shot of {product} with soft store lighting",
                "quality_notes": "value framing",
            },
            {
                "element": "pros_cons",
                "narration": "Balancing the trade-offs: outstanding hardware finish countered by aggressive software background management.",
                "visual_query": "tech review checklist hands gadget",
                "visual_prompt": "reviewer checklist overlay style product shot",
                "quality_notes": "pros cons beat",
            },
            {
                "element": "outro",
                "narration": f"Weigh the trade-offs before upgrading. Follow {channel_name} for real, unfiltered tech hardware evaluations.",
                "visual_query": f"{product} final verdict product stand",
                "visual_prompt": f"final hero shot of {product} with soft spotlight",
                "quality_notes": "verdict end",
            },
        ]

    title = (
        f"{product} Honest Review: Is It Worth Your Money in 2026?"
        if video_type == "short"
        else f"{product} Full In-Depth Review: Real-World Performance & Trade-Offs"
    )
    return {
        "analysis": {
            "niche_summary": f"{niche} review niche",
            "why_this_topic": "High-interest gadget not on channel blocklist",
            "audience": "English master audience; other languages via localization",
            "tone": "honest practical",
            "product_category": _guess_category(product),
            "avoided_duplicates": (blocked or [])[:20],
            "master_lang": "en",
        },
        "topic": product,
        "product_key_hint": product.lower(),
        "title": title,
        "description": f"{title}\n\n#{''.join(c for c in product if c.isalnum())} #GadgetReview #TechReview",
        "tags": [product, niche, "review", "2026", "tech review"],
        "scenes": _pad_scenes_to_budget(scenes, max_seconds, video_type, product, niche=niche),
        "director_provider": "fallback_gadget_director",
        "style_family": "gadget",
        "max_seconds": max_seconds,
        "video_type": video_type,
    }


def _fallback_general_plan(
    niche: str,
    topic: str,
    video_type: str,
    max_seconds: int,
    channel_name: str,
) -> Dict[str, Any]:
    subject = (topic or niche or "The Hidden Mechanism").strip() or "The Hidden Mechanism"
    beats = [
        (
            "intro",
            f"Most explanations of {subject} stop at the surface. But when you look at the underlying mechanics, an unexpected truth emerges.",
            f"cinematic macro establishing shot of complex mechanism related to {subject}",
            f"moody documentary establishing shot of intricate details regarding {subject}, soft directional lighting, high contrast",
        ),
        (
            "context",
            f"For years, conventional wisdom assumed a simple cause and effect, ignoring the hidden variables driving the real outcome.",
            f"detailed archival documentation and analytical diagram visualization",
            f"slow cinematic drift over structured analytical charts and historical notes, calm educational grade",
        ),
        (
            "mechanism",
            f"Careful investigation demonstrates that subtle changes in early conditions completely transform the end result.",
            f"precision laboratory or technical equipment actively monitoring {subject}",
            f"close documentary view of precision measurement instruments capturing fine data points, cinematic shallow depth of field",
        ),
        (
            "evidence",
            f"Cross-referencing verified case studies proves this pattern repeats across varied environments and diverse conditions.",
            f"comparative case study visual layout with analytical data overlays",
            f"clean modern documentary comparison sequence, elegant visual clarity, high resolution",
        ),
        (
            "payoff",
            f"Understanding this fundamental dynamic allows you to anticipate outcomes that catch everyone else completely off guard.",
            f"confident wide view of structured solution resolving successfully",
            f"illuminating cinematic wide shot showing orderly breakthrough, inspiring documentary lighting",
        ),
        (
            "outro",
            f"Mastering the nuances is what sets leaders apart. Stay with {channel_name} as we break down what matters most.",
            f"calm architectural endcard hold with atmospheric horizon",
            f"wide elegant endcard hold with soft cinematic lighting, thoughtful and authoritative finish",
        ),
    ]
    if video_type == "short":
        beats = beats[:5] + [beats[-1]]
    scenes = [
        {
            "element": el,
            "narration": narr,
            "visual_query": vq,
            "visual_prompt": vp,
            "quality_notes": "authoritative documentary grade, crisp contrast, no robotic cliches",
        }
        for el, narr, vq, vp in beats
    ]
    title = f"{subject}: What Most People Never Understand"
    return {
        "topic": subject,
        "title": title,
        "description": f"{title}\n\n#DeepDive #Explained #Documentary",
        "tags": [subject, niche, "documentary", "explained", "analysis"],
        "scenes": _pad_scenes_to_budget(scenes, max_seconds, video_type, subject, niche=niche),
        "director_provider": "fallback_general_director",
        "style_family": "general",
        "max_seconds": max_seconds,
        "video_type": video_type,
    }


def _fallback_plan(
    niche: str,
    topic: str,
    video_type: str,
    max_seconds: int,
    channel_name: str,
    blocked_products: Optional[List[str]] = None,
) -> Dict[str, Any]:
    fam = _detect_niche_family(niche, topic)
    if fam == "islamic":
        return _fallback_islamic_plan(niche, topic, video_type, max_seconds, channel_name)
    elif fam == "finance":
        return _fallback_finance_plan(niche, topic, video_type, max_seconds, channel_name)
    elif fam == "health":
        return _fallback_health_plan(niche, topic, video_type, max_seconds, channel_name)
    elif fam == "motivation":
        return _fallback_motivation_plan(niche, topic, video_type, max_seconds, channel_name)
    elif fam == "science":
        return _fallback_space_science_plan(niche, topic, video_type, max_seconds, channel_name)
    elif fam == "nature":
        return _fallback_nature_plan(niche, topic, video_type, max_seconds, channel_name)
    elif fam == "true_crime":
        return _fallback_true_crime_plan(niche, topic, video_type, max_seconds, channel_name)
    elif fam == "mystery":
        return _fallback_mystery_plan(niche, topic, video_type, max_seconds, channel_name)
    elif fam == "news":
        return _fallback_news_plan(niche, topic, video_type, max_seconds, channel_name)
    elif fam == "gadget":
        return _fallback_gadget_plan(niche, topic, video_type, max_seconds, channel_name, blocked_products)
    elif fam == "history":
        return _fallback_history_plan(niche, topic, video_type, max_seconds, channel_name, blocked_products)
    else:
        return _fallback_general_plan(niche, topic, video_type, max_seconds, channel_name)


def _pad_scenes_to_budget(
    scenes: List[Dict[str, Any]],
    max_seconds: int,
    video_type: str,
    product: str,
    *,
    niche: str = "",
) -> List[Dict[str, Any]]:
    from pipeline.duration_budget import planned_scene_count
    from pipeline.dialogue_uniqueness import HISTORY_ELEMENTS

    want = planned_scene_count(max_seconds, video_type)
    rows = [s for s in scenes if isinstance(s, dict)]
    if len(rows) >= want:
        return rows[: max(want, len(rows))]

    fam = _detect_niche_family(niche, product)
    subject = (product or niche or "this subject").strip()

    if fam == "gadget":
        fillers = [
            {
                "element": "design",
                "narration": f"Chassis weight balance and matte finish reduce wrist strain during long everyday use.",
                "visual_query": f"{product} macro design details",
                "visual_prompt": f"macro cinematic details of {product}, studio rim light",
                "quality_notes": "budget filler beat",
            },
            {
                "element": "software",
                "narration": f"Software optimization and background app management determine whether performance stays fluid after months.",
                "visual_query": f"{product} software ui in hand",
                "visual_prompt": f"{product} in-hand UI glow, documentary grade",
                "quality_notes": "budget filler beat",
            },
            {
                "element": "battery",
                "narration": "Thermal throttling under fast charging is often the silent deal-breaker during heavy work sessions.",
                "visual_query": f"{product} charging cable close up",
                "visual_prompt": f"{product} charging glow on night desk",
                "quality_notes": "budget filler beat",
            },
            {
                "element": "price",
                "narration": "Retail value holds only when these specific hardware strengths align with your personal daily workflow.",
                "visual_query": f"{product} retail value shot",
                "visual_prompt": f"premium value shot of {product}",
                "quality_notes": "budget filler beat",
            },
        ]
    elif fam == "science":
        space_facts = [
            ("heat_shield", f"Heat shield materials for {subject} are engineered for steep atmospheric reentry thermal gradients."),
            ("boosters", f"Primary propulsion stages deliver initial velocity before precision orbital maneuvers commence."),
            ("trajectory", f"Free-return geometry acts as an autonomous safety corridor throughout the journey."),
            ("coast", f"Extended coast phases demand meticulous power management and redundant environmental controls."),
            ("avionics", f"Telemetry streams continually monitor attitude stability and structural margins."),
        ]
        fillers = [
            {
                "element": el,
                "narration": line,
                "visual_query": f"{subject} {el} space documentary",
                "visual_prompt": f"documentary visualization for {el} in {subject}, continuous calm motion",
                "quality_notes": "science documentary budget filler",
            }
            for el, line in space_facts
        ]
    elif fam == "finance":
        fin_facts = [
            ("rebalancing", "Periodic portfolio rebalancing systematically buys discounted assets and trims overextended gains."),
            ("cash_buffer", "Holding adequate liquidity reserves prevents panic-selling during unpredictable market downturns."),
            ("fee_drag", "Minimizing expense ratios and trading commissions preserves tens of thousands in compound wealth."),
            ("diversification", "Uncorrelated asset allocations soften volatility drawdowns without sacrificing long-term returns."),
        ]
        fillers = [
            {
                "element": el,
                "narration": line,
                "visual_query": f"{subject} finance documentary {el}",
                "visual_prompt": f"cinematic analytical charts and corporate desk textures for {el}, cool blue lighting",
                "quality_notes": "finance documentary budget filler",
            }
            for el, line in fin_facts
        ]
    elif fam == "health":
        health_facts = [
            ("circadian", "Morning daylight exposure anchors hormone synthesis and stabilizes metabolic energy rhythms."),
            ("hydration", "Maintaining cellular electrolyte balance sustains cognitive stamina and muscular efficiency."),
            ("recovery", "Restorative sleep cycles facilitate neural glymphatic clearance and tissue repair."),
            ("overload", "Progressive physical stimulus signals bone density reinforcement and metabolic resilience."),
        ]
        fillers = [
            {
                "element": el,
                "narration": line,
                "visual_query": f"{subject} health wellness {el}",
                "visual_prompt": f"clean clinical macro visuals and soft morning daylight for {el}, teal accents",
                "quality_notes": "health documentary budget filler",
            }
            for el, line in health_facts
        ]
    elif fam == "motivation":
        mot_facts = [
            ("systems", "Routines eliminate decision fatigue, allowing energy to focus entirely on deep execution."),
            ("friction", "Reducing physical barriers to entry makes disciplined work the path of least resistance."),
            ("resilience", "Handling small daily inconveniences calmly builds psychological fortitude for major trials."),
            ("momentum", "Consistent small completions trigger natural dopamine feedback that sustains effort."),
        ]
        fillers = [
            {
                "element": el,
                "narration": line,
                "visual_query": f"{subject} productivity focus {el}",
                "visual_prompt": f"warm cinematic focused workspace and dawn lifestyle lighting for {el}, shallow DOF",
                "quality_notes": "motivation documentary budget filler",
            }
            for el, line in mot_facts
        ]
    elif fam == "islamic":
        isl_facts = [
            ("humility", "Classical teachers underscored that inward humility elevates understanding and softens the heart."),
            ("steadfastness", "Navigating hardship with quiet dignity reflects profound trust in divine wisdom."),
            ("sincerity", "Pure intentions transform ordinary daily efforts into meaningful spiritual legacy."),
            ("gratitude", "Recognizing small blessings during difficulty preserves contentment and inner peace."),
        ]
        fillers = [
            {
                "element": el,
                "narration": line,
                "visual_query": f"{subject} islamic architecture reflections {el}",
                "visual_prompt": f"serene warm golden ambient light and geometric architectural details for {el}, respectful mood",
                "quality_notes": "islamic documentary budget filler",
            }
            for el, line in isl_facts
        ]
    elif fam == "nature":
        nat_facts = [
            ("navigation", "Instinctive migratory compasses decode geomagnetic signals across thousands of miles."),
            ("acoustics", "Underwater acoustic communications penetrate ocean depths with astonishing clarity."),
            ("symbiosis", "Interconnected root networks exchange vital nutrients during seasonal drought extremes."),
            ("camouflage", "Microscopic skin cell structures bend ambient light to achieve flawless concealment."),
        ]
        fillers = [
            {
                "element": el,
                "narration": line,
                "visual_query": f"{subject} wildlife nature {el}",
                "visual_prompt": f"earth tones and authentic wildlife behavior in natural biomes for {el}, documentary grade",
                "quality_notes": "nature documentary budget filler",
            }
            for el, line in nat_facts
        ]
    elif fam in ("true_crime", "mystery"):
        myst_facts = [
            ("records", "Archival logs revealed discrepancies between initial eyewitness reports and dispatch logs."),
            ("forensics", "Microscopic physical residue provided critical clues that transformed the investigation."),
            ("timeline", "Careful chronology reconstruction placed movements in conflict with official theories."),
            ("anomaly", "Unusual sensor readings persisted long after standard explanations were exhausted."),
        ]
        fillers = [
            {
                "element": el,
                "narration": line,
                "visual_query": f"{subject} investigation documentary {el}",
                "visual_prompt": f"dramatic noir shadows and cold ambient side lighting for {el}, high tension",
                "quality_notes": "investigative documentary budget filler",
            }
            for el, line in myst_facts
        ]
    elif fam == "history":
        hist_facts = [
            ("logistics", f"Surviving trade inventories prove that supply lines into {subject} reached across vast territories."),
            ("masonry", f"Excavated stonework at {subject} demonstrates advanced hydraulic engineering beneath public spaces."),
            ("records", f"Administrative tablets preserved details of civic responsibilities and community laws in {subject}."),
            ("legacy", f"Pivotal strategic decisions at {subject} left lasting structural impacts on regional governance."),
        ]
        fillers = [
            {
                "element": el,
                "narration": line,
                "visual_query": f"{subject} historical ruins artifacts {el}",
                "visual_prompt": f"cinematic textured documentary lighting on ancient ruins and relics for {subject} {el}",
                "quality_notes": "history documentary budget filler",
            }
            for el, line in hist_facts
        ]
    else:
        gen_facts = [
            ("analysis", f"Systematic analysis of {subject} reveals underlying factors that casual observers routinely overlook."),
            ("evidence", f"Concrete case studies confirm how foundational principles govern performance across varying conditions."),
            ("mechanism", f"Investigating the structural mechanics of {subject} clarifies the distinction between assumptions and results."),
            ("payoff", f"Recognizing these subtle dynamics enables decisive and well-timed execution."),
        ]
        fillers = [
            {
                "element": el,
                "narration": line,
                "visual_query": f"{subject} documentary analysis {el}",
                "visual_prompt": f"authoritative documentary visuals and high contrast lighting for {subject} {el}",
                "quality_notes": "general documentary budget filler",
            }
            for el, line in gen_facts
        ]

    outro = rows[-1] if rows and str(rows[-1].get("element") or "") == "outro" else None
    body = rows[:-1] if outro is not None else list(rows)
    i = 0
    while len(body) + (1 if outro else 0) < want:
        extra = dict(fillers[i % len(fillers)])
        extra["element"] = str(extra.get("element") or "feature")
        body.append(extra)
        i += 1
    if outro is not None:
        body.append(outro)
    return body


def _is_audio_wearable(product: str) -> bool:
    p = product.lower()
    return any(x in p for x in ("bud", "ear", "airpod", "headphone", "headset", "wf-"))


def _guess_category(product: str) -> str:
    p = product.lower()
    if _is_audio_wearable(p):
        return "earbuds"
    if any(x in p for x in ("watch", "band", "ultra")):
        return "watch"
    if any(x in p for x in ("quest", "vision", "steam deck", "ally", "legion go")):
        return "handheld"
    if any(x in p for x in ("gopro", "osmo", "camera")):
        return "camera"
    if any(x in p for x in ("laptop", "macbook", "notebook")):
        return "laptop"
    return "phone"


def _primary_feature_element(product: str) -> str:
    if _is_audio_wearable(product):
        return "sound"
    cat = _guess_category(product)
    if cat == "watch":
        return "software"
    if cat in {"camera", "handheld"}:
        return "camera"
    return "display"


def _primary_feature_line(product: str) -> str:
    el = _primary_feature_element(product)
    if el == "sound":
        return "Sound and ANC are the real game-changer — music and calls both have to stay clear."
    if el == "software":
        return "Software and health features shape daily use — from notifications to tracking."
    if el == "camera":
        return "Camera quality is why many people buy it — daylight and low-light both matter."
    return "The display shapes everyday use — watch the brightness and how smoothly it scrolls."


def _primary_feature_query(product: str) -> str:
    el = _primary_feature_element(product)
    if el == "sound":
        return f"{product} wireless earbuds sound lifestyle close up"
    if el == "software":
        return f"{product} smartwatch ui wrist close up"
    if el == "camera":
        return f"{product} camera lens macro action"
    return f"{product} display screen content close up"


def _primary_feature_prompt(product: str) -> str:
    el = _primary_feature_element(product)
    if el == "sound":
        return f"cinematic close-up of {product} earbuds with subtle audio-wave atmosphere"
    if el == "software":
        return f"cinematic wrist shot of {product} glowing UI"
    if el == "camera":
        return f"macro cinematic of {product} lens, rim light"
    return f"close-up of {product} screen with colorful content, cinematic"


def _extract_json(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("{"):
        return text
    m = re.search(r"\{[\s\S]*\}", text)
    return m.group(0) if m else "{}"
