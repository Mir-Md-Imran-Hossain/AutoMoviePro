"""Cross-scene dialogue uniqueness + TTS narration sanitization."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple


_HASH_RE = re.compile(r"(?:^|\s)#[\w\u0980-\u09FF]+")
_VOICE_META_RE = re.compile(r"^voice\s*=\s*\S+\s*$", re.I | re.M)
_SEO_LINE_RE = re.compile(
    r"(?i)(?:subscribe|like and subscribe|follow for more|#\w+)"
)


def strip_narration_meta(text: str) -> str:
    """Remove voice= sidecars and collapse whitespace."""
    t = _VOICE_META_RE.sub("", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def sanitize_spoken_narration(text: str) -> str:
    """
    Spoken TTS must not read hashtags / SEO spam.
    Keeps human documentary lines only.
    """
    t = strip_narration_meta(text)
    if not t:
        return ""
    # Drop trailing hashtag clusters
    t = _HASH_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # Remove pure hashtag-only sentences
    parts = re.split(r"(?<=[.!?])\s+", t)
    kept = []
    for p in parts:
        p2 = p.strip()
        if not p2:
            continue
        if p2.startswith("#") or (p2.count("#") >= 2 and len(p2.split()) <= 8):
            continue
        kept.append(p2)
    return " ".join(kept).strip()


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9\u0980-\u09FF]{3,}", (text or "").lower())


def _trigrams(tokens: Sequence[str]) -> set:
    if len(tokens) < 3:
        return set()
    return {tuple(tokens[i : i + 3]) for i in range(len(tokens) - 2)}


def pair_overlap_ratio(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    # Prefer trigram Jaccard when both long enough
    ga, gb = _trigrams(ta), _trigrams(tb)
    if ga and gb:
        inter = len(ga & gb)
        union = len(ga | gb) or 1
        return inter / union
    sa, sb = set(ta), set(tb)
    inter = len(sa & sb)
    union = len(sa | sb) or 1
    return inter / union


def detect_dialogue_uniqueness(scenes: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Fail when two scenes reuse the same spoken claims (repeated dialogue).
    """
    result: Dict[str, Any] = {
        "check": "dialogue_uniqueness",
        "passed": True,
        "issues": [],
        "critical_issues": [],
        "pairs": [],
        "max_overlap": 0.0,
    }
    rows: List[Tuple[int, str]] = []
    for i, sc in enumerate(scenes or []):
        if not isinstance(sc, dict):
            continue
        narr = sanitize_spoken_narration(str(sc.get("narration") or ""))
        if len(_tokens(narr)) < 5:
            continue
        rows.append((i, narr))

    max_ov = 0.0
    bad: List[Dict[str, Any]] = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            ia, a = rows[i]
            ib, b = rows[j]
            ov = pair_overlap_ratio(a, b)
            max_ov = max(max_ov, ov)
            # Near-duplicate spoken beats
            if ov >= 0.42 or (ov >= 0.28 and len(set(_tokens(a)) & set(_tokens(b))) >= 8):
                bad.append(
                    {
                        "a": ia,
                        "b": ib,
                        "overlap": round(ov, 3),
                        "sample_a": a[:90],
                        "sample_b": b[:90],
                    }
                )

    result["max_overlap"] = round(max_ov, 3)
    result["pairs"] = bad[:12]
    if bad:
        result["passed"] = False
        result["issues"] = [
            f"repeated_dialogue:scenes_{p['a']}_{p['b']}:overlap={p['overlap']}" for p in bad[:6]
        ]
        result["critical_issues"] = ["repeated_dialogue"]
    return result


def enforce_unique_scene_narrations(
    scenes: List[Dict[str, Any]], *, topic: str = ""
) -> List[Dict[str, Any]]:
    """Sanitize + lightly de-dupe by blanking duplicate later beats (caller should rewrite)."""
    _ = topic  # reserved for topic-masked rewrite passes (marathon tests)
    out: List[Dict[str, Any]] = []
    seen: List[str] = []
    for sc in scenes or []:
        if not isinstance(sc, dict):
            continue
        row = dict(sc)
        narr = sanitize_spoken_narration(str(row.get("narration") or ""))
        for prev in seen:
            if pair_overlap_ratio(narr, prev) >= 0.42:
                # Mark for director rewrite — keep text but flag
                row["dialogue_duplicate"] = True
                break
        row["narration"] = narr
        if narr:
            seen.append(narr)
        out.append(row)
    return out


# Marathon/regression tests import this historical name.
force_unique_scene_narrations = enforce_unique_scene_narrations


HISTORY_ELEMENTS = [
    "intro",
    "context",
    "discovery",
    "technique",
    "culture",
    "engineering",
    "artifact",
    "mystery",
    "legacy",
    "compare",
    "lesson",
    "cta",
    "outro",
]

GADGET_ELEMENTS = {
    "design",
    "display",
    "camera",
    "processor",
    "battery",
    "sound",
    "fit",
    "case",
    "software",
    "price",
    "pros_cons",
}


def niche_uses_gadget_template(niche: str, style_family: str = "") -> bool:
    fam = (style_family or "").lower()
    if fam == "gadget":
        return True
    n = (niche or "").lower()
    return any(x in n for x in ("gadget", "tech review", "phone review", "গ্যাজেট"))


def detect_wrong_template(scenes: Sequence[Dict[str, Any]], *, niche: str, style_family: str = "") -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "check": "niche_template",
        "passed": True,
        "issues": [],
        "critical_issues": [],
    }
    if niche_uses_gadget_template(niche, style_family):
        return result
    elems = [str(s.get("element") or "").lower() for s in scenes if isinstance(s, dict)]
    gadget_hits = [e for e in elems if e in GADGET_ELEMENTS]
    if len(gadget_hits) >= 3:
        result["passed"] = False
        result["issues"] = [f"gadget_elements_on_nongadget_niche:{','.join(gadget_hits[:8])}"]
        result["critical_issues"] = ["wrong_niche_template"]
    return result
