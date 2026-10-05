"""
Niche auto-agent: when a user picks a Nish.Md niche, fill every channel /
director touchpoint so topic + video generation need almost no manual prompts.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pipeline.nish_catalog import resolve_niche


FAMILY_CHANNEL_DEFAULTS: Dict[str, Dict[str, str]] = {
    "history": {
        "video_special": (
            "Documentary English master narration; one concrete historical beat per scene; "
            "period-accurate props; no modern phones/logos."
        ),
        "generation_special": (
            "Industrial retention: cold-open curiosity gap; open loop → evidence → payoff; "
            "mid-video re-hooks every beat; close the promise before outro; "
            "keep character/env continuity across 7–9s clips."
        ),
        "title_desc_special": (
            "SEO+CTR: specific event/place/person + year + mystery angle; honest title promise; "
            "English+localized tags later."
        ),
    },
    "mystery": {
        "video_special": "Eerie documentary tone; evidence first, theory second; no jump-scare faces.",
        "generation_special": (
            "Build suspense with open loops; pay off with evidence; consistent fog/light grade; "
            "never flat description chains."
        ),
        "title_desc_special": "SEO+CTR: unsolved / vanished / secret + concrete subject; comment bait question.",
    },
    "science": {
        "video_special": "Clear English explainers; show cause→effect visually; lab/teal grade.",
        "generation_special": (
            "One mechanism per scene; re-hook with why/how/what-if; accurate metaphors; no cartoon science."
        ),
        "title_desc_special": "SEO+CTR: how/why + phenomenon + year; explain tags; searchable entity nouns.",
    },
    "islamic": {
        "video_special": "Respectful spiritual English master; faceless metaphors only; warm golden grade.",
        "generation_special": "No idols; no lip-sync; dignified hooks; focus on lessons, architecture, calligraphy textures.",
        "title_desc_special": "SEO: deen topic + lesson; respectful hashtags.",
    },
    "gadget": {
        "video_special": "Honest buyer review; exact model names; product-only hero shots.",
        "generation_special": (
            "One product element per scene; hook with a surprising claim; re-hook each feature beat; "
            "no generic phones."
        ),
        "title_desc_special": "SEO+CTR: product + year + review angle; price/value keywords; honest promise.",
    },
    "motivation": {
        "video_special": "Practical advice; one habit/claim per scene; cinematic lifestyle B-roll.",
        "generation_special": "Hook → proof → action; mid re-hooks; avoid empty slogans.",
        "title_desc_special": "SEO+CTR: habit/mindset keyword + year; specific outcome in title.",
    },
    "health": {
        "video_special": "Evidence-aware; no medical claims as diagnosis; calm clinical visuals.",
        "generation_special": "One tip per scene; curiosity gap then evidence; show body/food metaphors carefully.",
        "title_desc_special": "SEO: symptom/habit + tip; disclaimer-friendly description.",
    },
    "news": {
        "video_special": "Neutral briefing; timestamped facts; no sensational falsehoods.",
        "generation_special": "Headline hook → context → why it matters now; B-roll matched to claim.",
        "title_desc_special": "SEO+CTR: event + date + place; news tags.",
    },
    "finance": {
        "video_special": "Practical money explainers; no guaranteed-return promises; clean charts/metaphors.",
        "generation_special": "One concept per scene; open risk question then clarify; disclaimer in outro.",
        "title_desc_special": "SEO: finance keyword + year; educational tags.",
    },
    "nature": {
        "video_special": "Cinematic wildlife/nature; species/place named when known.",
        "generation_special": "Wonder hook → mechanism → stakes; wide→macro continuity.",
        "title_desc_special": "SEO+CTR: animal/place + wonder angle.",
    },
    "true_crime": {
        "video_special": "Documentary crime; respectful to victims; no gore glorification.",
        "generation_special": "Evidence timeline with open questions then payoffs; desaturated grade; no graphic violence.",
        "title_desc_special": "SEO: case name + year; true crime tags.",
    },
}

def apply_niche_to_channel(channel: Dict[str, Any], *, overwrite_empty_only: bool = True) -> Dict[str, Any]:
    """
    Inject niche_id, niche name, and default specials from Nish catalog.
    Merges per-niche production profile when present (marathon-written).
    Does not wipe user-authored specials unless overwrite_empty_only=False.
    """
    out = dict(channel)
    pack = resolve_niche(out)
    out["niche_id"] = int(pack.get("id") or 0)
    out["niche"] = str(pack.get("name") or out.get("niche") or "Custom")
    family = str(pack.get("style_family") or "history")
    out["niche_style_family"] = family
    defaults = FAMILY_CHANNEL_DEFAULTS.get(family) or FAMILY_CHANNEL_DEFAULTS["history"]

    # Per-niche production profile (topic seeds, overlays, policies)
    profile = None
    try:
        from pipeline.niche_production_profile import load_profile

        profile = load_profile(int(out["niche_id"]))
    except Exception:
        profile = None
    if profile and profile.get("status") in ("COMPLETE", "VERIFIED", "DRAFT"):
        family = str(profile.get("style_family") or family)
        out["niche_style_family"] = family
        defaults = FAMILY_CHANNEL_DEFAULTS.get(family) or defaults
        out["niche_topic_seeds"] = list(profile.get("topic_seeds") or [])[:8]
        out["niche_forbidden_visuals"] = list(profile.get("forbidden_visuals") or [])
        out["niche_preferred_subjects"] = list(profile.get("preferred_subjects") or [])
        out["niche_lighting_default"] = profile.get("lighting_default") or ""
        out["niche_face_policy"] = profile.get("face_policy") or ""
        out["niche_dialogue_tone"] = profile.get("dialogue_tone") or ""
        out["niche_profile_status"] = profile.get("status")

    for key in ("video_special", "generation_special", "title_desc_special"):
        cur = (out.get(key) or "").strip()
        if overwrite_empty_only and cur:
            continue
        if key == "video_special":
            blurb = (pack.get("video_type") or "").strip()
            overlay = ""
            if profile:
                overlay = str(profile.get("video_prompt_overlay") or "")[:280]
            base = (blurb + " | " + defaults[key]).strip(" |") if blurb else defaults[key]
            out[key] = (base + (" | " + overlay if overlay else "")).strip(" |")
        elif key == "generation_special" and profile and profile.get("dialogue_tone"):
            out[key] = (
                f"{defaults[key]} Tone: {profile.get('dialogue_tone')}. "
                f"Lighting: {profile.get('lighting_default') or ''}".strip()
            )
        else:
            out[key] = defaults[key]
    # Stash prompts for director (runtime only; OK if persisted as JSON-ish text)
    topic_p = pack.get("topic_generation_prompt") or ""
    video_p = pack.get("video_prompt") or ""
    if profile:
        if profile.get("topic_prompt_overlay"):
            topic_p = f"{topic_p}\n\n{profile['topic_prompt_overlay']}".strip()
        if profile.get("video_prompt_overlay"):
            video_p = f"{video_p}\n\n{profile['video_prompt_overlay']}".strip()
    out["niche_topic_prompt"] = topic_p
    out["niche_video_prompt"] = video_p
    return out


def director_notes_from_channel(channel: Optional[Dict[str, Any]]) -> str:
    if not channel:
        return ""
    pack = resolve_niche(channel)
    topic_p = str(channel.get("niche_topic_prompt") or pack.get("topic_generation_prompt") or "")
    video_p = str(channel.get("niche_video_prompt") or pack.get("video_prompt") or "")
    parts = [
        f"NISH_ID={pack.get('id')}",
        f"NISH_NAME={pack.get('name')}",
        f"STYLE_FAMILY={channel.get('niche_style_family') or pack.get('style_family')}",
        "TOPIC_GENERATION_PROMPT:",
        topic_p,
        "VIDEO_PROMPT_TEMPLATE:",
        video_p,
    ]
    seeds = channel.get("niche_topic_seeds") or []
    if seeds:
        parts.append("NICHE_TOPIC_SEEDS:")
        parts.extend(f"- {s}" for s in list(seeds)[:8])
    if channel.get("niche_dialogue_tone"):
        parts.append(f"DIALOGUE_TONE: {channel.get('niche_dialogue_tone')}")
    if channel.get("niche_face_policy"):
        parts.append(f"FACE_POLICY: {channel.get('niche_face_policy')}")
    if channel.get("niche_lighting_default"):
        parts.append(f"LIGHTING_DEFAULT: {channel.get('niche_lighting_default')}")
    forbid = channel.get("niche_forbidden_visuals") or []
    if forbid:
        parts.append("FORBIDDEN_VISUALS: " + ", ".join(str(x) for x in forbid[:10]))
    return "\n".join(parts)
