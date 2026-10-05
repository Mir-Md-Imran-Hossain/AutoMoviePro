"""
English-master (pivot) language policy.

Industry pattern (broadcast / AI dubbing 2026):
  lock one English picture+script master (BCP-47 en-US), then localize audio+subs.
  Dubformer/ElevenLabs-style: explicit sourceLanguage, hard TTS language gate,
  glossary-aware repair, never naive "replace language name" on operator notes.
Bangla/Hindi/Urdu/Tamil/Malayalam are TARGETS, never the generation master.

This module is the single source of truth used by director, TTS, critic, and generate.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from pipeline.lang_config import MASTER_VOICE_NAME, SOURCE_LANG, SOURCE_LANG_BCP47, TARGET_LANG_CODES

logger = logging.getLogger(__name__)

# Unicode blocks that must NOT appear in the English master script.
_SCRIPT_RANGES: Tuple[Tuple[str, int, int], ...] = (
    ("bn", 0x0980, 0x09FF),  # Bengali
    ("hi", 0x0900, 0x097F),  # Devanagari
    ("ta", 0x0B80, 0x0BFF),  # Tamil
    ("ml", 0x0D00, 0x0D7F),  # Malayalam
    ("ur", 0x0600, 0x06FF),  # Arabic (Urdu)
    ("gu", 0x0A80, 0x0AFF),
    ("pa", 0x0A00, 0x0A7F),
    ("te", 0x0C00, 0x0C7F),
    ("kn", 0x0C80, 0x0CFF),
)

# High-signal Bangla words even if someone mixed scripts poorly
_BANGLA_HINTS = (
    "আজকের",
    "রিভিউ",
    "ব্যাটারি",
    "ডিসপ্লে",
    "প্রসেসর",
    "ধন্যবাদ",
    "কমেন্টে",
    "বাংলাদেশ",
    "আসসালামু",
)

# Romanized Bangla/Hindi the Unicode detector would miss (director Banglish leak).
# Distinctive tokens only — require 2 hits (or 1 hit on a short line).
_ROMANIZED_BN = frozenset(
    {
        "ajker",
        "aajker",
        "ashun",
        "asun",
        "dhonnobad",
        "kemon",
        "achho",
        "achhen",
        "ekhon",
        "tarpor",
        "kintu",
        "karon",
        "jonno",
        "niben",
        "jaben",
        "dekhun",
        "bhalo",
        "kharap",
        "onek",
        "kichu",
        "amra",
        "apnara",
        "apni",
        "amake",
        "tomar",
        "tader",
        "hoyeche",
        "korben",
        "kothay",
        "shudhu",
        "bondhura",
        "janaben",
        "korun",
        "dekho",
        "ashchi",
        "thakben",
    }
)
_ROMANIZED_HI = frozenset(
    {
        "bataenge",
        "dekhein",
        "dosto",
        "kyunki",
        "lekin",
        "bahut",
        "nahi",
        "aaj",
        "dekhiye",
        "chaliye",
        "kripya",
        "dhanyavaad",
        "kyaa",
    }
)

_VISUAL_FIELDS = (
    "visual_prompt",
    "exact_ai_video_prompt",
    "visual_query",
    "visual",
    "quality_notes",
)


def rewrite_master_language_instructions(text: str) -> str:
    """
    Stop leftover channel specials from ordering Bangla as the *master* script.

    Must NOT rewrite localization-target mentions
    (e.g. "Bangla/other languages are localization-only").
    """
    raw = text or ""
    if not raw:
        return raw

    placeholders: List[str] = []

    def _stash(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"\x00LOC{len(placeholders) - 1}\x00"

    protected = re.sub(
        r"(?is)"
        r"(?:bangla|বাংলা)[\s/,&-]*(?:other languages|hindi|urdu|tamil|malayalam)?"
        r"[^\n.]{0,80}localization(?:-only)?"
        r"|localization(?:-only)?[^\n.]{0,80}(?:bangla|বাংলা)"
        r"|bangla\s*/\s*other languages are localization-only",
        _stash,
        raw,
    )

    out = protected
    out = re.sub(r"\bBangla narration\b", "English narration (master)", out, flags=re.I)
    out = re.sub(r"\bBangla explainers\b", "English explainers", out, flags=re.I)
    out = re.sub(r"\bBD buyer Bangla review\b", "buyer English review", out, flags=re.I)
    out = re.sub(r"\bSpoken Bangla\b", "Spoken English", out, flags=re.I)
    out = re.sub(
        r"\bSpoken language:\s*natural Bangla\b",
        "Spoken language: natural English",
        out,
        flags=re.I,
    )
    out = re.sub(
        r"\bwrite (?:the )?(?:script|narration|dialogue) in Bangla\b",
        "write the script in English",
        out,
        flags=re.I,
    )
    out = re.sub(
        r"\bBangla (review|script|dialogue|voiceover|explainer)s?\b",
        r"English \1",
        out,
        flags=re.I,
    )
    out = re.sub(r"(?i)\b(?:in|into|as)\s+Bangla\b", "in English", out)
    out = out.replace("বাংলা ন্যারেশন", "English narration (master)")
    out = out.replace("বাংলা রিভিউ", "English review")
    # Remaining native-script বাংলা in operator notes is almost always a master-language order.
    out = out.replace("বাংলা", "English")

    for i, saved in enumerate(placeholders):
        out = out.replace(f"\x00LOC{i}\x00", saved)
    return out


DIRECTOR_MASTER_LANGUAGE_RULES = """
MASTER LANGUAGE LOCK (non-negotiable):
- Spoken narration, title, and description MUST be natural spoken English (BCP-47 en-US).
- This is the English picture+audio MASTER. Other languages are added later by
  replacing audio + subtitles only (never by rewriting this script in Bangla).
- Keep product/model names, numbers, and place names in their original English form.
- Do NOT output Bangla, Hindi, Urdu, Tamil, or Malayalam in narration fields.
- Do NOT write romanized Bangla/Hindi (Banglish/Hinglish) — use real English sentences.
- Visual prompts, keyword_triggers, and tags stay English (Agnes + SEO).
""".strip()

CRITIC_MASTER_LANGUAGE_LABEL = "Spoken English master narration"


def _letters(text: str) -> List[str]:
    return [ch for ch in (text or "") if ch.isalpha() or ("\u0900" <= ch <= "\u0D7F") or ("\u0600" <= ch <= "\u06FF")]


def script_char_counts(text: str) -> Dict[str, int]:
    counts = {code: 0 for code, _, _ in _SCRIPT_RANGES}
    counts["latin"] = 0
    counts["other"] = 0
    for ch in _letters(text):
        o = ord(ch)
        hit = False
        for code, lo, hi in _SCRIPT_RANGES:
            if lo <= o <= hi:
                counts[code] += 1
                hit = True
                break
        if hit:
            continue
        if "A" <= ch <= "Z" or "a" <= ch <= "z":
            counts["latin"] += 1
        else:
            counts["other"] += 1
    return counts


def _romanized_hint_lang(text: str) -> Optional[str]:
    tokens = re.findall(r"[A-Za-z]+", (text or "").lower())
    if not tokens:
        return None
    bn = sum(1 for t in tokens if t in _ROMANIZED_BN)
    hi = sum(1 for t in tokens if t in _ROMANIZED_HI)
    if bn >= 2:
        return "bn"
    if hi >= 2:
        return "hi"
    return None


def dominant_non_english_lang(text: str) -> Optional[str]:
    counts = script_char_counts(text)
    total = sum(counts.values()) or 1
    best_code = ""
    best_n = 0
    for code, _, _ in _SCRIPT_RANGES:
        n = counts.get(code, 0)
        if n > best_n:
            best_n = n
            best_code = code
    if best_n / total >= 0.08 and best_n >= 4:
        return best_code if best_code in TARGET_LANG_CODES else "bn"
    if any(h in (text or "") for h in _BANGLA_HINTS):
        return "bn"
    return _romanized_hint_lang(text)


def looks_like_english_master(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    if dominant_non_english_lang(text):
        return False
    counts = script_char_counts(text)
    letters = sum(counts.values())
    if letters < 8:
        # short English hooks like "Here is why." still OK if latin present
        return counts["latin"] >= 3 and not any(counts[c] for c, _, _ in _SCRIPT_RANGES)
    return (counts["latin"] / letters) >= 0.70


def master_lang_issues(text: str, *, field: str = "narration") -> List[str]:
    issues: List[str] = []
    if not (text or "").strip():
        issues.append(f"{field}_empty")
        return issues
    code = dominant_non_english_lang(text)
    if code:
        issues.append(f"{field}_not_english_master:{code}")
    elif not looks_like_english_master(text):
        issues.append(f"{field}_english_confidence_low")
    return issues


def _generic_english_beat(element: str, topic: str) -> str:
    el = (element or "feature").strip() or "feature"
    top = (topic or "this topic").strip() or "this topic"
    return f"This beat covers the {el} of {top} — one clear claim, matched to the picture."


def _generic_english_visual(element: str, topic: str) -> str:
    el = (element or "scene").strip() or "scene"
    top = (topic or "the subject").strip() or "the subject"
    return (
        f"cinematic {el} of {top}, documentary lighting, continuous motion, "
        "no text, no watermark, no subtitles, no talking-head"
    )


def _normalize_script(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def narration_from_sidecar(stored: str) -> str:
    lines = []
    for line in (stored or "").splitlines():
        if line.startswith("sha1=") or line.startswith("voice="):
            continue
        lines.append(line)
    return _normalize_script("\n".join(lines))


def narration_sidecar_matches(stored: str, current: str) -> bool:
    """True when cached TTS was synthesized from this exact English master line."""
    body = narration_from_sidecar(stored)
    return body == _normalize_script(current) and bool(_normalize_script(current))


def ensure_english_text(
    text: str,
    *,
    google_api_keys: Optional[List[str]] = None,
    openrouter_keys: Optional[List[str]] = None,
    huggingface_keys: Optional[List[str]] = None,
    element: str = "",
    topic: str = "",
    field: str = "narration",
) -> Tuple[str, Dict[str, Any]]:
    """
    Return English master text. Translates if the source drifted to a target language.
    Never returns empty when a fallback beat can be synthesized.
    """
    raw = (text or "").strip()
    meta: Dict[str, Any] = {"field": field, "repaired": False, "source_lang": SOURCE_LANG}
    optional_empty = field in {"description", "quality_notes"}
    if not raw and optional_empty:
        meta["ok"] = True
        meta["empty"] = True
        return "", meta
    if looks_like_english_master(raw):
        meta["ok"] = True
        return raw, meta

    src = dominant_non_english_lang(raw) or "bn"
    meta["source_lang"] = src
    if raw:
        try:
            from pipeline.localization import translate_text

            out = translate_text(
                raw,
                target_lang=SOURCE_LANG,
                source_lang=src,
                google_api_keys=google_api_keys,
                openrouter_keys=openrouter_keys,
                huggingface_keys=huggingface_keys,
                domain_hint=(
                    "documentary narration for an English video master. "
                    "Keep product/model names, numbers, and place names unchanged"
                    + (f" (especially {topic})" if topic else "")
                    + ". Adapt intent and spoken pacing, not word-for-word."
                ),
            )
            out = (out or "").strip()
            if looks_like_english_master(out):
                meta["repaired"] = True
                meta["via"] = "translate"
                meta["ok"] = True
                logger.info("master_lang repaired %s %s→en via translate", field, src)
                return out, meta
        except Exception as exc:
            meta["translate_error"] = str(exc)[:180]
            logger.warning("master_lang translate failed for %s: %s", field, exc)

    if field == "title":
        fallback = f"{topic} Review" if topic else "Review"
    elif field in _VISUAL_FIELDS:
        fallback = _generic_english_visual(element, topic)
    elif field == "narration":
        fallback = _generic_english_beat(element, topic)
    else:
        fallback = topic or "Review"
    meta["repaired"] = True
    meta["via"] = "generic_english_fallback"
    meta["ok"] = looks_like_english_master(fallback)
    logger.warning("master_lang used generic English fallback for %s", field)
    return fallback, meta


def _lock_keyword_list(items: Any, *, topic: str) -> List[str]:
    raw = items if isinstance(items, list) else ([items] if items else [])
    out: List[str] = []
    for item in raw:
        token = str(item or "").strip()
        if not token:
            continue
        if dominant_non_english_lang(token):
            continue
        if looks_like_english_master(token) or (
            script_char_counts(token)["latin"] >= 2 and not any(script_char_counts(token)[c] for c, _, _ in _SCRIPT_RANGES)
        ):
            out.append(token)
    if not out:
        seed = (topic or "cinematic").split()[0]
        out = [seed, "cinematic", "close-up"][:3]
    return out[:5]


def lock_english_master_plan(
    plan: Dict[str, Any],
    *,
    google_api_keys: Optional[List[str]] = None,
    openrouter_keys: Optional[List[str]] = None,
    huggingface_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Mutate a director plan so narration/title/description/visuals are English.
    Safe to call on resume of an old Bangla director_plan.json.
    """
    data = dict(plan or {})
    topic = str(data.get("topic") or "").strip()
    if topic and not looks_like_english_master(topic) and dominant_non_english_lang(topic):
        topic_en, tmeta = ensure_english_text(
            topic,
            google_api_keys=google_api_keys,
            openrouter_keys=openrouter_keys,
            huggingface_keys=huggingface_keys,
            topic=topic,
            field="title",
        )
        if tmeta.get("repaired") and topic_en:
            data["topic"] = topic_en
            topic = topic_en
    repairs: List[Dict[str, Any]] = []

    title, tmeta = ensure_english_text(
        str(data.get("title") or ""),
        google_api_keys=google_api_keys,
        openrouter_keys=openrouter_keys,
        huggingface_keys=huggingface_keys,
        topic=topic,
        field="title",
    )
    if tmeta.get("repaired"):
        repairs.append(tmeta)
        data["title"] = title
    elif title:
        data["title"] = title
    elif topic:
        data["title"] = f"{topic} Review"

    desc, dmeta = ensure_english_text(
        str(data.get("description") or ""),
        google_api_keys=google_api_keys,
        openrouter_keys=openrouter_keys,
        huggingface_keys=huggingface_keys,
        topic=topic,
        field="description",
    )
    if dmeta.get("repaired"):
        repairs.append(dmeta)
        data["description"] = desc
    elif desc:
        data["description"] = desc

    tags = data.get("tags")
    if isinstance(tags, list):
        orig_tags = [str(t).strip() for t in tags if str(t).strip()]
        locked_tags = _lock_keyword_list(tags, topic=topic)
        if orig_tags and locked_tags != orig_tags:
            repairs.append({"field": "tags", "repaired": True, "via": "drop_non_english_tags"})
            data["tags"] = locked_tags
        elif orig_tags:
            data["tags"] = orig_tags
        elif locked_tags:
            data["tags"] = locked_tags

    scenes_out: List[Dict[str, Any]] = []
    for scene in data.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        row = dict(scene)
        element = str(row.get("element") or "")
        narr, nmeta = ensure_english_text(
            str(row.get("narration") or ""),
            google_api_keys=google_api_keys,
            openrouter_keys=openrouter_keys,
            huggingface_keys=huggingface_keys,
            element=element,
            topic=topic,
            field="narration",
        )
        row["narration"] = narr
        row["lang"] = SOURCE_LANG
        row["lang_bcp47"] = SOURCE_LANG_BCP47
        if nmeta.get("repaired"):
            repairs.append({**nmeta, "element": element})

        for vf in _VISUAL_FIELDS:
            if vf not in row and vf != "visual":
                continue
            if vf not in row:
                continue
            raw_v = str(row.get(vf) or "")
            if not raw_v.strip() and vf == "quality_notes":
                continue
            vis, vmeta = ensure_english_text(
                raw_v,
                google_api_keys=google_api_keys,
                openrouter_keys=openrouter_keys,
                huggingface_keys=huggingface_keys,
                element=element,
                topic=topic,
                field=vf,
            )
            row[vf] = vis
            if vmeta.get("repaired"):
                repairs.append({**vmeta, "element": element})

        orig_kws = [str(k).strip() for k in (row.get("keyword_triggers") or []) if str(k).strip()]
        kws = _lock_keyword_list(row.get("keyword_triggers") or [], topic=topic)
        if orig_kws and kws != orig_kws:
            repairs.append({"field": "keyword_triggers", "repaired": True, "element": element})
        row["keyword_triggers"] = orig_kws and kws or kws
        scenes_out.append(row)
    data["scenes"] = scenes_out
    data["master_lang"] = SOURCE_LANG
    data["master_lang_bcp47"] = SOURCE_LANG_BCP47
    data["sourceLanguage"] = SOURCE_LANG
    data["master_lang_policy"] = "english_pivot_then_localize"
    data["narrator_voice"] = MASTER_VOICE_NAME
    if repairs:
        data["master_lang_repairs"] = repairs
        logger.info("lock_english_master_plan repairs=%s topic=%r", len(repairs), topic)
    analysis = data.get("analysis")
    if isinstance(analysis, dict):
        analysis["master_lang"] = SOURCE_LANG
        analysis["master_lang_bcp47"] = SOURCE_LANG_BCP47
        analysis.setdefault("audience", "English master; localized audio for unlocked languages")
        for akey in ("niche_summary", "why_this_topic", "tone"):
            aval = str(analysis.get(akey) or "")
            if aval and not looks_like_english_master(aval) and dominant_non_english_lang(aval):
                aen, ameta = ensure_english_text(
                    aval,
                    google_api_keys=google_api_keys,
                    openrouter_keys=openrouter_keys,
                    huggingface_keys=huggingface_keys,
                    topic=topic,
                    field="description",
                )
                if ameta.get("repaired"):
                    analysis[akey] = aen
                    repairs.append(ameta)
    leftover = [i for i in assert_plan_english(data) if not i.endswith("_empty") or i.startswith("scene_")]
    hard = [i for i in leftover if "narration" in i or i == "plan_master_lang_flag" or i.startswith("title_")]
    if hard:
        for i, scene in enumerate(data.get("scenes") or []):
            if not isinstance(scene, dict):
                continue
            if master_lang_issues(str(scene.get("narration") or ""), field=f"scene_{i}_narration"):
                scene["narration"] = _generic_english_beat(str(scene.get("element") or ""), topic)
                repairs.append({"field": f"scene_{i}_narration", "repaired": True, "via": "force_generic"})
        if master_lang_issues(str(data.get("title") or ""), field="title"):
            data["title"] = f"{topic} Review" if topic else "Review"
        data["master_lang_repairs"] = repairs
        data["master_lang_force_fallback"] = True
    return data


def assert_plan_english(plan: Dict[str, Any]) -> List[str]:
    """Return issue codes; empty means the plan is safe to TTS as English master."""
    issues: List[str] = []
    if str((plan or {}).get("master_lang") or SOURCE_LANG).lower()[:2] != SOURCE_LANG:
        issues.append("plan_master_lang_flag")
    issues.extend(master_lang_issues(str((plan or {}).get("title") or ""), field="title"))
    desc = str((plan or {}).get("description") or "").strip()
    if desc:
        issues.extend(master_lang_issues(desc, field="description"))
    for i, scene in enumerate((plan or {}).get("scenes") or []):
        if not isinstance(scene, dict):
            continue
        issues.extend(
            master_lang_issues(str(scene.get("narration") or ""), field=f"scene_{i}_narration")
        )
        for vf in ("visual_prompt", "exact_ai_video_prompt", "visual_query"):
            val = str(scene.get(vf) or "").strip()
            if not val:
                continue
            issues.extend(master_lang_issues(val, field=f"scene_{i}_{vf}"))
    return issues


def require_english_master_plan(
    plan: Dict[str, Any],
    *,
    google_api_keys: Optional[List[str]] = None,
    openrouter_keys: Optional[List[str]] = None,
    huggingface_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Lock then hard-fail if spoken master still is not English. Never TTS a drifted script."""
    locked = lock_english_master_plan(
        plan,
        google_api_keys=google_api_keys,
        openrouter_keys=openrouter_keys,
        huggingface_keys=huggingface_keys,
    )
    residual = [
        i
        for i in assert_plan_english(locked)
        if "_narration" in i or i.startswith("title_") or i == "plan_master_lang_flag"
    ]
    if residual:
        raise RuntimeError(f"English master lock failed (refusing TTS): {residual}")
    return locked
