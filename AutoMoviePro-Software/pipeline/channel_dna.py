"""ChannelDNA v0 — channel identity for topic/template gating.

v0 loads from existing `channels` row fields (no DB migration required).
Later tasks persist richer DNA (audience scores, cooldowns, performance).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


HISTORY_MARKERS = (
    "ancient",
    "civilization",
    "civilisation",
    "history",
    "archaeology",
    "archeology",
    "museum",
    "ruins",
    "প্রাচীন",
    "ইতিহাস",
)
GADGET_MARKERS = (
    "gadget",
    "tech review",
    "phone review",
    "গ্যাজেট",
    "smartphone",
    "earbuds",
)
TECH_MARKERS = (
    "tech",
    "technology",
    "consumer technology",
    "consumer tech",
    "gadgets",
    "electronics",
    "software",
    "ai",
    "startup",
)
FINANCE_MARKERS = ("finance", "stock", "investing", "crypto", "bitcoin", "market")
EDUCATION_MARKERS = ("education", "learning", "tutorial", "course", "শিক্ষা")
HEALTH_MARKERS = ("health", "medical", "fitness", "nutrition", "স্বাস্থ্য")
ENTERTAINMENT_MARKERS = ("entertainment", "movie", "music", "gaming", "games")
SCIENCE_MARKERS = ("science", "physics", "chemistry", "বিজ্ঞান")
MYSTERY_MARKERS = ("mystery", "unexplained", "রহস্য")


@dataclass
class ChannelDNA:
    channel_id: int = 0
    niche: str = ""
    sub_niche: str = ""
    audience: str = "general"
    country: str = ""
    language: str = "en"
    tone: str = "documentary"
    video_style: str = ""
    hook_style: str = ""
    preferred_topics: List[str] = field(default_factory=list)
    forbidden_topics: List[str] = field(default_factory=list)
    preferred_duration: Dict[str, int] = field(default_factory=dict)
    historical_topics: List[str] = field(default_factory=list)
    historical_performance: Dict[str, Any] = field(default_factory=dict)
    topic_cooldown: List[str] = field(default_factory=list)
    style_family: str = ""
    version: str = "v0"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def allows_gadget_template(self) -> bool:
        return (self.style_family or "").lower() == "gadget"

    def topic_forbidden(self, topic: str) -> bool:
        t = (topic or "").lower().strip()
        if not t:
            return False
        for bad in self.forbidden_topics:
            b = (bad or "").lower().strip()
            if b and (b in t or t in b):
                return True
        return False


def _canonical_niche(niche: str) -> str:
    n = (niche or "").strip().lower()
    aliases = {
        "tech": "technology",
        "technology": "technology",
        "consumer technology": "technology",
        "consumer tech": "technology",
        "gadgets": "gadget",
        "gadget": "gadget",
        "finance": "finance",
        "history": "history",
        "science": "science",
        "education": "education",
        "health": "health",
        "entertainment": "entertainment",
    }
    return aliases.get(n, n)


def infer_style_family(niche: str, video_special: str = "", generation_special: str = "") -> str:
    canonical = _canonical_niche(niche)
    blob = f"{niche} {video_special} {generation_special}".lower()
    if canonical == "gadget" or any(m in blob for m in GADGET_MARKERS):
        return "gadget"
    if canonical == "technology" or any(m in blob for m in TECH_MARKERS):
        return "gadget"
    if canonical == "finance" or any(m in blob for m in FINANCE_MARKERS):
        return "finance"
    if canonical == "history" or any(m in blob for m in HISTORY_MARKERS):
        return "history"
    if canonical == "science" or any(m in blob for m in SCIENCE_MARKERS):
        return "science"
    if canonical == "education" or any(m in blob for m in EDUCATION_MARKERS):
        return "education"
    if canonical == "health" or any(m in blob for m in HEALTH_MARKERS):
        return "health"
    if canonical == "entertainment" or any(m in blob for m in ENTERTAINMENT_MARKERS):
        return "entertainment"
    if any(m in blob for m in MYSTERY_MARKERS):
        return "mystery"
    if niche.strip():
        return "general"
    return "general"


def _default_forbidden(style_family: str) -> List[str]:
    fam = (style_family or "").lower()
    if fam == "history":
        return [
            "iphone",
            "samsung galaxy",
            "pixel",
            "oneplus",
            "earbuds",
            "gadget",
            "smartphone",
            "unboxing",
            "tech review",
        ]
    if fam == "gadget":
        return []
    if fam == "finance":
        return []
    if fam == "general":
        return ["talking head lip sync"]
    return ["talking head lip sync"]


def _default_preferred(style_family: str, niche: str) -> List[str]:
    fam = (style_family or "").lower()
    if fam == "history":
        return [
            "ancient sites",
            "lost libraries",
            "archaeological discoveries",
            "engineering of antiquity",
        ]
    if fam == "gadget":
        return ["flagship phones", "earbuds", "wearables"]
    return [niche] if niche else []


def from_channel_row(channel: Optional[Dict[str, Any]]) -> ChannelDNA:
    ch = channel if isinstance(channel, dict) else {}
    niche = str(ch.get("niche") or "").strip()
    video_special = str(ch.get("video_special") or "")
    gen_special = str(ch.get("generation_special") or "")
    style = infer_style_family(niche, video_special, gen_special)

    # Optional JSON blob if present (future migration)
    raw_dna = ch.get("channel_dna_json") or ch.get("dna_json")
    if isinstance(raw_dna, str) and raw_dna.strip().startswith("{"):
        try:
            data = json.loads(raw_dna)
            if isinstance(data, dict) and data.get("niche"):
                return ChannelDNA(
                    channel_id=int(ch.get("id") or data.get("channel_id") or 0),
                    niche=str(data.get("niche") or niche),
                    sub_niche=str(data.get("sub_niche") or ""),
                    audience=str(data.get("audience") or "general"),
                    country=str(data.get("country") or ""),
                    language=str(data.get("language") or "en"),
                    tone=str(data.get("tone") or "documentary"),
                    video_style=str(data.get("video_style") or video_special),
                    hook_style=str(data.get("hook_style") or ""),
                    preferred_topics=list(data.get("preferred_topics") or _default_preferred(style, niche)),
                    forbidden_topics=list(data.get("forbidden_topics") or _default_forbidden(style)),
                    preferred_duration=dict(data.get("preferred_duration") or {}),
                    historical_topics=list(data.get("historical_topics") or []),
                    historical_performance=dict(data.get("historical_performance") or {}),
                    topic_cooldown=list(data.get("topic_cooldown") or []),
                    style_family=str(data.get("style_family") or style),
                    version=str(data.get("version") or "v0"),
                )
        except Exception:
            pass

    tone = "review" if style == "gadget" else "documentary"
    return ChannelDNA(
        channel_id=int(ch.get("id") or 0),
        niche=niche,
        sub_niche="",
        audience="general",
        country="",
        language="en",
        tone=tone,
        video_style=video_special,
        hook_style="",
        preferred_topics=_default_preferred(style, niche),
        forbidden_topics=_default_forbidden(style),
        preferred_duration={},
        historical_topics=[],
        historical_performance={},
        topic_cooldown=[],
        style_family=style,
        version="v0",
    )


def validate_topic_against_dna(topic: str, dna: ChannelDNA) -> Dict[str, Any]:
    """Topic acceptance helper for T003; v0 = forbidden + style sanity."""
    result: Dict[str, Any] = {
        "passed": True,
        "verdict": "PASS",
        "issues": [],
        "channel_fit": True,
        "freshness": "UNVERIFIED",
        "trend_evidence": "UNVERIFIED",
    }
    topic = (topic or "").strip()
    if not topic:
        result["passed"] = False
        result["verdict"] = "FAIL"
        result["issues"].append("empty_topic")
        return result
    if dna.topic_forbidden(topic):
        result["passed"] = False
        result["verdict"] = "FAIL"
        result["channel_fit"] = False
        result["issues"].append("forbidden_topic")
    if not dna.allows_gadget_template():
        # Gadget product tokens on non-gadget channels
        gadget_hits = [
            x
            for x in ("iphone", "galaxy", "pixel", "oneplus", "earbuds", "unboxing")
            if x in topic.lower()
        ]
        if gadget_hits:
            result["passed"] = False
            result["verdict"] = "FAIL"
            result["channel_fit"] = False
            result["issues"].append("gadget_topic_on_nongadget:" + ",".join(gadget_hits))
    return result


def save_dna_sidecar(work_dir: Any, dna: ChannelDNA) -> Optional[Path]:
    try:
        path = Path(str(work_dir)) / "CHANNEL_DNA.json"
        path.write_text(json.dumps(dna.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    except Exception:
        return None
