"""Deterministic topic quality / placeholder / SEO guards (PART-5A + live marathon).

Does not replace BUILD-04G duplicate or niche scoring authorities.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


_PLACEHOLDER_PATTERNS = (
    r"^\s*\{?\s*topic\s*\}?\s*$",
    r"^\s*topic\s+angle\s+\d+\s*$",
    r"topic\s+angle\s+\d+",
    r"^\s*placeholder\s*$",
    r"^\s*test\s+topic\s*$",
    r"^\s*untitled\s*$",
    r"^\s*n/?a\s*$",
    r"^\s*tbd\s*$",
    r"^\s*coming\s+soon\s*$",
    r"^\s*lorem\s+ipsum",
    r"for\s+c\d+\s+marathon",
)

_CLICKBAIT_WEAK = (
    "you won't believe",
    "shocking",
    "gone wrong",
    "this one trick",
)

_SEO_INTENT = (
    "how",
    "why",
    "what",
    "which",
    "when",
    "best",
    "guide",
    "explained",
    "vs",
    "versus",
    "secrets",
    "hidden",
    "map",
    "preserve",
    "discover",
)


_NICHE_SYNONYMS = {
    "space": (
        "space",
        "nasa",
        "lunar",
        "moon",
        "mars",
        "artemis",
        "jwst",
        "orbit",
        "satellite",
        "planet",
        "solar",
        "cosmos",
        "astro",
        "europa",
        "neutron",
        "spectrometer",
        "corona",
        "probe",
    ),
    "science": (
        "science",
        "research",
        "evidence",
        "experiment",
        "lab",
        "physics",
        "chemistry",
        "biology",
        "data",
        "instrument",
    ),
}


def _niche_aligned(topic_low: str, niche: str) -> bool:
    niche_l = str(niche or "").lower().strip()
    if not niche_l:
        return True
    niche_tokens = [t for t in re.findall(r"[a-z0-9]{4,}", niche_l) if t not in ("with", "from", "that", "this")]
    if any(t in topic_low for t in niche_tokens):
        return True
    for key, syns in _NICHE_SYNONYMS.items():
        if key in niche_l or any(key == t for t in niche_tokens):
            if any(s in topic_low for s in syns):
                return True
    return False


def score_topic_seo(topic_text: str, *, niche: str = "") -> Dict[str, Any]:
    """Heuristic SEO-friendliness for niche video titles (not a Google ranking claim)."""
    text = " ".join(str(topic_text or "").strip().split())
    low = text.lower()
    score = 0.35
    notes: List[str] = []
    words = low.split()
    if 6 <= len(words) <= 18:
        score += 0.2
        notes.append("length_ok")
    else:
        notes.append("length_suboptimal")
    if any(w in low for w in _SEO_INTENT):
        score += 0.15
        notes.append("intent_keyword")
    if niche and _niche_aligned(low, niche):
        score += 0.15
        notes.append("niche_anchor")
    if re.search(r"\d", text):
        score += 0.05
        notes.append("has_specific_number_or_year")
    if any(c in low for c in _CLICKBAIT_WEAK):
        score -= 0.25
        notes.append("clickbait_penalty")
    if len(words) < 5:
        score -= 0.2
    score = max(0.0, min(1.0, score))
    return {
        "seo_score": round(score, 3),
        "seo_friendly": score >= 0.55,
        "notes": notes,
        "method": "HEURISTIC",
        "claims_google_rank": False,
    }


def validate_topic_quality(topic_text: str, *, niche: str = "") -> Dict[str, Any]:
    """Return ok=False when topic is empty, placeholder, or too generic for script."""
    text = " ".join(str(topic_text or "").strip().split())
    issues: List[str] = []
    if not text:
        return {
            "ok": False,
            "error_code": "topic_empty",
            "issues": ["topic_empty"],
            "specificity_score": 0.0,
            "seo": score_topic_seo("", niche=niche),
        }
    low = text.lower()
    for pat in _PLACEHOLDER_PATTERNS:
        if re.search(pat, low, flags=re.I):
            issues.append(f"placeholder_pattern:{pat}")
    if "{" in text and "}" in text:
        issues.append("template_braces")
    tokens = re.findall(r"[A-Za-z\u0980-\u09FF0-9]{3,}", text)
    specificity = min(1.0, len(tokens) / 8.0)
    if len(tokens) < 4:
        issues.append("too_few_content_tokens")
        specificity = min(specificity, 0.25)
    niche_hit = _niche_aligned(low, niche)
    if str(niche or "").strip() and not niche_hit and len(tokens) < 8:
        issues.append("weak_niche_anchor_and_short")
        specificity = min(specificity, 0.35)
    if len(tokens) <= 2 and not any(ch.isdigit() for ch in text):
        issues.append("overly_generic_short_topic")
    seo = score_topic_seo(text, niche=niche)
    if not seo.get("seo_friendly"):
        issues.append("seo_weak")
    ok = specificity >= 0.4 and not any(
        i.startswith("placeholder") or i in ("template_braces", "too_few_content_tokens", "overly_generic_short_topic")
        for i in issues
    )
    # SEO weak alone → WARN (ok stays True if otherwise solid) for discovery flexibility
    if "seo_weak" in issues and ok and specificity >= 0.7 and niche_hit:
        issues = [i for i in issues if i != "seo_weak"]
    return {
        "ok": ok,
        "error_code": "" if ok else "topic_placeholder_or_generic",
        "issues": issues,
        "specificity_score": round(float(specificity), 3),
        "token_count": len(tokens),
        "niche_aligned": bool(niche_hit),
        "seo": seo,
        "authority": "pipeline.intelligence.topic_quality",
    }
