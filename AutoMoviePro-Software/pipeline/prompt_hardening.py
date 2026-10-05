"""
Deterministic first-shot prompt engineering — no Gemini required.

Injects learned training rules + hard AV constraints BEFORE Agnes/image API
calls so we do not burn 3× regenerations fixing the same faults.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

from pipeline.av_sync_critic import load_training_rules
from pipeline.dialogue_sync import AGNES_AUDIO_CHUNK_MAX, AGNES_MIN_SECONDS
from pipeline.prompt_engineering import (
    agnes_vs_image_hard_rules,
    truncate_keep_lock,
)

logger = logging.getLogger(__name__)

# Always-on hard constraints. Display beats allow device UI; never burned captions.
HARD_CONSTRAINTS = agnes_vs_image_hard_rules(for_image=False)

# Stopwords for dialogue<->image anchor extraction (EN + common filler)
_STOP = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "from", "by", "as", "is", "are", "was", "were", "be", "been", "this", "that", "these",
    "those", "it", "its", "they", "them", "their", "we", "our", "you", "your", "he", "she",
    "his", "her", "not", "no", "yes", "into", "over", "under", "about", "than", "then",
    "so", "if", "when", "while", "just", "also", "very", "more", "most", "can", "will",
    "would", "could", "should", "may", "might", "must", "here", "there", "what", "which",
    "who", "how", "why", "all", "each", "every", "some", "any", "few", "such", "only",
    "own", "same", "other", "again", "further", "once", "after", "before", "above",
    "below", "between", "through", "during", "without", "within", "along", "across",
}


# Words that are spoken but should not be forced as on-screen objects
_NOT_VISUAL = {
    "today", "tonight", "thanks", "thank", "please", "really", "still", "even",
    "much", "many", "thing", "things", "people", "someone", "something",
    "everything", "anything", "nothing", "going", "using", "making", "looking",
    "watching", "video", "videos", "clip", "scene", "beat", "review", "reviews",
    "comment", "comments", "subscribe", "channel", "welcome", "stay", "next",
    "first", "last", "also", "just", "very", "more", "most", "tell", "ask",
    "question", "questions", "honest", "practical", "clear", "full", "deep",
    # verbs / copulas — forcing these onto pixels causes false visual_anchors_missing
    "show", "shows", "shown", "showing", "look", "looks", "looked",
    "say", "says", "said", "talk", "talks", "talked", "come", "comes", "came",
    "take", "takes", "took", "taken", "give", "gives", "gave", "given",
    "see", "sees", "seen", "know", "knows", "knew", "think", "thinks", "thought",
    "make", "makes", "made", "want", "wants", "need", "needs", "used", "call",
    "calls", "called", "keep", "keeps", "kept", "feel", "feels", "felt",
    "become", "becomes", "became", "leave", "leaves", "left", "bring", "brings",
    "here", "there", "then", "than", "into", "onto", "from", "with",
    # shot language / abstract nouns — not on-screen objects
    "macro", "micro", "hero", "cinematic", "closeup", "broll",
    "storyteller", "storytellers", "storytelling", "story",
    "technology", "secret", "secrets", "context", "feature", "features",
    "identity", "module", "detail", "details", "visual", "visuals",
}


def is_non_visual_anchor(phrase: str) -> bool:
    """True when a critic 'missed keyword' is shot language, not a pixel object."""
    raw = (phrase or "").strip().lower()
    if not raw:
        return True
    if raw in _NOT_VISUAL:
        return True
    # Years / wall-clock stamps are not on-screen SKUs for documentary niches
    if re.fullmatch(r"20\d{2}", raw) or re.fullmatch(r"sku[_\s-]?20\d{2}", raw):
        return True
    if "sku_20" in raw or raw.endswith("_2026") or raw.endswith("_2025"):
        return True
    tokens = re.findall(r"[a-z0-9]+", raw)
    content = [t for t in tokens if t not in _STOP and len(t) >= 3]
    if not content:
        return True
    # Drop year tokens from content before judging
    content = [t for t in content if not re.fullmatch(r"20\d{2}", t)]
    if not content:
        return True
    return all(t in _NOT_VISUAL for t in content)


def extract_model_tokens(text: str) -> List[str]:
    """Keep SKU fragments like 9a, XM5, S24, WF-1000XM5 that letter-only extractors drop."""
    found = re.findall(r"\b(?=[A-Za-z0-9\-]*\d)[A-Za-z0-9][A-Za-z0-9\-]{1,24}\b", text or "")
    out: List[str] = []
    seen = set()
    for tok in found:
        key = tok.lower()
        if key in seen or len(tok) < 2:
            continue
        seen.add(key)
        out.append(tok)
    return out


def extract_dialogue_anchors(text: str, *, limit: int = 8) -> List[str]:
    """Content nouns/words that MUST appear in the visual prompt for this beat."""
    words = re.findall(r"[A-Za-z\u0980-\u09FF\u0900-\u097F]{4,}", text or "")
    out: List[str] = []
    seen = set()
    for w in words:
        low = w.lower()
        if low in _STOP or low in _NOT_VISUAL or low in seen:
            continue
        seen.add(low)
        out.append(w)
        if len(out) >= limit:
            break
    for tok in extract_model_tokens(text):
        if tok.lower() not in seen:
            out.append(tok)
            seen.add(tok.lower())
        if len(out) >= limit + 4:
            break
    return out


def _token_pieces(token: str) -> List[str]:
    pieces = []
    for p in re.split(r"[\s/_]+", (token or "").lower()):
        p = p.strip(".,!?;:\"'()-")
        if not p:
            continue
        if any(ch.isdigit() for ch in p):
            if len(p) >= 2:
                pieces.append(p)
        elif len(p) >= 3 and p not in _STOP and p not in _NOT_VISUAL:
            pieces.append(p)
    return pieces


def _token_in_blob(token: str, blob: str) -> bool:
    blob = blob or ""
    raw = (token or "").strip().lower()
    if not raw:
        return True
    if raw in blob:
        return True
    pieces = _token_pieces(token)
    if not pieces:
        return True
    for p in pieces:
        if p in blob or f"{p}s" in blob or (p.endswith("s") and p[:-1] in blob):
            continue
        return False
    return True


def required_visual_tokens(
    *,
    keywords: Optional[List[str]] = None,
    narration: str = "",
    product_name: str = "",
) -> List[str]:
    required: List[str] = []
    seen = set()

    def _add(token: str) -> None:
        t = str(token or "").strip()
        if not t:
            return
        key = t.lower()
        if key in seen or key in _STOP or key in _NOT_VISUAL:
            return
        seen.add(key)
        required.append(t)

    if product_name:
        _add(product_name)
        for tok in extract_model_tokens(product_name):
            _add(tok)
    for k in keywords or []:
        _add(str(k))
    for a in extract_dialogue_anchors(narration, limit=6):
        _add(a)
    return required


def _clip_rules(rules: List[str], *, limit: int = 8) -> List[str]:
    out: List[str] = []
    seen = set()
    for r in rules:
        t = re.sub(r"\s+", " ", (r or "").strip())
        if len(t) < 12:
            continue
        key = t.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(t[:220])
        if len(out) >= limit:
            break
    return out


def harden_video_prompt(
    base_prompt: str,
    *,
    narration: str = "",
    keywords: Optional[List[str]] = None,
    product_name: str = "",
    element: str = "",
    niche: str = "",
    duration_sec: float = 0.0,
    prior_issues: Optional[List[str]] = None,
) -> str:
    """
    Build a single strong English prompt for the FIRST provider call.
    """
    base = (base_prompt or "").strip()
    kw = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    trained = _clip_rules(load_training_rules(), limit=6)
    issues = [str(i).strip() for i in (prior_issues or []) if str(i).strip()]

    # Issue-specific boosters from prior hard fails on this scene
    issue_boost: List[str] = []
    joined = " ".join(issues).lower()
    if "dialogue_cutoff" in joined or "cutoff" in joined:
        issue_boost.append(
            "CRITICAL FIX: previous take truncated speech — speak the FULL last sentence then silence."
        )
    if "missing_tail_hold" in joined or "tail" in joined:
        issue_boost.append(
            "CRITICAL FIX: after the last word leave ~1s silence while camera KEEPS MOVING — no hard freeze."
        )
    if "talking_head" in joined:
        issue_boost.append("CRITICAL FIX: no human face mouthing words; use metaphor visuals only.")
    if "end_frame_freeze" in joined or "freeze" in joined or "localize_freeze" in joined:
        issue_boost.append(
            "CRITICAL FIX: continuous motion through the beat — never freeze-pad or black-pad to match audio."
        )
    if "black_tail" in joined:
        issue_boost.append("CRITICAL FIX: do not fade to black; end on the visible scene.")
    if "speech_pace" in joined or "last_word" in joined:
        issue_boost.append(
            "CRITICAL FIX: speak every final noun clearly at steady documentary pace (~2.3 wps)."
        )

    dur = float(duration_sec or 0.0)
    if dur <= 0 and narration:
        # rough: ~2.5 words/sec English
        words = max(1, len(narration.split()))
        dur = min(AGNES_AUDIO_CHUNK_MAX, max(AGNES_MIN_SECONDS, words / 2.5 + 0.8))
    dur = min(AGNES_AUDIO_CHUNK_MAX, max(AGNES_MIN_SECONDS, dur or AGNES_MIN_SECONDS))

    # C05-GP: do not soft-truncate the semantic core (entities/relations/location).
    # Provider formatting may append rules; truncate_keep_lock keeps the head.
    _has_semantic_core = bool(
        re.search(
            r"(?i)(relationship|beside|holding|semantic_lock|visual_mode|entity|location)",
            base or "",
        )
    )
    base_core = (
        base
        if (base and _has_semantic_core)
        else (base[:500] if base else f"Cinematic documentary shot for {product_name or niche or 'topic'}")
    )
    parts = [
        base_core,
        f"Beat/element: {element or 'feature'}.",
        f"Target duration about {dur:.1f} seconds.",
    ]
    if issue_boost:
        parts.append(" ".join(issue_boost))
    if narration:
        anchors = extract_dialogue_anchors(narration, limit=8)
        parts.append(f'Narration to visualize (must match mood/action): "{narration[:280]}"')
        if anchors:
            parts.append(
                "DIALOGUE<->IMAGE LOCK — show these spoken anchors on screen: "
                + ", ".join(anchors)
                + "."
            )
    if kw:
        parts.append("Must visualize these triggers: " + ", ".join(kw[:12]) + ".")
    if product_name:
        parts.append(f"Topic/subject: {product_name}.")
    if niche:
        parts.append(f"Niche: {niche}.")

    parts.append("HARD RULES: " + " ".join(agnes_vs_image_hard_rules(for_image=False, element=element)))
    if trained:
        parts.append("LEARNED RULES: " + " | ".join(trained))

    out = " ".join(parts)
    out = re.sub(r"\s+", " ", out).strip()
    if len(out) > 1400:
        out = truncate_keep_lock(
            out, limit=1400, product_name=product_name or "", keywords=kw
        )
    logger.info("Hardened prompt (%s chars) for first-shot generation", len(out))
    return out


def preflight_keyword_prompt(
    prompt: str,
    *,
    keywords: Optional[List[str]] = None,
    narration: str = "",
    product_name: str = "",
) -> Dict[str, Any]:
    """
    API-less keyword lock: every trigger, product/SKU, and narration anchor
    must appear in the Agnes/image prompt before we spend a generation call.
    """
    required = required_visual_tokens(
        keywords=keywords, narration=narration, product_name=product_name
    )
    blob = (prompt or "").lower()
    missing = [token for token in required if not _token_in_blob(token, blob)]
    fixed = (prompt or "").strip()
    if missing:
        inject = " REQUIRED on-screen anchors: " + ", ".join(missing[:10]) + "."
        if inject.lower() not in fixed.lower():
            fixed = (fixed + inject).strip()
        if len(fixed) > 1600:
            # Keep the inject; trim the head so anchors survive Agnes limits.
            keep = inject.strip()
            head = fixed[: 1600 - len(keep) - 1]
            fixed = (head + " " + keep).strip()
    blob2 = fixed.lower()
    still = [token for token in required if not _token_in_blob(token, blob2)]
    return {
        "passed": not still,
        "missing": missing,
        "still_missing": still,
        "required": required,
        "fixed_prompt": fixed,
        "check": "keyword_preflight",
        "injected": bool(missing),
    }


def character_base_seed(name: str, visual_description: str) -> int:
    """Stable integer seed from character identity."""
    raw = f"{(name or '').strip().lower()}|{(visual_description or '').strip().lower()}"
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 2_147_483_647
