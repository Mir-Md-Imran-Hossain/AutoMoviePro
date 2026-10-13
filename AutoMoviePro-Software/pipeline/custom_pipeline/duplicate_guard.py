"""Duplicate topic/script detection for custom pipeline (cross-format, entity collision & NFC aware)."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config import ROOT
from pipeline.output_layout import CURATED_OUTPUT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.45
ARCHIVE_ROOT = ROOT / "Output" / "CustomPipeline_Complete_JSON"

GENERIC_WORDS = {
    # Stopwords & common verbs / conversational tokens
    "ভিডিও", "টপিক", "নিয়ে", "জন্য", "হবে", "করছে", "পারে", "আসল", "সত্যি", "কি", "কী", "কেন", "কিভাবে",
    "যে", "এই", "আর", "ও", "না", "একবার", "সেট", "করো", "হলে", "মতো", "এখন", "থেকে", "করে", "নয়", "হিসাব",
    "কিছু", "সব", "কোন", "কোথায়", "কখন", "বলল", "বলছে", "যায়", "যা", "থাকে", "থাকবে", "হয়ে", "হলে",
    "আসসালামু", "আলাইকুম", "আল্লাহ", "হাফেজ", "বন্ধুরা", "দর্শক", "চ্যানেল", "সাবস্ক্রাইব", "লাইক", "শেয়ার",
    "আছে", "ছিল", "হচ্ছে", "হয়েছে", "দেয়", "নেয়", "কাজ", "মানুষ", "নতুন", "সবচেয়ে", "বেশি", "কম", "প্রথম",
    "শেষ", "আজ", "কাল", "অনেক", "এক", "দুই", "তিন", "সেই", "কিন্তু", "বা", "কিংবা", "অথবা", "যদি", "তবে", "তাই",
    "বলতে", "গেলে", "জানেন", "দেখুন", "শুনুন", "মনে", "রাখবেন", "কারণ", "ফলে", "পর", "আগে", "পরে",
    # Generic domain & conversational filler words (should not alone trigger anchor collision)
    "ai", "tech", "facts", "fact", "smart", "video", "topic", "2024", "2025", "2026", "science", "world",
    "robot", "robots", "রোবট", "প্রযুক্তি", "কৃত্রিম", "বুদ্ধিমত্তা", "ডিভাইস", "মোবাইল", "ফোন",
    "গভীর", "সমুদ্র", "মহাসাগর", "পানি", "জল", "জীবন্ত", "প্রাণী", "বিজ্ঞান", "ইতিহাস", "মহাকাশ",
    "পৃথিবী", "গবেষণা", "আবিষ্কার", "রহস্য", "রহস্যময়", "ঘটনা", "তদন্ত", "বিজ্ঞানীরা", "গবেষকরা",
    "মানুষের", "জীবন", "আলো", "অন্ধকার", "বাতাস", "শহর", "দেশ",
    "আপনার", "আপনা", "আমাদের", "আমরা", "তাদের", "তারা", "তিনি", "সে", "এটি", "এসব",
    "গোপন", "সত্য", "শুধু", "অবিশ্বাস্য", "চমক", "জানুন", "জানল", "দেখুন", "করুন",
    "ব্যবস্থা", "সিস্টেম", "উপায়", "উপায়", "কীভাবে", "কেন", "কী", "কখন",
    "মস্তিষ্ক", "ব্রেইন", "দেহ", "শরীর", "মানুষ", "অঙ্গ", "রক্ত", "কোষ",
    "রাত", "দিন", "সময়", "সময়", "বছর", "মাস", "ঘণ্টা", "মিনিট", "সেকেন্ড",
    "নতুন", "পুরোনো", "পুরানো", "ভালো", "খারাপ", "ছোট", "বড়", "সহজ", "কঠিন",
    "হয়", "হয়", "হলো", "হলো", "নয়", "নয়", "থাকে", "পারে", "হবে", "হয়েছিল", "হয়েছে", "হতে", "করবে", "আসছে",
    "অসম্ভব", "লুকানো", "কাঁপিয়ে", "কাঁপিয়ে", "দিল", "ভুল", "নাকি", "দেখল", "খেলা", "ঘড়ি", "ঘড়ি",
    "শিশু", "পূর্ণবয়স্ক", "বিস্ময়কর", "বিস্ময়কর", "চমকপ্রদ", "অজানা", "উন্মোচন", "বদলে", "যাবে",
    # English stopwords
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with", "is", "are", "was", "were",
    "your", "you", "this", "that", "these", "those", "how", "what", "why", "when", "where", "which", "will",
}

# High-priority anchor entity pairs that define an identical technical subject/event
ANCHOR_ENTITY_PAIRS = [
    {"bmw", "figure"},
    {"figure", "02"},
    {"figure", "ai"},
    {"tesla", "optimus"},
    {"chatgpt", "custom"},
    {"chatgpt", "instructions"},
    {"dark", "oxygen"},
    {"black", "hole"},
    {"event", "horizon"},
    {"boston", "dynamics"},
    {"nvidia", "gr00t"},
]


def _norm_text(text: str) -> str:
    """Normalize text with Unicode NFC, lowercase, and unified whitespace."""
    if not text:
        return ""
    t = unicodedata.normalize("NFC", str(text)).lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(
        r"[^\w\s\u0980-\u09FF\u0900-\u097F\u0B80-\u0BFF\u0D00-\u0D7F]+",
        " ",
        t,
        flags=re.UNICODE,
    )
    return t.strip()


def extract_entities(text: str) -> Set[str]:
    """Extract key proper nouns, brand names, model numbers, and stemmed Bengali terms."""
    if not text:
        return set()
    t = unicodedata.normalize("NFC", str(text)).lower()
    # English alphanumeric tokens (e.g. 'bmw', '02', 'chatgpt', 'optimus')
    en_tokens = set(re.findall(r"[a-z0-9]{2,}", t))
    # Bengali tokens (3+ chars)
    bn_tokens = set(re.findall(r"[\u0980-\u09FF]{3,}", t))

    raw_tokens = (en_tokens | bn_tokens) - GENERIC_WORDS
    cleaned: Set[str] = set()
    for tk in raw_tokens:
        # Strip common Bengali grammatical suffixes
        for sfx in ("টিতেও", "টিতে", "গুলো", "দের", "ের", "তে", "ায়", "ে", "র", "য়", "কে"):
            if tk.endswith(sfx) and len(tk) > len(sfx) + 2:
                tk = tk[:-len(sfx)]
                break
        if tk not in GENERIC_WORDS and len(tk) >= 2:
            cleaned.add(tk)
    return cleaned


def detect_entity_collision(
    new_entities: Set[str],
    existing_entities: Set[str],
) -> Tuple[bool, float, Set[str]]:
    """Determine if two topics share critical anchor entity pairs or heavy entity overlap."""
    common = new_entities & existing_entities
    if not common:
        return False, 0.0, set()

    # Rule 1: High-priority anchor pair collision (e.g. BMW + Figure, or Figure + 02)
    for pair in ANCHOR_ENTITY_PAIRS:
        if pair.issubset(common):
            return True, 1.0, common

    # Rule 2: Alphanumeric or distinctive named entity match
    alphanumeric_common = {tk for tk in common if re.match(r"[a-z0-9]", tk)}
    distinctive_common = {tk for tk in common if len(tk) >= 4 or re.match(r"[a-z0-9]", tk)}
    if len(alphanumeric_common) >= 2 or len(distinctive_common) >= 4:
        return True, 0.95, common

    # Rule 3: Jaccard overlap on distinctive entities (requires at least 2 distinctive matches and >= 50% overlap)
    min_size = min(len(new_entities), len(existing_entities))
    score = len(distinctive_common) / min_size if min_size > 0 else 0.0
    if score >= 0.50 and (len(alphanumeric_common) >= 1 or len(distinctive_common) >= 3):
        return True, round(score, 4), common

    return False, round(score, 4), common


def similarity(a: str, b: str) -> float:
    """Compute character-sequence similarity on NFC-normalized strings."""
    na, nb = _norm_text(a), _norm_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def token_overlap(a: str, b: str) -> float:
    """Compute token overlap coefficient between two phrases, handling Bengali inflections and NFC."""
    na = unicodedata.normalize("NFC", a or "").lower()
    nb = unicodedata.normalize("NFC", b or "").lower()
    tokens_a = set(re.findall(r"[\w\u0980-\u09FF]{3,}", na))
    tokens_b = set(re.findall(r"[\w\u0980-\u09FF]{3,}", nb))
    if not tokens_a or not tokens_b:
        return 0.0

    def _stem_tokens(tks: Set[str]) -> Set[str]:
        res = set()
        for tk in tks:
            for sfx in ("টিতেও", "টিতে", "গুলো", "দের", "ের", "তে", "ায়", "ে", "র", "য়", "কে"):
                if tk.endswith(sfx) and len(tk) > len(sfx) + 2:
                    tk = tk[:-len(sfx)]
                    break
            res.add(tk)
        return res

    norm_a = _stem_tokens(tokens_a) - GENERIC_WORDS
    norm_b = _stem_tokens(tokens_b) - GENERIC_WORDS
    if not norm_a or not norm_b:
        return 0.0
    inter = norm_a & norm_b
    return len(inter) / min(len(norm_a), len(norm_b))


def _voiceover_blob(payload: Dict[str, Any]) -> str:
    scenes = payload.get("script_scenes") or payload.get("voice_scenes") or []
    parts = []
    for sc in scenes:
        if isinstance(sc, dict):
            parts.append(str(sc.get("voiceover_script") or ""))
    return unicodedata.normalize("NFC", " ".join(parts))


def _topic_blob(payload: Dict[str, Any]) -> str:
    seo = payload.get("seo_metadata") if isinstance(payload.get("seo_metadata"), dict) else {}
    titles = seo.get("suggested_titles") or []
    title_join = " ".join(str(t) for t in titles if t)
    raw = " ".join([str(seo.get("selected_topic") or ""), title_join]).strip()
    return unicodedata.normalize("NFC", raw)


def extract_record(payload: Dict[str, Any], *, source: str = "") -> Dict[str, Any]:
    topic_blob = _topic_blob(payload)
    script_blob = _voiceover_blob(payload)
    sel_topic = unicodedata.normalize(
        "NFC",
        str(((payload.get("seo_metadata") or {}).get("selected_topic")) or "").strip(),
    )
    topic_entities = extract_entities(sel_topic or topic_blob)
    return {
        "topic": topic_blob,
        "script": script_blob,
        "selected_topic": sel_topic,
        "entities": topic_entities,
        "source": source,
    }


def load_history(
    *,
    video_type: Optional[str] = "short",
    output_root: Optional[Path] = None,
    archive_root: Optional[Path] = None,
    include_all_formats: bool = True,
) -> List[Dict[str, Any]]:
    """Load prior topic/script records from Output packages + Complete_JSON archive.
    
    When `include_all_formats=True` (default), history is loaded across both Short and Long
    directories so that topics are NEVER repeated across formats.
    """
    out_dir = Path(output_root or CURATED_OUTPUT_ROOT)
    arc_dir = Path(archive_root or ARCHIVE_ROOT)

    roots: List[Path] = []
    if include_all_formats:
        for base in (out_dir, arc_dir):
            if base.is_dir():
                roots.extend([base / "Short", base / "Long", base])
    else:
        kind = "Short" if str(video_type).lower() in ("short", "shorts", "reel") else "Long"
        roots = [out_dir / kind, arc_dir / kind]

    records: List[Dict[str, Any]] = []
    seen_sources: set[str] = set()

    for root in roots:
        if not root.is_dir():
            continue
        # topic_script.json anywhere under root
        for path in root.rglob("topic_script.json"):
            key = str(path.resolve())
            if key in seen_sources:
                continue
            seen_sources.add(key)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    records.append(extract_record(data, source=key))
            except Exception:
                continue
        # Script_NNN_*.json archive naming
        for path in root.rglob("Script_*.json"):
            key = str(path.resolve())
            if key in seen_sources:
                continue
            seen_sources.add(key)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and (
                    data.get("script_scenes") or data.get("seo_metadata")
                ):
                    records.append(extract_record(data, source=key))
            except Exception:
                continue

    return records


def find_duplicate(
    payload: Dict[str, Any],
    history: List[Dict[str, Any]],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> Optional[Dict[str, Any]]:
    """Return match info if topic, entities, or script similarity ≥ threshold or anchor collision."""
    topic = _topic_blob(payload)
    script = _voiceover_blob(payload)
    sel_topic = unicodedata.normalize(
        "NFC",
        str(((payload.get("seo_metadata") or {}).get("selected_topic")) or "").strip(),
    )
    new_topic_entities = extract_entities(sel_topic or topic)
    best: Optional[Dict[str, Any]] = None

    for rec in history:
        rec_sel = str(rec.get("selected_topic") or "").strip()
        rec_topic = rec.get("topic") or ""
        rec_script = rec.get("script") or ""
        rec_entities = rec.get("entities")
        if rec_entities is None:
            rec_entities = extract_entities(rec_topic)

        # 1. Anchor entity collision check on topic entities
        is_entity_collision, entity_score, common_entities = detect_entity_collision(
            new_topic_entities, rec_entities
        )

        # 2. Sequence similarity
        topic_sim = similarity(topic, rec_topic)
        script_sim = similarity(script, rec_script)
        sel_sim = similarity(sel_topic, rec_sel) if (sel_topic and rec_sel) else 0.0

        # 3. Token overlap across selected topic and full topic blob
        tok_sel = token_overlap(sel_topic, rec_sel) if (sel_topic and rec_sel) else 0.0
        tok_blob = token_overlap(topic, rec_topic) if (topic and rec_topic) else 0.0
        tok_sim = max(tok_sel, tok_blob)

        # 4. Multi-vector scoring
        if is_entity_collision:
            final = 1.0
        else:
            eff_entity = entity_score if len(common_entities) >= 2 else 0.0
            score = max(topic_sim, script_sim, sel_sim, tok_sim, eff_entity)
            blend = 0.55 * max(topic_sim, sel_sim, tok_sim) + 0.45 * max(script_sim, eff_entity)
            final = max(score, blend)

        if final >= threshold or is_entity_collision:
            hit = {
                "matched": True,
                "score": round(final, 4),
                "entity_collision": is_entity_collision,
                "common_entities": sorted(common_entities),
                "topic_similarity": round(max(topic_sim, sel_sim), 4),
                "script_similarity": round(script_sim, 4),
                "token_overlap": round(tok_sim, 4),
                "entity_overlap": round(entity_score, 4),
                "existing_topic": rec_sel or rec_topic[:120],
                "source": rec.get("source"),
            }
            if best is None or hit["score"] > best["score"]:
                best = hit

    return best


def blocked_topic_list(history: List[Dict[str, Any]], *, limit: int = 40) -> List[str]:
    """Generate a clean list of blocked topics from history."""
    out: List[str] = []
    seen = set()
    for rec in history:
        t = (rec.get("selected_topic") or "").strip()
        if not t:
            t = (rec.get("topic") or "").strip().split("  ")[0][:120]
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
        if len(out) >= limit:
            break
    return out


def build_dedupe_retry_suffix(blocked: List[str], *, match: Optional[Dict[str, Any]] = None) -> str:
    """Build high-urgency retry guidance when a duplicate is caught."""
    lines = [
        "",
        "🚨 ডুপ্লিকেট নিষেধাজ্ঞা (STRICT ZERO-DUPLICATE ENFORCEMENT):",
        "আমাদের সিস্টেমে নিচের বিষয়/অ্যাঙ্গেলগুলো ইতিমধ্যে তৈরি করা হয়েছে। একই বিষয়, প্রতিষ্ঠান, রোবট মডেল বা টেকনোলজি কোনোভাবেই পুনরায় বেছে নেওয়া যাবে না।",
        "সম্পূর্ণ ভিন্ন, অপ্রচলিত, নতুন ও চমকপ্রদ অন্য কোনো সাবজেক্ট বা প্রযুক্তি বেছে নাও।",
        "",
        "আগে থেকে থাকা টপিক তালিকা:",
    ]
    for i, t in enumerate(blocked[:25], 1):
        lines.append(f"{i}. {t}")

    if match:
        common = match.get("common_entities") or []
        lines.append("")
        lines.append(
            f"❌ সর্বশেষ রিজেক্ট কারণ: মিলের স্কোর={match.get('score')} "
            f"(পূর্বে থাকা বিষয়: '{match.get('existing_topic')}')"
        )
        if common:
            lines.append(f"⛔ নিষিদ্ধ কি-ওয়ার্ড/মডেল/প্রতিষ্ঠান: {', '.join(common)}")
        lines.append("ওপরের নির্দিষ্ট বিষয় বা প্রতিষ্ঠানের নাম বাদ দিয়ে সম্পূর্ণ নতুন বিষয়ের ওপর স্ক্রিপ্ট দাও।")

    lines.append("")
    lines.append("এখন নতুন JSON আউটপুট দাও — পুরনো টপিকের পুনরাবৃত্তি সম্পূর্ণ নিষিদ্ধ।")
    return "\n".join(lines)
