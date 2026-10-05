"""
Parse Nish.Md (150 global niches) into a structured catalog for the dashboard
and niche director.

Each niche supplies:
  - topic_generation_prompt  → auto topic selection
  - video_prompt             → scene / dialogue / visual continuity rules
  - video_type_blurb         → short description for UI
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Repo root: AutoMovieProSAAS/Nish.Md (sibling of AutoMoviePro-Software)
SOFTWARE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SOFTWARE_ROOT.parent
NISH_MD_CANDIDATES = [
    REPO_ROOT / "Nish.Md",
    SOFTWARE_ROOT / "Nish.Md",
    REPO_ROOT / "nish.md",
]
CACHE_PATH = SOFTWARE_ROOT / "pipeline" / "nish_catalog_cache.json"


def _find_nish_md() -> Path:
    for p in NISH_MD_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Nish.Md not found. Expected at repo root: "
        + str(REPO_ROOT / "Nish.Md")
    )


def _split_sections(text: str) -> List[tuple]:
    """Return [(num, title, body), ...] from ### N. Title headings."""
    pattern = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$", re.M)
    matches = list(pattern.finditer(text))
    out = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((int(m.group(1)), m.group(2).strip(), text[start:end]))
    return out


def _extract_field(body: str, labels: List[str]) -> str:
    for label in labels:
        # **Label:** ... until next **Something:** or --- or ###
        pat = re.compile(
            rf"\*\*{re.escape(label)}:\*\*\s*(.*?)(?=\n\*\*[A-Za-z]|\n---|\n###|\Z)",
            re.S | re.I,
        )
        m = pat.search(body)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def parse_nish_markdown(text: str) -> List[Dict[str, Any]]:
    niches: List[Dict[str, Any]] = []
    for num, title, body in _split_sections(text):
        video_type = _extract_field(body, ["Video Type"])
        topic_prompt = _extract_field(
            body, ["Topic Generation Prompt", "Topic Prompt"]
        )
        video_prompt = _extract_field(
            body, ["Video Prompt", "Video Generation Prompt"]
        )
        niches.append(
            {
                "id": num,
                "name": title,
                "slug": re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-"),
                "video_type": video_type,
                "topic_generation_prompt": topic_prompt,
                "video_prompt": video_prompt,
                "style_family": infer_style_family(title, video_type, video_prompt),
            }
        )
    niches.sort(key=lambda n: int(n["id"]))
    return niches


def infer_style_family(name: str, video_type: str = "", video_prompt: str = "") -> str:
    """Map a Nish niche onto a director style pack family."""
    blob = f"{name} {video_type} {video_prompt}".lower()
    checks = [
        ("islamic", ("islam", "quran", "muslim", "deen", "mosque", "hadith")),
        ("science", ("science", "physics", "chem", "space", "lab", "biology", "tech explain")),
        ("mystery", ("myster", "unsolved", "vanish", "paranormal", "haunt", "secret")),
        (
            "history",
            (
                "histor",
                "ancient",
                "war",
                "battle",
                "civilization",
                "kingdom",
                "empire",
                "royal",
                "assassina",
                "shipwreck",
                "chernobyl",
                "documentary",
            ),
        ),
        ("gadget", ("gadget", "phone", "review", "unbox", "tech review", "earbuds", "laptop")),
        ("motivation", ("motivat", "self", "habit", "mindset", "success", "productivity")),
        ("health", ("health", "fitness", "nutrition", "medical", "sleep", "mental")),
        ("news", ("news", "current", "politics", "geopolit")),
        ("finance", ("financ", "money", "invest", "crypto", "stock", "econom")),
        ("nature", ("nature", "wildlife", "animal", "ocean", "climate", "planet")),
        ("true_crime", ("crime", "murder", "serial", "forensic", "case file")),
    ]
    for family, keys in checks:
        if any(k in blob for k in keys):
            return family
    return "history"  # Nish skews documentary/history by default


@lru_cache(maxsize=1)
def load_niche_catalog(*, force_reload: bool = False) -> List[Dict[str, Any]]:
    if force_reload:
        load_niche_catalog.cache_clear()
    try:
        md_path = _find_nish_md()
        text = md_path.read_text(encoding="utf-8", errors="replace")
        niches = parse_nish_markdown(text)
        if len(niches) >= 50:
            try:
                CACHE_PATH.write_text(
                    json.dumps(
                        {"source": str(md_path), "count": len(niches), "niches": niches},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.debug("niche cache write failed: %s", exc)
            logger.info("Loaded %s niches from %s", len(niches), md_path.name)
            return niches
    except Exception as exc:
        logger.warning("Nish.Md parse encountered error: %s. Checking cache fallback...", exc)

    if CACHE_PATH.exists():
        try:
            cached_data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            cached_niches = cached_data.get("niches") or []
            if len(cached_niches) >= 50:
                logger.info("Loaded %s niches from fallback cache %s", len(cached_niches), CACHE_PATH.name)
                return cached_niches
        except Exception as cache_exc:
            logger.warning("Cache fallback also failed: %s", cache_exc)

    raise FileNotFoundError("Nish.Md not found and niche cache is missing or corrupt.")


def get_niche_by_id(niche_id: int) -> Optional[Dict[str, Any]]:
    for n in load_niche_catalog():
        if int(n["id"]) == int(niche_id):
            return n
    return None


def get_niche_by_name(name: str) -> Optional[Dict[str, Any]]:
    needle = (name or "").strip().lower()
    if not needle:
        return None
    for n in load_niche_catalog():
        if n["name"].lower() == needle or n["slug"] == needle:
            return n
    # fuzzy contains
    for n in load_niche_catalog():
        if needle in n["name"].lower() or n["name"].lower() in needle:
            return n
    return None


def resolve_niche(channel_or_name: Any) -> Dict[str, Any]:
    """
    Resolve channel niche fields or free-text name to a full Nish entry.
    Falls back to a synthetic pack if unknown.
    """
    if isinstance(channel_or_name, dict):
        nid = channel_or_name.get("niche_id")
        if nid not in (None, "", 0, "0"):
            hit = get_niche_by_id(int(nid))
            if hit:
                return hit
        name = str(channel_or_name.get("niche") or "").strip()
    else:
        name = str(channel_or_name or "").strip()
    hit = get_niche_by_name(name)
    if hit:
        return hit
    return {
        "id": 0,
        "name": name or "Custom",
        "slug": "custom",
        "video_type": "Custom niche documentary storytelling.",
        "topic_generation_prompt": (
            f"Find a viral, SEO-friendly YouTube topic for the niche '{name}'. "
            "Must be concrete (named entity/event/mechanism), high curiosity gap, "
            "visual proof potential, and a clear retention spine "
            "(hook → open loop → payoff → re-hook). Avoid vague listicles."
        ),
        "video_prompt": (
            "Generate a 7–9 second dialogue clip for topic {topic}. "
            "Retention-first spoken beat (hook/question/reveal/payoff — not flat description). "
            "Cinematic B-roll matched to narration; no talking-head lip-sync; "
            "consistent lighting/character/environment across clips."
        ),
        "style_family": infer_style_family(name),
    }


def list_niches_for_api(*, lang: str = "en") -> List[Dict[str, Any]]:
    """Compact list for dropdown UI — localized name/blurb by UI language."""
    from pipeline.niche_production_profile import load_profile, localize_niche_fields

    code = (lang or "en").strip().lower()[:2] or "en"
    out: List[Dict[str, Any]] = []
    for n in load_niche_catalog():
        loc = localize_niche_fields(n, lang=code)
        prof = load_profile(int(n["id"]))
        out.append(
            {
                "id": n["id"],
                "name": loc["name"],
                "name_en": n["name"],
                "slug": n["slug"],
                "style_family": n.get("style_family"),
                "blurb": loc["blurb"],
                "blurb_en": (n.get("video_type") or "")[:180],
                "has_production_profile": bool(prof and prof.get("status") in ("COMPLETE", "VERIFIED")),
                "lang": code,
            }
        )
    return out
