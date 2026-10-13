"""
Canonical prompt engineering for AutoMovie Pro.

Every LLM / Agnes / image / TTS instruction should pull shared contracts from
here so first-shot generation matches English master + visual lock + aspect lock
(short=9:16 vertical, long=16:9 horizontal).
"""
from __future__ import annotations

import re
from typing import List, Optional, Sequence

from pipeline.duration_budget import SECONDS_PER_BEAT, planned_scene_count


def aspect_framing(video_type: str = "short") -> str:
    """Canonical framing phrase for prompts (orientation + ratio)."""
    from pipeline.aspect_lock import (
        LONG_RATIO,
        SHORT_RATIO,
        normalize_video_type,
        size_for_video_type,
    )

    vt = normalize_video_type(video_type)
    size = size_for_video_type(vt)
    if vt == "long":
        return f"HORIZONTAL {LONG_RATIO} landscape ({size})"
    return f"VERTICAL {SHORT_RATIO} portrait ({size})"


def wrong_aspect_ban(video_type: str = "short") -> str:
    from pipeline.aspect_lock import normalize_video_type

    if normalize_video_type(video_type) == "long":
        return "vertical 9:16 portrait, phone-story framing"
    return "landscape 16:9, widescreen horizontal"

# Spoken window inside one Agnes beat: ~8.5s total minus ~1s moving hold.
# 7–9s spoken target → ~16–21 words at 2.3 wps (NOT 12 — that lands ~5s).
SPOKEN_SECONDS_PER_BEAT = 7.5
WORDS_PER_SEC = 2.3
WORDS_PER_BEAT_MIN = 16
WORDS_PER_BEAT_MAX = 21  # ~9.1s — never 35–55 (that blows Agnes)


def sku_tokens(product_name: str) -> List[str]:
    found = re.findall(
        r"\b(?=[A-Za-z0-9\-]*\d)[A-Za-z0-9][A-Za-z0-9\-]{1,24}\b",
        product_name or "",
    )
    out: List[str] = []
    seen = set()
    for tok in found:
        key = tok.lower()
        if key in seen or len(tok) < 2:
            continue
        # Certification / wall-clock stamps are not product SKUs (e.g. 202609091228 cert)
        if tok.isdigit() and len(tok) >= 8:
            continue
        if key.endswith("cert") or key == "cert":
            continue
        seen.add(key)
        out.append(tok)
    return out


# Channel niche / category labels must never become the on-screen EXACT subject.
_ABSTRACT_VISUAL_SUBJECTS = frozenset(
    {
        "space science",
        "science",
        "nature",
        "general",
        "documentary",
        "documentary setting",
        "unknown",
        "education",
        "tech",
        "technology",
        "lifestyle",
        "health",
        "finance",
        "history",
        "news",
        "entertainment",
        "narrator",
        "host",
        "speaker",
        "voiceover",
        "announcer",
        "presenter",
    }
)


def resolve_visual_subject(
    product_name: str = "",
    keywords: Optional[Sequence[str]] = None,
    narration: str = "",
) -> str:
    """Pick a concrete visual subject; never lock prompts to abstract niche labels."""
    name = (product_name or "").strip()
    kw = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    if name and name.lower() not in _ABSTRACT_VISUAL_SUBJECTS and len(name) > 2:
        return name
    for k in kw:
        kl = k.lower()
        if kl in _ABSTRACT_VISUAL_SUBJECTS:
            continue
        if len(k.split()) >= 2 or (len(k) >= 4 and k[:1].isupper()):
            return k
    for k in kw:
        if k.lower() not in _ABSTRACT_VISUAL_SUBJECTS and len(k) >= 3:
            return k
    narr = (narration or "").strip()
    if narr:
        # Prefer a proper-noun phrase from the first clause
        m = re.search(
            r"\b((?:The\s+)?[A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){1,5})\b",
            narr,
        )
        if m:
            return m.group(1).strip()
        return narr.split(",")[0].strip()[:80]
    return name or "documentary subject"


def product_lock_clause(
    product_name: str = "",
    keywords: Optional[Sequence[str]] = None,
    *,
    video_type: str = "short",
) -> str:
    """Must-survive tail: product + SKU fragments + trigger nouns."""
    bits: List[str] = []
    kw = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    name = resolve_visual_subject(product_name, kw)
    if name:
        bits.append(f"EXACT subject on screen: {name}.")
        toks = sku_tokens(name)
        if toks:
            bits.append("SKU tokens that MUST appear: " + ", ".join(toks) + ".")
    if kw:
        bits.append("Visual triggers: " + ", ".join(kw[:8]) + ".")
    bits.append(
        f"{aspect_framing(video_type)}, continuous camera motion, English picture, "
        "no burned captions/watermarks/subtitles, no talking-head."
    )
    return " ".join(bits)


def on_screen_text_rule(element: str = "") -> str:
    """Burned captions are forbidden; device UI is required on display beats."""
    el = (element or "").strip().lower()
    if el in {"display", "software", "ui", "screen"}:
        return (
            "Device screen must be ON with real UI content (never a blank black panel). "
            "Still forbid burned captions, watermarks, logos, and subtitle burn-in."
        )
    return (
        "No burned captions, watermarks, logos, or subtitle burn-in on the picture. "
        "Device UI is allowed only when the beat is about a screen."
    )


def agnes_visual_contract(video_type: str = "short") -> str:
    return (
        f"{aspect_framing(video_type)} cinematic B-roll. Continuous slow push/pan/orbit for the full beat. "
        "Show the EXACT topic/product named in narration (SKU fragments included). "
        "English picture master. No talking-head lip-sync. "
        "No burned captions, watermarks, or subtitle burn-in (soft SRT is added later). "
        "Do not fade to black; keep motion through ~1s after the last spoken syllable. "
        "Audio sounding fine is NOT a visual pass."
    )


def image_still_contract(video_type: str = "short") -> str:
    return (
        f"Photoreal still for Ken Burns: {aspect_framing(video_type)}, sharp subject, "
        "EXACT topic/product + SKU in frame, no burned text/watermark, no talking-head. "
        "Describe only the still photograph — no clip duration and no spoken-word timing."
    )


# Backward-compatible aliases (short / vertical default)
AGNES_VISUAL_CONTRACT = agnes_visual_contract("short")
IMAGE_STILL_CONTRACT = image_still_contract("short")

SPOKEN_MASTER_CONTRACT = (
    "Spoken master is natural English (BCP-47 en-US). "
    "Never Bangla/Hindi/Urdu/Tamil/Malayalam or Banglish/Hinglish on the master. "
    "Keep product/model names, numbers, and place names unchanged. "
    "Other languages are localization later (audio+subs only)."
)

NARRATOR_CONTRACT = (
    "ONE adult male documentary narrator (Gemini Charon timbre). "
    "Never female; never Kore/Aoede/Leda/Jenny/Zephyr. "
    "Same pitch across neighboring clips. Enunciate the FINAL word; do not add extra words."
)

HUMAN_VOICE_CONTRACT = (
    "HUMAN VOICE: Write like a top 1% YouTube creator — specific, uneven, concrete. "
    "Ban AI tells (delve, furthermore, moreover, tapestry, digital landscape, unlock potential, "
    "game-changer, seamlessly, comprehensive guide, in conclusion). "
    "Vary sentence length. Plain verbs. Title = curiosity + exact product/topic + searchable nouns. "
    "Description = short human paragraphs + real hashtags, not an essay."
)

INDUSTRIAL_RETENTION_CONTRACT = (
    "RETENTION (industrial YouTube): The script is the soul of the video. "
    "Never write flat encyclopedia narration. Every beat must EARN the next second of watch time. "
    "Beat 1 = pattern interrupt + open curiosity loop (why/how/what-most-people-miss + topic noun). "
    "Every later beat = NEW information OR a question OR a mini-reveal that re-hooks attention. "
    "Close open loops before outro; leave one soft callback, not emptiness. "
    "Ban cold mid-paragraph opens like 'The telescope floats in deep space…'."
)


def industrial_retention_rules(*, max_seconds: int = 60, video_type: str = "short") -> str:
    """Industrial retention architecture injected into director/script API prompts."""
    vt = (video_type or "short").lower()
    n = planned_scene_count(max_seconds, video_type)
    if vt == "long":
        cadence = (
            f"LONG-FORM (~{max_seconds}s, {n} beats): "
            "0–5s pattern interrupt; 5–15s promise + stakes; then repeating "
            "question → evidence → payoff → new_question every 2–3 beats. "
            "Plant at least 3 open loops and close ≥80% before the final beat."
        )
    else:
        cadence = (
            f"SHORT-FORM (~{max_seconds}s, {n} beats ≈ 8s each): "
            "0–2s scroll-stop interrupt; 2–5s curiosity gap; 5–10s first payoff; "
            "then every remaining beat must add a NEW fact, contrast, question, or reveal. "
            "Never three flat descriptive beats in a row."
        )
    return f"""
INDUSTRIAL RETENTION ARCHITECTURE (mandatory — this is what keeps viewers to the end):
{INDUSTRIAL_RETENTION_CONTRACT}
{cadence}

Beat design checklist (apply to EVERY scene):
A) HOOK LANGUAGE: prefer why/how/what-if/most-people-miss/the-detail-experts-watch — never pure description.
B) OPEN LOOP: each early/mid beat may open a micro-question the viewer needs answered next.
C) PAYOFF CADENCE: within 1–2 beats, pay off the prior loop with a concrete fact or visual claim.
D) INFORMATION DENSITY: each beat delivers one NEW concrete takeaway (no paraphrase recycle).
E) RE-HOOK: mid-script beats (3+) start with a turn, contrast, number, or question — not "Also…".
F) ENDING: final beat resolves the main promise + one memorable closing noun (no black-screen fade essay).
G) NO CTA SPAM in spoken audio (no like/subscribe/hashtags inside narration).

Forbidden flat opens (examples — do NOT write these styles):
- "The James Webb Space Telescope floats in deep space…"
- "Today we will discuss the history of…"
- "In this video I will explain…"
Required open styles (adapt to topic):
- "Most people miss this about {{TOPIC}} — …"
- "Why does {{TOPIC}} change the evidence in the next few seconds?"
- "What {{TOPIC}} just revealed is not what textbooks say — watch the detail."
""".strip()


def industrial_seo_rules(*, video_type: str = "short", year: int = 2026) -> str:
    return f"""
INDUSTRIAL SEO + CTR PACKAGE (mandatory metadata — not spoken):
1) TITLE: searchable primary keyword + curiosity angle + concrete entity (max ~70 chars mind).
   Formula: [Specific Entity/Event] + [Unexpected Angle/Year] — never vague ("Amazing Space Facts").
   Include year {year} when timely. No ALL CAPS spam, no fake "GONE WRONG" clickbait lies.
2) DESCRIPTION: 2–4 short human paragraphs → what viewer learns → soft watch reason → 3–8 real hashtags.
3) TAGS: 8–15 mixed broad+long-tail keywords grounded in the exact topic (entity, niche, year, angle).
4) CTR HONESTY: title promise MUST appear in spoken beats and visuals; no unsupported shock claims.
5) SEO entity lock: title, topic field, and first narration must share the same concrete subject tokens.
6) For {video_type}: optimize for YouTube search + suggested traffic — specificity beats fluff.
""".strip()


def industrial_topic_selection_rules(*, year: int = 2026) -> str:
    return f"""
INDUSTRIAL TOPIC SELECTION (when AUTO-SELECT):
Pick topics that can HOLD attention for the full runtime — not bland encyclopedia subjects.
Required topic traits:
1) Concrete named entity / event / mechanism (not "space is cool").
2) Built-in curiosity gap (conflict, counterintuitive fact, hidden mechanism, stakes).
3) SEO headroom: searchable nouns + {year} relevance when applicable.
4) Visual proof potential: can be shown with clear B-roll / AI footage (not abstract slogans).
5) Retention spine: you can outline hook → reveal → payoff → re-hook before writing scenes.
6) Reject: generic listicles, duplicate angles, vague "top 10", or topics with no openable loop.
Good shape: "Why JWST's hexagonal mirrors catch light older galaxies hide from Hubble"
Bad shape: "Interesting facts about telescopes"
""".strip()


def human_voice_contract() -> str:
    return HUMAN_VOICE_CONTRACT


def spoken_word_budget_rules(*, max_seconds: int = 120, video_type: str = "short") -> str:
    n = planned_scene_count(max_seconds, video_type)
    return (
        f"HARD RULE — each dialogue/scene spoken beat MUST land in the 7–9 second window "
        f"({WORDS_PER_BEAT_MIN}–{WORDS_PER_BEAT_MAX} English words ≈ {SPOKEN_SECONDS_PER_BEAT:.0f}s at "
        f"{WORDS_PER_SEC} wps, then ~1s moving hold; total beat ≈ {SECONDS_PER_BEAT}s). "
        f"NEVER write under ~7s (too thin) or over ~9s (Agnes cut risk); NEVER 35–55 words in one scene. "
        f"Story continuity: each dialogue must feel like the next beat of ONE story — bridge from the "
        f"previous claim with a shared entity, place, or consequence (no random topic jumps). "
        f"{(video_type or 'short').title()} {max_seconds}s needs {n} scenes "
        f"(~{SECONDS_PER_BEAT}s/beat), not fewer longer monologues."
    )


def face_policy_for_niche(niche: str = "") -> str:
    n = (niche or "").lower()
    if any(x in n for x in ("gadget", "tech", "phone", "review", "গ্যাজেট")):
        return (
            "Gadget: product-only hero. Hands OK if the exact device is clear. "
            "No talking-head / lip-sync avatar."
        )
    if any(x in n for x in ("islam", "deen", "quran", "muslim")):
        return "Islamic: strictly faceless metaphors; no talking-head; no idols."
    if any(x in n for x in ("true crime", "serial", "forensic")):
        return "True crime: silhouettes only; never glorify violence; no talking-head."
    if any(x in n for x in ("news", "geopolit")):
        return "News: wide/crowd OK; no fabricated politician lip-sync."
    # Space / science / nature documentary — portraits are wrong subjects (C11 FINAL evidence).
    if any(
        x in n
        for x in (
            "space",
            "science",
            "astro",
            "telescope",
            "nasa",
            "galaxy",
            "cosmos",
            "physics",
            "nature",
            "wrath",
            "earth",
            "ocean",
            "climate",
            "wildlife",
        )
    ):
        return (
            "Documentary science/nature: NO human faces, NO portraits, NO talking-heads, "
            "NO lip-sync avatars. Show instruments, landscapes, phenomena, animals, or "
            "environment only."
        )
    return (
        "Silent cinematic humans OK when the niche allows. "
        "Talking-head / lip-sync AI avatar is ALWAYS a critical fail."
    )


def system_for_purpose(purpose: str, *, json_mode: bool = False, video_type: str = "short") -> str:
    """Default OpenAI-compat system message — never a generic 'helpful assistant'."""
    p = (purpose or "script").strip().lower()
    json_bit = " Respond with valid JSON only. No markdown." if json_mode else ""
    if p in {"script", "director"}:
        return (
            "You are AutoMovie Pro Industrial Niche Director — world-class YouTube showrunner. "
            f"Plan English-master documentary beats with matched {aspect_framing(video_type)} B-roll. "
            "Script is the soul: pattern-interrupt hook, open/close curiosity loops, "
            "new information every beat, SEO-honest title/description/tags. "
            "One claim per scene. Exact product/topic on screen. No burned captions. No talking-head. "
            + HUMAN_VOICE_CONTRACT
            + " "
            + INDUSTRIAL_RETENTION_CONTRACT
            + json_bit
        )
    if p == "translate":
        return (
            "You are AutoMovie Pro Cultural Localization Writer — NOT a machine translator. "
            "Rewrite the narration so it feels originally authored in the target language: "
            "native emotion, cultural tone, dignity, and spoken cadence. "
            "Preserve facts, product/model names, numbers, and place names (Latin form). "
            "Respect faith and cultural sensitivity. "
            "Never sound like a word-for-word translation. "
            "Output ONLY the localized narration — no titles, labels, or bilingual notes."
        )
    if p == "agent":
        return (
            "You are AutoMovie Pro Hybrid Automation Agent. Explain like the user is 10. "
            "English picture+script master; Charon male narrator; dry-run is not live publish. "
            "Talk naturally — never robotic corporate AI."
            + json_bit
        )
    if p in {"critic", "repair"}:
        return (
            "You are AutoMovie Pro Industrial Critic. "
            "For AV: fail wrong_subject, missing SKU, talking-head, burned captions, non-English master. "
            "For SCRIPT compliance: fail weak hooks, flat encyclopedia beats, missing mid re-hooks, "
            "vague non-SEO titles, or endings that never close the open loop. "
            "Evidence over praise. JSON when requested."
            + json_bit
        )
    return (
        "You are AutoMovie Pro. English master, exact subject on screen, "
        f"{aspect_framing(video_type)}, no burned captions. "
        + HUMAN_VOICE_CONTRACT
        + json_bit
    )


def director_av_sync_rules(*, max_seconds: int = 120, video_type: str = "short") -> str:
    framing = aspect_framing(video_type)
    return f"""
DIALOGUE RULES (strict):
1) {SPOKEN_MASTER_CONTRACT}
2) Natural spoken documentary English — not essay text. {HUMAN_VOICE_CONTRACT}
3) {spoken_word_budget_rules(max_seconds=max_seconds, video_type=video_type)}
4) Each scene = ONE element + ONE claim + concrete viewer takeaway.
5) No filler. NEVER repeat the same claim, fact, or near-paraphrase across scenes.
   Every beat must introduce NEW information the viewer has not heard yet.
6) Never put hashtags, SEO tags, or "like and subscribe" spam inside spoken narration.
7) Character/environment/lighting continuity when the Nish video prompt requires it.
8) Title/description must sound human-written (no ChatGPT cadence).

{industrial_retention_rules(max_seconds=max_seconds, video_type=video_type)}

{industrial_seo_rules(video_type=video_type)}

AV-SYNC / FOOTAGE RULES (strict):
1) keyword_triggers = 2–5 English visual nouns from THIS beat. For gadgets include the full model AND SKU fragments (Pixel + 9a).
2) exact_ai_video_prompt = FULL English Agnes prompt for THIS beat only:
   {framing} + exact subject/SKU + action + camera move + lighting + niche grade
   + {on_screen_text_rule()}
   + no talking-head. NEVER use {wrong_aspect_ban(video_type)}.
3) visual_query / visual_prompt = shorter search/legacy fields (still required).
4) Spoken beat and picture MUST match keyword_triggers. Pretty unrelated B-roll is a fail.
5) Prefer faceless cinematic metaphors; follow niche face policy.
6) start_hint_s / end_hint_s approximate timeline.
7) Do NOT end beats on black; keep motion through ~1s post-dialogue room.
8) Copy the topic/product name VERBATIM into exact_ai_video_prompt — never a generic phone/forest.
9) Non-gadget niches MUST use story elements (intro/context/discovery/technique/legacy/outro)
   — NEVER gadget slots like camera/battery/software/price unless the niche is gadget review.
10) FIRST beat = PATTERN INTERRUPT + curiosity gap (industrial retention). NEVER open mid-description
   like "The telescope floats in deep space…". Open with why/how/what-most-people-miss + topic noun,
   then pay off in beat 2–3. Second beat = promise / evidence. No cold mid-paragraph starts.
11) Mid beats MUST re-hook (question, contrast, number, reveal). Flat "Also…" chaining is a fail.
12) Final beat MUST close the main open loop with a concrete closing noun — no empty outro filler.
""".strip()


def director_json_scene_example(*, video_type: str = "short") -> str:
    framing = aspect_framing(video_type)
    return f"""
Return JSON:
{{
  "analysis": {{
    "niche_summary": "...",
    "why_this_topic": "retention spine: hook → open loop → payoff → re-hook",
    "audience": "...",
    "tone": "industrial documentary urgency without hype",
    "product_category": "phone|earbuds|watch|laptop|camera|handheld|science|mystery|history|islamic|motivation|health|news|finance|nature|true_crime|other",
    "style_pack": "{{style_pack}}",
    "nish_id": {{nish_id}},
    "avoided_duplicates": ["..."],
    "retention_spine": "one-line: open loop → evidence → payoff → new question"
  }},
  "topic": "Exact topic or product/model name (SEO-specific entity)",
  "product_key_hint": "normalized lowercase tokens",
  "title": "CTR+SEO title: exact entity + curiosity angle + searchable nouns (honest, no fake shock)",
  "description": "2-4 short SEO paragraphs: what you learn + why watch to end + real hashtags",
  "tags": ["primary keyword", "long-tail", "entity", "year", "niche angle"],
  "scenes": [
    {{
      "element": "intro|context|discovery|technique|legacy|outro (history) OR intro|design|camera|battery|outro (gadget only)",
      "retention_role": "pattern_interrupt|curiosity_gap|first_payoff|question|evidence|payoff|new_question|ending",
      "open_loop": "optional micro-question planted for the next beat",
      "payoff_for": "optional prior loop this beat closes",
      "start_hint_s": 0,
      "end_hint_s": 8,
      "narration": "Most people miss this about the EXACT topic — why it matters in the next few seconds. UNIQUE curiosity hook, no hashtags.",
      "keyword_triggers": ["topic-or-SKU", "hero", "macro"],
      "exact_ai_video_prompt": "{framing} cinematic slow push-in of the EXACT topic/product named in narration, niche color grade, continuous motion, no burned captions, no watermark, no talking-head",
      "visual_query": "exact topic hero documentary",
      "visual_prompt": "cinematic hero of exact topic, continuous motion",
      "quality_notes": "SKU on screen, continuity with next beat, retention role honored"
    }}
  ]
}}
""".strip()


def precheck_instruction(
    *,
    niche: str,
    element: str,
    product_name: str,
    narration: str,
    keywords: Sequence[str],
    exact_ai_video_prompt: str,
    trained_txt: str,
    video_type: str = "short",
) -> str:
    framing = aspect_framing(video_type)
    return f"""
You are AutoMovie Pro PRE-GENERATION Prompt Auditor.
BEFORE any video is generated, decide if this Agnes prompt will visually match the English master narration.
{SPOKEN_MASTER_CONTRACT}
{agnes_visual_contract(video_type)}
{face_policy_for_niche(niche)}
{on_screen_text_rule(element)}
{product_lock_clause(product_name, keywords, video_type=video_type)}

Niche: {niche or "general"}
Element: {element or "feature"}
Product/topic: {product_name or "n/a"}
Aspect lock: {framing}

Spoken English master narration:
\"\"\"{narration}\"\"\"

Keyword triggers that MUST be visualized (product/SKU first):
{list(keywords)}

Proposed Agnes prompt:
\"\"\"{exact_ai_video_prompt}\"\"\"

Learned hard rules from marathon training:
{trained_txt}

FAIL if: missing product/SKU tokens, vague "cinematic shot" with no subject, talking-head risk, burned-caption request, {wrong_aspect_ban(video_type)}, or off-topic metaphor.

Return STRICT JSON:
{{
  "prompt_score": 0-100,
  "passed": true/false,
  "issues": ["..."],
  "missing_triggers": ["..."],
  "risk_flags": ["wrong_subject"|"unrelated_metaphor"|"talking_head"|"vague"|"no_motion"|"burned_captions"|"wrong_aspect"|...],
  "fixed_prompt": "improved FULL English Agnes prompt: {framing}, exact subject+SKU, camera move, lighting, niche grade, {on_screen_text_rule(element)}"
}}
Pass if prompt_score >= 80 AND missing_triggers empty AND no wrong_subject/talking_head/burned_captions risk.
""".strip()


def critic_instruction(
    *,
    niche: str,
    element: str,
    product_name: str,
    narration: str,
    keywords: Sequence[str],
    exact_ai_video_prompt: str,
    trained_txt: str,
    video_dur: float,
    audio_dur: float,
    pass_score: int,
    video_type: str = "short",
) -> str:
    framing = aspect_framing(video_type)
    return f"""
You are AutoMovie Pro AV-Sync Critic — elite multimodal judge.
Watch/listen and decide if VISUALS match the spoken English master.
Audio sounding fine is NEVER a visual pass.

{SPOKEN_MASTER_CONTRACT}
{agnes_visual_contract(video_type)}
{face_policy_for_niche(niche)}
{on_screen_text_rule(element)}
{product_lock_clause(product_name, keywords, video_type=video_type)}

Niche: {niche or "general"}
Element beat: {element or "feature"}
Product/topic: {product_name or "n/a"}
Aspect lock: {framing}
Video duration (s): {video_dur:.2f}
Audio duration (s): {audio_dur:.2f}

Spoken English master narration:
\"\"\"{narration}\"\"\"

Keyword triggers that MUST appear visually (metaphor or literal):
{list(keywords)}

Current Agnes generation prompt:
\"\"\"{exact_ai_video_prompt}\"\"\"

HARD RULES LEARNED FROM MARATHON TRAINING:
{trained_txt}

Judge:
1) On-screen action depicts English narration meaning AND keyword/SKU triggers?
2) Wrong product/object / unrelated B-roll? Score must be <40 and include wrong_subject.
3) Talking-head / lip-sync avatar?
4) Motion for the full beat (not a static still)?
5) If audio is much longer than unique visual content (looped short clip), FAIL duration_mismatch.
6) Spoken track must be English. Bangla/Hindi/Hinglish on the master is master_not_english.
7) Burned-in English captions on the picture = burned_master_subs (soft SRT only).
8) Wrong aspect ({wrong_aspect_ban(video_type)}) = wrong_aspect FAIL.
9) If mismatch: write a BETTER exact_ai_video_prompt that NAMES the product/SKU + keywords + {framing} + camera move.

Return STRICT JSON only:
{{
  "match_score": 0-100,
  "passed": true/false,
  "issues": ["short concrete issue codes"],
  "critical_issues": ["wrong_subject"|"unrelated_broll"|"talking_head"|"visual_anchors_missing"|"master_not_english"|"burned_master_subs"|"voice_drift"|"wrong_aspect"|...],
  "matched_keywords": ["..."],
  "missed_keywords": ["..."],
  "visual_summary": "what you actually see",
  "audio_summary": "what narration claims",
  "revised_prompt": "full Agnes-ready English {framing} prompt naming exact subject+SKU, motion, lighting; no burned captions; no talking-head"
}}
Pass rule: match_score >= {pass_score} AND critical_issues empty.
If a product/SKU trigger is missing on screen, include visual_anchors_missing and fail.
""".strip()


def meta_audit_instruction(
    *,
    narration: str,
    keywords: Sequence[str],
    agent_blob: str,
) -> str:
    return f"""
You are AutoMovie Pro META-AUDITOR over the AV-sync critic.
Decide if the agent's verdict was correct. Audio-only pass with wrong picture = false_pass.

{SPOKEN_MASTER_CONTRACT}
{AGNES_VISUAL_CONTRACT}

Spoken English master:
\"\"\"{narration}\"\"\"

Keywords/SKU that must be on screen: {list(keywords)}

Agent critique JSON:
{agent_blob}

Return STRICT JSON:
{{
  "agent_was_correct": true/false,
  "error_type": "none"|"false_pass"|"false_fail"|"weak_revised_prompt"|"missed_critical",
  "your_match_score": 0-100,
  "your_passed": true/false,
  "explanation": "short",
  "training_rule": "one durable rule the agent should always follow next time, or empty if none"
}}
If the agent passed a clip that misses the product/SKU, error_type=false_pass and write a training_rule.
""".strip()


def sanitize_generation_prompt(text: str) -> str:
    """Strip critic/API junk that must never reach Agnes."""
    out = (text or "").strip()
    out = re.sub(r"Fix prior issues:.*?(?:avatar\.?|$)", "", out, flags=re.I | re.S)
    out = re.sub(r"RESOURCE_EXHAUSTED.*?(?:on thi\.?|$)", "", out, flags=re.I | re.S)
    out = re.sub(r"critic_api_failed:\S*", "", out, flags=re.I)
    out = re.sub(r"precheck_(?:no_keys|api_failed|google_circuit_open)", "", out, flags=re.I)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def revised_visual_prompt(
    *,
    narration: str,
    keywords: Sequence[str],
    exact_ai_video_prompt: str,
    product_name: str,
    element: str,
    issues: Optional[Sequence[str]] = None,
    video_type: str = "short",
) -> str:
    """API-less improved Agnes prompt — never concatenate quota error strings."""
    base = sanitize_generation_prompt(exact_ai_video_prompt)
    if len(base) < 24:
        base = (
            f"{aspect_framing(video_type)} cinematic slow push-in visualizing: "
            f"{(narration or product_name or element or 'subject')[:160]}"
        )
    clean_issues = [
        str(i).strip()
        for i in (issues or [])
        if str(i).strip()
        and "RESOURCE" not in str(i).upper()
        and "critic_api" not in str(i).lower()
        and "precheck_" not in str(i).lower()
    ][:4]
    issue_bit = f" Prior visual faults to fix: {'; '.join(clean_issues)}." if clean_issues else ""
    return (
        f"{base} {product_lock_clause(product_name, keywords, video_type=video_type)} "
        f"{on_screen_text_rule(element)}{issue_bit} "
        "Shallow depth of field, sharp focus, continuous motion."
    ).strip()


def agnes_generation_wrapper(
    core_prompt: str,
    *,
    product_name: str = "",
    keywords: Optional[Sequence[str]] = None,
    narration_hint: str = "",
    niche_mod: str = "",
    video_type: str = "short",
) -> str:
    core = sanitize_generation_prompt(core_prompt)
    speak = ""
    if (narration_hint or "").strip():
        speak = (
            f' Speak this English narration exactly, in {NARRATOR_CONTRACT} '
            f'"{narration_hint.strip()[:220]}"'
        )
    else:
        speak = (
            " Generate MATCHING spoken English narration IN SYNC with the visuals. "
            + NARRATOR_CONTRACT
        )
    return (
        f"{core} {product_lock_clause(product_name, keywords, video_type=video_type)} {niche_mod} "
        f"{agnes_visual_contract(video_type)} {speak} "
        "After the last spoken word, keep the picture moving for at least one full second."
    ).strip()


def agnes_negative(video_type: str = "short") -> str:
    return (
        "blurry, watermark, logo overlay, burned-in text, burned-in subtitles, "
        f"wrong subject, generic stand-in phone, {wrong_aspect_ban(video_type)}, "
        "low quality, talking-head lip-sync avatar close-up, "
        "switching narrator gender mid-clip, female then male voice, "
        "Kore Aoede Jenny voice, robotic glitch audio, silent video with no narration, "
        "fade to black ending"
    )


AGNES_NEGATIVE = agnes_negative("short")


def translate_instruction(
    *,
    text: str,
    src_display: str,
    tgt_display: str,
    domain_hint: str,
    target_lang: str = "",
    culture_brief: str = "",
) -> str:
    """Cultural localization prompt — native rewrite, not literal MT."""
    brief = (culture_brief or "").strip()
    if not brief and target_lang:
        try:
            from pipeline.lang_config import localization_culture_brief

            brief = localization_culture_brief(target_lang)
        except Exception:
            brief = ""
    culture_block = f"\nLocale voice guide:\n{brief}\n" if brief else "\n"

    return f"""Culturally LOCALIZE (not word-for-word translate) this {src_display} {domain_hint}
into natural spoken {tgt_display} documentary narration.

Goal:
- Listener must feel the script was originally written in {tgt_display}.
- STRICTLY ENFORCE maintaining the original emotional gravity, urgency, and tone of {tgt_display}.
- Adapt idioms and phrasing to the target culture; keep the SAME facts and claims.
- Respect religious and cultural sensitivity for that language community.
- Sound beautiful when spoken aloud (TTS) — never stiff machine-translation cadence.
{culture_block}
Hard rules:
- Preserve meaning, spoken pacing intent, and emotional intent — adapt expression.
- Keep product/model names, SKUs, numbers, and place names in their original Latin form
  (do not translate Pixel, 9a, iPhone, Chernobyl, NASA, JWST).
- Do NOT invent new facts, drop closing claims, or reverse negation/time order.
- Do NOT add titles, labels, prefaces, commentary, or a second language.
- Output ONLY the localized narration — one spoken paragraph.
- If the target is English: real English sentences, never Banglish/Hinglish.

Source text:
\"\"\"{text}\"\"\"
""".strip()


def condense_instruction(*, text: str, target_seconds: int, max_seconds: int) -> str:
    return f"""Condense this English documentary narration to about {int(target_seconds)} seconds when spoken
(max {int(max_seconds)} seconds, ~{WORDS_PER_SEC} words/sec).
Keep the core facts, the exact product/topic names, and the LAST claim — never drop the closing noun.
Output ONLY the condensed English narration, no quotes or labels.

Text:
\"\"\"{text}\"\"\"
""".strip()


def trending_instruction(*, count: int, block_txt: str, year: int = 2026, niche: str = "") -> str:
    nl = (niche or "").lower()
    if any(k in nl for k in ("islam", "deen", "quran", "muslim")):
        topic_domain = "Islamic history, Quranic reflections, Golden Age scientific discoveries, and spiritual wisdom"
    elif any(k in nl for k in ("cook", "food", "recipe", "baking")):
        topic_domain = "culinary recipes, gastronomy techniques, viral kitchen methods, and food science"
    elif any(k in nl for k in ("financ", "crypto", "money", "invest", "stock")):
        topic_domain = "market dynamics, cryptocurrency developments, investment strategies, and personal finance"
    elif any(k in nl for k in ("health", "fit", "diet", "sleep", "workout", "longevity")):
        topic_domain = "evidence-based health discoveries, longevity science, nutrition, and metabolic wellness"
    elif any(k in nl for k in ("motivat", "habit", "mindset", "productiv", "discipline")):
        topic_domain = "high-performance discipline, habit architecture, cognitive focus, and stoic mindset"
    elif any(k in nl for k in ("histor", "ancient", "civiliz", "archaeolog")):
        topic_domain = "unsolved ancient history mysteries, archaeological revelations, and civilizational turns"
    else:
        topic_domain = "consumer electronics and technology trends (phones, earbuds, smart devices, cameras)"

    return f"""You have up-to-date knowledge of trending topics in {topic_domain}.
List the top {count} MOST TRENDING specific topics/subjects right now worldwide ({year}).

NEVER include these already-covered / blocked topics (or near-duplicates):
{block_txt}

Each item must be a concrete, compelling topic/subject name (not a generic vague phrase).

Return STRICT JSON:
{{
  "topics": [
    {{
      "name": "exact specific topic name",
      "why_trending": "one short reason",
      "search_query": "search query for verification",
      "category": "category of topic"
    }}
  ]
}}
Only JSON, no markdown.
""".strip()


def script_bundle_instruction(
    *,
    channel_name: str,
    niche: str,
    focus: str,
    research_notes: str,
    video_type: str,
    max_sec: int,
    video_special: str,
    generation_special: str,
    title_desc_special: str,
    example_script: str,
    islamic_mode: bool = False,
) -> str:
    n = planned_scene_count(max_sec, video_type)
    is_islamic = islamic_mode or any(k in (niche or "").lower() for k in ("islam", "deen", "quran", "muslim"))
    islamic_directive = (
        "ISLAMIC ETIQUETTE & HOOK RETENTION (MANDATORY): For Shorts, deliver the high-impact curiosity hook punchline in the first 2 seconds FIRST, then place the greeting naturally right after the hook punchline (never waste the opening 2-3 seconds of a fast vertical short on generic greetings). For Long videos, include a warm Islamic greeting ('Assalamu Alaikum' / 'আসসালামু আলাইকুম') in Scene 1. Conclude the final scene with a gracious closing ('Jazakallah Khairan', 'Allah Hafez' / 'আল্লাহ হাফেজ')."
        if is_islamic else ""
    )
    return f"""
You are AutoMovie Pro industrial English-master script writer for channel: {channel_name}.
Niche: {niche}
Main topic / product: {focus}
Research notes: {research_notes or "none"}
Video type: {video_type} (HARD max {max_sec} seconds)
{spoken_word_budget_rules(max_seconds=max_sec, video_type=video_type)}
{SPOKEN_MASTER_CONTRACT}
{HUMAN_VOICE_CONTRACT}
{industrial_retention_rules(max_seconds=max_sec, video_type=video_type)}
{industrial_seo_rules(video_type=video_type)}
Special video recommendations: {video_special or "none"}
Generation recommendations: {generation_special or "none"}
Title/description recommendations: {title_desc_special or "none"}
Example script style (optional): {example_script or "none"}
{islamic_directive}

SOCIAL CALL-TO-ACTION (MANDATORY):
In the final outro scene, include an engaging spoken Call-To-Action (CTA) encouraging viewers to like the video, leave their thoughts in the comments, share with friends and family, and subscribe/follow for the next episode.

Return STRICT JSON with keys:
title, description, tags (array of strings), script (spoken narration),
scenes (array of {{"narration": "...", "visual": "...", "retention_role": "...", "open_loop": "...", "payoff_for": "..."}} — HARD {n} items).
Scene 1 MUST be a pattern-interrupt curiosity hook naming the exact topic.
Every later scene MUST add NEW information or a re-hook question/reveal — never flat description chains.
Each visual must name the exact topic/product + {aspect_framing(video_type)} cinematic motion.
Keep total spoken length suitable for max {max_sec} seconds.
Title/description must be SEO+CTR industrial grade and human-written. Description: short paragraphs + hashtags.
""".strip()


def image_beat_prompt(
    *,
    art_style: str,
    profile_name: str,
    visual_description: str,
    keywords: Sequence[str],
    anchors: Sequence[str],
    beat_text: str,
    beat_index: int,
    beat_count: int,
    seed: int,
    video_type: str = "short",
) -> str:
    """Ken Burns still — must not inherit Agnes AV timing rules."""
    return (
        f"{art_style}. Scene lock: {profile_name} — {visual_description}. "
        f"{image_still_contract(video_type)} "
        f"{product_lock_clause(profile_name, list(keywords) or list(anchors), video_type=video_type)} "
        f"DIALOGUE nouns to show: {', '.join(list(anchors)[:6]) or beat_text[:80]}. "
        f"Beat {beat_index + 1}/{beat_count}: {beat_text[:180]}. seed={seed}."
    )[:950]


def truncate_keep_lock(text: str, *, limit: int, product_name: str = "", keywords: Optional[Sequence[str]] = None, video_type: str = "short") -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if len(raw) <= limit:
        return raw
    tail = product_lock_clause(product_name, keywords, video_type=video_type)
    budget = max(80, limit - len(tail) - 1)
    head = raw[:budget].rsplit(" ", 1)[0]
    return (head + " " + tail).strip()[:limit]


def agnes_vs_image_hard_rules(*, for_image: bool, element: str = "", video_type: str = "short") -> List[str]:
    shared = [
        f"{aspect_framing(video_type)}. Continuous motion. Exact subject/SKU on screen.",
        on_screen_text_rule(element),
        "NO talking-head lip-sync avatar; prefer cinematic metaphor / environment / objects.",
        "Keep subject and environment consistent with the narration mood and keywords.",
        "STRICT: important nouns/places/objects spoken in this beat MUST appear visually.",
        "Do not fade to black at the end.",
    ]
    if for_image:
        shared.append(
            "IMAGE STILL: photoreal frame only. Motion is added later. "
            "Do not mention speech timing or spoken-word finish rules."
        )
    else:
        shared.extend(
            [
                "Finish EVERY spoken word before the clip ends; never cut mid-syllable.",
                "After the last spoken syllable leave ~1s while the picture KEEPS MOVING.",
            ]
        )
    return shared
