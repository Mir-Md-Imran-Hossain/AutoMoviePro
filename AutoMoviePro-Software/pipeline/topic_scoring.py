"""Weighted topic scoring (ChannelDNA-aware).

Default weights:
  Trend 25% | Channel Fit 25% | Audience Fit 20% | Freshness 15% | Content Potential 15%
Penalties: duplicate, repetition, risk.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from pipeline.channel_dna import ChannelDNA, from_channel_row, validate_topic_against_dna


WEIGHTS = {
    "trend": 0.25,
    "channel_fit": 0.25,
    "audience_fit": 0.20,
    "freshness": 0.15,
    "content_potential": 0.15,
}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


_HISTORY_TOPIC_MARKERS = (
    "ancient", "civilization", "revolution", "roman", "medieval", "empire",
    "dynasty", "archaeology", "temple", "pyramid", "ruins",
)
_TECH_TOPIC_MARKERS = (
    "processor", "gpu", "smartphone", "chip", "benchmark", "earbuds",
    "android", "iphone", "laptop", "ai model", "semiconductor",
)
_FINANCE_TOPIC_MARKERS = (
    "stock", "market", "interest rate", "inflation", "portfolio", "dividend", "crypto",
)


def _topic_has_markers(text: str, markers: tuple[str, ...]) -> bool:
    tl = (text or "").lower()
    return any(m in tl for m in markers)


def _apply_niche_mismatch_penalty(channel_fit: float, topic: str, style_family: str) -> float:
    """Reduce false relevance when topic markers belong to a different niche family."""
    fam = (style_family or "").lower()
    tl = (topic or "").lower()
    hist = _topic_has_markers(tl, _HISTORY_TOPIC_MARKERS)
    tech = _topic_has_markers(tl, _TECH_TOPIC_MARKERS)
    fin = _topic_has_markers(tl, _FINANCE_TOPIC_MARKERS)
    if fam in ("gadget", "technology") and hist and not tech:
        return min(channel_fit, 0.35)
    if fam == "history" and tech and not hist:
        return min(channel_fit, 0.35)
    if fam == "finance" and hist and not fin:
        return min(channel_fit, 0.35)
    if fam == "science" and fin and not _topic_has_markers(tl, ("physics", "chemistry", "biology", "black hole", "quantum")):
        return min(channel_fit, 0.40)
    return channel_fit


def _niche_context_adjustment(channel_fit: float, topic: str, style_family: str) -> float:
    """Borderline topics: same wording should score differently per channel family."""
    tl = (topic or "").lower()
    fam = (style_family or "").lower()
    if fam == "history":
        if tl.startswith("history of") or " history of " in f" {tl} ":
            return max(channel_fit, 0.82)
        if any(w in tl for w in ("revolution", "ancient", "civilization", "empire", "roman")):
            return max(channel_fit, 0.90)
    if fam in ("gadget", "technology"):
        if "artificial intelligence" in tl or "machine learning" in tl:
            return max(channel_fit, 0.78)
        if any(w in tl for w in ("processor", "smartphone", "gpu", "chip", "benchmark")):
            return max(channel_fit, 0.90)
    if fam == "finance":
        if _topic_has_markers(tl, _FINANCE_TOPIC_MARKERS):
            return max(channel_fit, 0.85)
    if fam == "science":
        if any(w in tl for w in ("black hole", "quantum", "physics", "chemistry", "biology")):
            return max(channel_fit, 0.85)
    return channel_fit


def score_topic(
    topic: str,
    dna: ChannelDNA,
    *,
    trend_score: float = 0.0,
    trend_evidence: str = "UNVERIFIED",
    source_count: int = 0,
    freshness: float = 0.5,
    is_duplicate: bool = False,
    is_recent_repeat: bool = False,
    risk: float = 0.0,
    evergreen_verified: bool = False,
) -> Dict[str, Any]:
    topic = (topic or "").strip()
    gate = validate_topic_against_dna(topic, dna)
    if not gate.get("passed"):
        return {
            "topic": topic,
            "passed": False,
            "verdict": "FAIL",
            "total": 0.0,
            "components": {},
            "penalties": {"channel_gate": 1.0},
            "issues": list(gate.get("issues") or []),
            "trend_evidence": trend_evidence,
        }

    # Channel fit: preferred topic overlap
    pref_hit = 0.0
    tl = topic.lower()
    for p in dna.preferred_topics:
        if p and p.lower() in tl:
            pref_hit = 1.0
            break
    channel_fit = 0.85 if pref_hit else 0.65
    if dna.style_family == "history" and any(
        w in tl for w in ("ancient", "library", "tomb", "ruin", "temple", "pyramid", "civilization")
    ):
        channel_fit = 1.0

    channel_fit = _apply_niche_mismatch_penalty(channel_fit, topic, dna.style_family)
    channel_fit = _niche_context_adjustment(channel_fit, topic, dna.style_family)

    audience_fit = 0.7 if dna.audience else 0.6
    if dna.tone == "documentary" and dna.style_family == "history":
        audience_fit = 0.8

    # Trend: UNVERIFIED live trend still scores low unless evergreen verified
    t_raw = _clamp01(trend_score)
    if trend_evidence == "UNVERIFIED" and not evergreen_verified:
        t_raw = min(t_raw, 0.35)
    if evergreen_verified and t_raw < 0.4:
        t_raw = 0.55
    if source_count >= 2:
        t_raw = min(1.0, t_raw + 0.1)

    fresh = _clamp01(freshness)
    # Content potential: specificity heuristic (token count + proper nouns)
    tokens = [w for w in topic.replace("-", " ").split() if len(w) > 2]
    potential = _clamp01(0.4 + 0.08 * min(8, len(tokens)))
    if any(c.isupper() for c in topic if c.isalpha()):
        potential = min(1.0, potential + 0.1)

    components = {
        "trend": t_raw,
        "channel_fit": channel_fit,
        "audience_fit": audience_fit,
        "freshness": fresh,
        "content_potential": potential,
    }
    total = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)

    penalties = {}
    if is_duplicate:
        penalties["duplicate"] = 0.45
    if is_recent_repeat:
        penalties["repetition"] = 0.25
    if risk > 0:
        penalties["risk"] = _clamp01(risk) * 0.3
    total = max(0.0, total - sum(penalties.values()))

    # Acceptance (protocol §22)
    trend_ok = trend_evidence != "UNVERIFIED" or evergreen_verified or t_raw >= 0.5
    passed = (
        total >= 0.45
        and channel_fit >= 0.5
        and fresh >= 0.25
        and not is_duplicate
        and trend_ok
    )
    issues: List[str] = []
    if not trend_ok:
        issues.append("trend_evidence_unverified")
    if is_duplicate:
        issues.append("duplicate")
    if total < 0.45:
        issues.append("score_below_threshold")

    return {
        "topic": topic,
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
        "total": round(total, 4),
        "components": {k: round(v, 4) for k, v in components.items()},
        "penalties": {k: round(v, 4) for k, v in penalties.items()},
        "issues": issues,
        "trend_evidence": trend_evidence,
        "weights": dict(WEIGHTS),
    }


def rank_topics(
    candidates: Sequence[Dict[str, Any]],
    dna: ChannelDNA,
    *,
    blocked: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Rank candidate dicts with keys: topic, trend_score?, freshness?, ..."""
    blocked_l = [str(b).lower() for b in (blocked or []) if b]
    scored: List[Dict[str, Any]] = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        topic = str(c.get("topic") or c.get("name") or "").strip()
        if not topic:
            continue
        if any(b in topic.lower() or topic.lower() in b for b in blocked_l):
            continue
        row = score_topic(
            topic,
            dna,
            trend_score=float(c.get("trend_score") or c.get("score") or 0.0),
            trend_evidence=str(c.get("trend_evidence") or "UNVERIFIED"),
            source_count=int(c.get("source_count") or 0),
            freshness=float(c.get("freshness") if c.get("freshness") is not None else 0.5),
            is_duplicate=bool(c.get("is_duplicate")),
            is_recent_repeat=bool(c.get("is_recent_repeat")),
            risk=float(c.get("risk") or 0.0),
            evergreen_verified=bool(c.get("evergreen_verified")),
        )
        row["raw"] = c
        scored.append(row)
    scored.sort(key=lambda r: float(r.get("total") or 0.0), reverse=True)
    return scored


def select_best_topic(
    candidates: Sequence[Dict[str, Any]],
    channel: Optional[Dict[str, Any]] = None,
    dna: Optional[ChannelDNA] = None,
    *,
    blocked: Optional[Sequence[str]] = None,
    require_pass: bool = True,
) -> Dict[str, Any]:
    dna = dna or from_channel_row(channel or {})
    ranked = rank_topics(candidates, dna, blocked=blocked)
    for row in ranked:
        if not require_pass or row.get("passed"):
            return row
    return {
        "topic": "",
        "passed": False,
        "verdict": "FAIL",
        "total": 0.0,
        "issues": ["no_passing_candidate"],
        "ranked": ranked[:5],
    }
