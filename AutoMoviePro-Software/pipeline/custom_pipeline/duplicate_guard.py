"""Duplicate topic/script detection for custom pipeline (≥60% match → regenerate)."""

from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import ROOT
from pipeline.output_layout import CURATED_OUTPUT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.60
ARCHIVE_ROOT = ROOT / "Output" / "CustomPipeline_Complete_JSON"


def _norm_text(text: str) -> str:
    t = (text or "").lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s\u0980-\u09FF\u0900-\u097F\u0B80-\u0BFF\u0D00-\u0D7F]+", " ", t, flags=re.UNICODE)
    return t.strip()


def similarity(a: str, b: str) -> float:
    na, nb = _norm_text(a), _norm_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _voiceover_blob(payload: Dict[str, Any]) -> str:
    scenes = payload.get("script_scenes") or payload.get("voice_scenes") or []
    parts = []
    for sc in scenes:
        if isinstance(sc, dict):
            parts.append(str(sc.get("voiceover_script") or ""))
    return " ".join(parts)


def _topic_blob(payload: Dict[str, Any]) -> str:
    seo = payload.get("seo_metadata") if isinstance(payload.get("seo_metadata"), dict) else {}
    titles = seo.get("suggested_titles") or []
    title_join = " ".join(str(t) for t in titles if t)
    return " ".join(
        [
            str(seo.get("selected_topic") or ""),
            title_join,
        ]
    ).strip()


def extract_record(payload: Dict[str, Any], *, source: str = "") -> Dict[str, str]:
    return {
        "topic": _topic_blob(payload),
        "script": _voiceover_blob(payload),
        "selected_topic": str(((payload.get("seo_metadata") or {}).get("selected_topic")) or ""),
        "source": source,
    }


def load_history(
    *,
    video_type: str = "short",
    output_root: Optional[Path] = None,
    archive_root: Optional[Path] = None,
) -> List[Dict[str, str]]:
    """Load prior topic/script records from Output packages + Complete_JSON archive."""
    kind = "Short" if str(video_type).lower() in ("short", "shorts", "reel") else "Long"
    roots = [
        Path(output_root or CURATED_OUTPUT_ROOT) / kind,
        Path(archive_root or ARCHIVE_ROOT) / kind,
    ]
    records: List[Dict[str, str]] = []
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


def token_overlap(a: str, b: str) -> float:
    """Compute token overlap coefficient between two phrases, handling Bengali inflections."""
    tokens_a = set(re.findall(r"[\w\u0980-\u09FF]{3,}", (a or "").lower()))
    tokens_b = set(re.findall(r"[\w\u0980-\u09FF]{3,}", (b or "").lower()))
    if not tokens_a or not tokens_b:
        return 0.0
    norm_a = set()
    for tk in tokens_a:
        for sfx in ("ের", "তে", "ায়", "ে", "র", "য়"):
            if tk.endswith(sfx) and len(tk) > len(sfx) + 2:
                tk = tk[:-len(sfx)]
                break
        norm_a.add(tk)
    norm_b = set()
    for tk in tokens_b:
        for sfx in ("ের", "তে", "ায়", "ে", "র", "য়"):
            if tk.endswith(sfx) and len(tk) > len(sfx) + 2:
                tk = tk[:-len(sfx)]
                break
        norm_b.add(tk)
    inter = norm_a & norm_b
    return len(inter) / min(len(norm_a), len(norm_b))


def find_duplicate(
    payload: Dict[str, Any],
    history: List[Dict[str, str]],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> Optional[Dict[str, Any]]:
    """Return match info if topic OR script similarity ≥ threshold."""
    topic = _topic_blob(payload)
    script = _voiceover_blob(payload)
    sel_topic = str(((payload.get("seo_metadata") or {}).get("selected_topic")) or "").strip()
    best: Optional[Dict[str, Any]] = None

    for rec in history:
        rec_sel = str(rec.get("selected_topic") or "").strip()
        rec_topic = rec.get("topic") or ""
        rec_script = rec.get("script") or ""

        topic_sim = similarity(topic, rec_topic)
        script_sim = similarity(script, rec_script)

        # Direct selected_topic comparison & token overlap
        sel_sim = similarity(sel_topic, rec_sel) if (sel_topic and rec_sel) else 0.0
        tok_sim = token_overlap(sel_topic, rec_sel) if (sel_topic and rec_sel) else 0.0

        # "বেশিরভাগ অংশ" — either topic blob, direct selected_topic, token overlap, or script hitting threshold counts as duplicate
        score = max(topic_sim, script_sim, sel_sim, tok_sim)
        blend = 0.55 * max(topic_sim, sel_sim) + 0.45 * script_sim
        final = max(score, blend)
        if final >= threshold:
            hit = {
                "matched": True,
                "score": round(final, 4),
                "topic_similarity": round(max(topic_sim, sel_sim), 4),
                "script_similarity": round(script_sim, 4),
                "token_overlap": round(tok_sim, 4),
                "existing_topic": rec_sel or rec_topic[:120],
                "source": rec.get("source"),
            }
            if best is None or hit["score"] > best["score"]:
                best = hit
    return best


def blocked_topic_list(history: List[Dict[str, str]], *, limit: int = 40) -> List[str]:
    out: List[str] = []
    seen = set()
    for rec in history:
        t = (rec.get("selected_topic") or "").strip()
        if not t:
            # first line-ish of topic blob
            t = (rec.get("topic") or "").strip().split("  ")[0][:120]
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
        if len(out) >= limit:
            break
    return out


def build_dedupe_retry_suffix(blocked: List[str], *, match: Optional[Dict[str, Any]] = None) -> str:
    lines = [
        "",
        "⚠️ ডুপ্লিকেট নিষেধাজ্ঞা (অবশ্যই মানতে হবে):",
        "নিচের টপিক/অ্যাঙ্গেলগুলো আমাদের সিস্টেমে ইতিমধ্যে আছে। এগুলোর সাথে ≥৬০% মিল থাকা টপিক বা স্ক্রিপ্ট দিও না।",
        "এর বাইরে সম্পূর্ণ নতুন, ট্রেন্ডিং এবং আলাদা অ্যাঙ্গেলের SEO-ফ্রেন্ডলি টপিক + নতুন স্ক্রিপ্ট দাও।",
        "",
        "আগে থেকে থাকা টপিক তালিকা:",
    ]
    for i, t in enumerate(blocked, 1):
        lines.append(f"{i}. {t}")
    if match:
        lines.append("")
        lines.append(
            f"(সর্বশেষ রিজেক্ট কারণ: score={match.get('score')} "
            f"topic_sim={match.get('topic_similarity')} "
            f"script_sim={match.get('script_similarity')} "
            f"matched≈{match.get('existing_topic')})"
        )
    lines.append("")
    lines.append("এখন নতুন JSON আউটপুট দাও — পুরনো টপিকের পুনরাবৃত্তি নয়।")
    return "\n".join(lines)
