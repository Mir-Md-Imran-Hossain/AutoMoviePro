"""Per-niche production profiles — make pipeline niche-aware beyond family defaults.

Profiles are written by niche_setup_marathon (one niche at a time) under
pipeline/niche_profiles/{id:03d}.json and merged into channel enrichment.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

PROFILES_DIR = Path(__file__).resolve().parent / "niche_profiles"
I18N_PATH = Path(__file__).resolve().parent / "niche_i18n_store.json"

UI_LANGS = ("en", "bn", "hi", "ur", "ta", "ml")


def profile_path(niche_id: int) -> Path:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return PROFILES_DIR / f"{int(niche_id):03d}.json"


def load_profile(niche_id: int) -> Optional[Dict[str, Any]]:
    p = profile_path(niche_id)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_profile(profile: Dict[str, Any]) -> Path:
    nid = int(profile["niche_id"])
    p = profile_path(nid)
    p.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_i18n_store() -> Dict[str, Any]:
    if not I18N_PATH.is_file():
        return {"version": 1, "niches": {}}
    try:
        return json.loads(I18N_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "niches": {}}


def save_i18n_store(store: Dict[str, Any]) -> None:
    I18N_PATH.parent.mkdir(parents=True, exist_ok=True)
    I18N_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_i18n(niche_id: int, translations: Dict[str, Dict[str, str]]) -> None:
    store = load_i18n_store()
    niches = store.setdefault("niches", {})
    key = str(int(niche_id))
    row = dict(niches.get(key) or {})
    for lang, payload in translations.items():
        if lang not in UI_LANGS:
            continue
        row[lang] = {
            "name": str((payload or {}).get("name") or "").strip(),
            "blurb": str((payload or {}).get("blurb") or "").strip(),
        }
    niches[key] = row
    store["niches"] = niches
    save_i18n_store(store)


def localize_niche_fields(
    niche: Dict[str, Any],
    *,
    lang: str = "en",
) -> Dict[str, str]:
    """Return localized name + blurb for dropdown (falls back to English catalog)."""
    code = (lang or "en").strip().lower()[:2] or "en"
    store = load_i18n_store()
    row = (store.get("niches") or {}).get(str(int(niche.get("id") or 0))) or {}
    hit = row.get(code) or {}
    name = str(hit.get("name") or niche.get("name") or "").strip()
    blurb = str(hit.get("blurb") or (niche.get("video_type") or "")[:220]).strip()
    # Profile i18n override (marathon writes both)
    prof = load_profile(int(niche.get("id") or 0))
    if prof:
        pi = ((prof.get("i18n") or {}).get(code) or {})
        if pi.get("name"):
            name = str(pi["name"]).strip()
        if pi.get("blurb"):
            blurb = str(pi["blurb"]).strip()
    return {"name": name, "blurb": blurb[:280]}


def _short_blurb(video_type: str, *, max_len: int = 160) -> str:
    text = re.sub(r"\s+", " ", (video_type or "").strip())
    if len(text) <= max_len:
        return text
    cut = text[: max_len - 1].rsplit(" ", 1)[0]
    return (cut or text[: max_len - 1]) + "…"


def build_profile_from_nish(pack: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic production profile researched from Nish.Md pack fields."""
    nid = int(pack.get("id") or 0)
    name = str(pack.get("name") or f"Niche {nid}")
    family = str(pack.get("style_family") or "history")
    video_type = str(pack.get("video_type") or "")
    topic_prompt = str(pack.get("topic_generation_prompt") or "")
    video_prompt = str(pack.get("video_prompt") or "")
    blob = f"{name} {video_type} {topic_prompt} {video_prompt}".lower()
    blob_raw = f"{name} {video_type} {topic_prompt}"

    # Research: niche-specific topic seeds (SEO-friendly angles)
    seeds = _topic_seeds_for(name, family, blob, blob_raw=blob_raw)
    forbidden = _forbidden_for(family, blob)
    subjects = _subjects_for(name, family, blob)
    lighting = _lighting_for(family, blob)
    face = _face_policy_for(family, blob)
    tone = _dialogue_tone_for(family, blob)
    ambience = _ambience_for(family, blob)

    i18n = {
        "en": {
            "name": name,
            "blurb": _short_blurb(video_type or f"Documentary shorts about {name}."),
        }
    }
    # Seed other langs with English until marathon/translator fills them
    for lang in UI_LANGS:
        if lang == "en":
            continue
        i18n[lang] = {"name": name, "blurb": i18n["en"]["blurb"]}

    return {
        "niche_id": nid,
        "name": name,
        "slug": pack.get("slug") or "",
        "style_family": family,
        "status": "DRAFT",
        "topic_seeds": seeds,
        "seo_angles": seeds[:4],
        "forbidden_visuals": forbidden,
        "preferred_subjects": subjects,
        "lighting_default": lighting,
        "face_policy": face,
        "dialogue_tone": tone,
        "audio_ambience": ambience,
        "research_hints": [
            f"Prefer primary evidence and concrete entities for {name}",
            "Avoid generic niche-label topics; require specific place/person/event/mechanism",
            "7–9 second spoken beats with story continuity across scenes",
        ],
        "topic_prompt_overlay": (
            f"NICHE LOCK ({name}): only propose topics that fit this niche's video type. "
            f"Video type: {video_type[:240]} "
            f"Follow niche topic strategy: {topic_prompt[:400]}"
        ),
        "video_prompt_overlay": (
            f"NICHE VISUAL LOCK ({name} / {family}): {video_prompt[:700]} "
            f"Forbidden: {', '.join(forbidden[:8])}. "
            f"Preferred subjects: {', '.join(subjects[:6])}. "
            f"Lighting: {lighting}. Face policy: {face}."
        ),
        "i18n": i18n,
        "source": "Nish.Md + deterministic research",
    }


def _topic_seeds_for(
    name: str, family: str, blob: str, *, blob_raw: str = ""
) -> List[str]:
    base = [
        f"How {name} shaped the modern world — one overlooked mechanism",
        f"Why experts still debate the key mystery inside {name}",
        f"What new evidence changed our understanding of {name}",
        f"The {name} detail most explainers get wrong",
        f"A 60-second breakdown of the most viral {name} angle this year",
    ]
    if "ancient" in blob or "civilization" in blob:
        return [
            "How Egyptian Nile flood calendars organized temple labor and harvest taxes",
            "Why Indus Valley drainage grids still outclass early Mesopotamian streets",
            "What Roman concrete chemistry explains about marine harbor longevity",
            "How Greek city-state rivalries funded naval innovation before empire",
            "Why Mesopotamian clay tablets preserved contracts better than papyrus",
        ]
    if "lost kingdom" in blob or "atlantis" in blob or "khmer" in blob:
        return [
            "How LiDAR revealed Angkor's hidden hydraulic city grid under jungle canopy",
            "Why El Dorado myths tracked real Muisca goldwork — not a single lost city",
            "What underwater scans suggest about Mediterranean 'vanished port' candidates",
        ]
    # Entity-driven seeds from Nish video-type nouns (Egypt, Titanic, DNA, etc.)
    entities = _extract_entities(blob_raw or name)
    if entities:
        seeds = []
        for ent in entities[:5]:
            seeds.append(f"What new evidence reframes the story of {ent} inside {name}")
            seeds.append(f"How {ent} still shapes public curiosity about {name}")
        # Dedupe preserve order
        seen = set()
        out = []
        for s in seeds + base:
            k = s.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(s)
        return out[:6]
    if family == "science" or "space" in blob:
        return [
            f"How one experiment overturned a textbook claim in {name}",
            f"Why the cause→effect chain in {name} matters for daily life",
            f"What instruments actually measure in {name} — and what they cannot",
        ]
    if family == "true_crime" or "crime" in blob:
        return [
            f"How forensic timeline evidence reframed a famous {name} case",
            f"Why one overlooked witness detail still divides investigators",
        ]
    return base


def _extract_entities(blob: str) -> List[str]:
    """Pull concrete proper nouns / quoted phrases from Nish video_type text."""
    text = re.sub(r"[—–]", "-", blob or "")
    found: List[str] = []
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b", text):
        w = m.group(1).strip()
        if w.lower() in {
            "the", "how", "what", "why", "each", "this", "that", "video", "type",
            "documentary", "deep", "real", "true", "famous", "great", "epic",
        }:
            continue
        if len(w) < 3:
            continue
        if w not in found:
            found.append(w)
    return found[:8]


def _forbidden_for(family: str, blob: str) -> List[str]:
    common = ["talking-head lip-sync avatar", "burned-in captions", "watermark", "modern meme text"]
    if family in ("history", "mystery") or "ancient" in blob:
        return common + ["modern smartphones", "cars", "LED screens", "sneakers", "contemporary skyline"]
    if family == "islamic":
        return common + ["idols", "prophet depiction", "graphic violence", "lip-sync faces"]
    if family == "gadget":
        return common + ["wrong model phone", "generic unbranded slab", "stock office handshake"]
    if family == "true_crime":
        return common + ["gore close-ups", "victim exploitation", "glorified violence"]
    if family == "nature":
        return common + ["CGI cartoon animals", "studio green-screen obvious seams"]
    return common + ["off-niche stock office B-roll"]


def _subjects_for(name: str, family: str, blob: str) -> List[str]:
    if "ancient" in blob or "civilization" in blob:
        return [
            "Nile riverbank temple pylons",
            "Indus brick drainage channel",
            "Roman concrete harbor pier",
            "Greek trireme hull detail",
            "Mesopotamian cuneiform tablet",
            "desert excavation trench at dawn",
        ]
    if family == "science":
        return ["lab instrument close-up", "diagrammatic mechanism metaphor", "field measurement site"]
    if family == "nature":
        return ["biome wide establishing shot", "species macro detail", "weather system overhead"]
    if family == "gadget":
        return ["exact product hero", "component close-up", "hands with device only"]
    return [f"{name} documentary subject", "period-accurate environment", "evidence object close-up"]


def _lighting_for(family: str, blob: str) -> str:
    if "ancient" in blob or family == "history":
        return "warm desert sun / torchlit interiors, high-contrast documentary grade"
    if family == "mystery":
        return "dappled fog light, cool teal shadows, slow push-ins"
    if family == "science":
        return "teal/cyan lab grade, high contrast, shallow DOF"
    if family == "islamic":
        return "warm golden hour, soft architectural light"
    if family == "true_crime":
        return "desaturated overcast, practical interiors"
    return "natural directional key, documentary clarity"


def _face_policy_for(family: str, blob: str) -> str:
    if family == "islamic":
        return "faceless metaphors only; no idols; no lip-sync"
    if family == "gadget":
        return "product-only hero; hands OK; no talking-head"
    if family == "true_crime":
        return "silhouettes / archival only; never glorify violence"
    if "ancient" in blob or family == "history":
        return "period extras OK if consistent; prefer environment/object hero when possible"
    return "no talking-head lip-sync avatar; cinematic B-roll preferred"


def _dialogue_tone_for(family: str, blob: str) -> str:
    if "ancient" in blob:
        return "curious documentary narrator; wonder + concrete fact; no campy adventure slang"
    if family == "mystery":
        return "slow, ominous, evidence-first"
    if family == "science":
        return "clear explainer; one mechanism per beat"
    if family == "true_crime":
        return "restrained investigative; respectful"
    return "human documentary narration; specific nouns; 7–9s beats"


def _ambience_for(family: str, blob: str) -> str:
    if "ancient" in blob:
        return "distant wind over sand/stone, soft temple-room reverb, sparse strings"
    if family == "mystery":
        return "low drone, subtle reverb, sparse percussion"
    if family == "science":
        return "clean room tone, soft electronic texture"
    return "subtle documentary bed; do not overpower voice"
