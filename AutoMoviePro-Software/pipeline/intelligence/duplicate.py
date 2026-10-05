"""Layered duplicate detection (BUILD-04G)."""
from __future__ import annotations

from typing import Any, Optional, Sequence

from pipeline.intelligence.contracts import DuplicateResult, DuplicateVerdict
from pipeline.intelligence.normalization import canonical_topic_key, jaccard_similarity, normalize_topic_text
from pipeline.product_registry import is_same_product, normalize_product_key, similarity_score

DUPLICATE_RULE_VERSION = "1.0.0"
TOKEN_JACCARD_THRESHOLD = 0.85
TOKEN_JACCARD_HARD = 0.95
SEMANTIC_PRODUCT_THRESHOLD = 0.72
SEMANTIC_INTENT_THRESHOLD = 0.55
SEMANTIC_JACCARD_SOFT = 0.65
ENTITY_EVENT_SHARED_MIN = 3
ENTITY_EVENT_SIM_MIN = 0.45

_SYNONYM_GROUPS = (
    {"drop", "dropped", "fall", "fell", "fallen", "decline", "declined", "caused"},
    {"stock", "stocks", "share", "shares", "equity"},
    {"bitcoin", "btc"},
    {"apple", "apples"},
)


def _expand_synonyms(tokens: set[str]) -> set[str]:
    out = set(tokens)
    for group in _SYNONYM_GROUPS:
        if tokens & group:
            out |= group
    return out


def merge_duplicate_corpus(*corpora: Sequence[str]) -> list[str]:
    """Merge topic lists for duplicate checks; preserve first occurrence order."""
    seen: set[str] = set()
    out: list[str] = []
    for corpus in corpora:
        for item in corpus:
            t = (item or "").strip()
            if not t:
                continue
            key = canonical_topic_key(t)
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
    return out


def duplicate_rule_fingerprint() -> str:
    """Stable fingerprint for duplicate rule version (cache invalidation aid)."""
    from pipeline.idempotency.fingerprint import hash_text
    payload = (
        f"{DUPLICATE_RULE_VERSION}|{TOKEN_JACCARD_THRESHOLD}|{SEMANTIC_PRODUCT_THRESHOLD}|"
        f"{SEMANTIC_INTENT_THRESHOLD}|{len(_SYNONYM_GROUPS)}"
    )
    return hash_text(payload)[:16]


def _intent_similarity(a: str, b: str) -> float:
    ta = _expand_synonyms(set(canonical_topic_key(a).split()))
    tb = _expand_synonyms(set(canonical_topic_key(b).split()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def check_exact_duplicate(
    candidate: str,
    existing_keys: Sequence[str],
    *,
    candidate_key: str = "",
) -> DuplicateResult:
    key = candidate_key or canonical_topic_key(candidate)
    norm = normalize_topic_text(candidate)
    for ex in existing_keys:
        if not ex:
            continue
        if key and key == canonical_topic_key(ex):
            return DuplicateResult(
                verdict=DuplicateVerdict.DUPLICATE,
                confidence=1.0,
                comparison_target=ex,
                layer="exact_canonical",
                evidence={"candidate_key": key},
            )
        if norm == normalize_topic_text(ex):
            return DuplicateResult(
                verdict=DuplicateVerdict.DUPLICATE,
                confidence=1.0,
                comparison_target=ex,
                layer="exact_title",
            )
    return DuplicateResult(verdict=DuplicateVerdict.UNIQUE, confidence=1.0, layer="exact")


def check_token_duplicate(candidate: str, existing: Sequence[str], *, threshold: float = TOKEN_JACCARD_THRESHOLD) -> DuplicateResult:
    for ex in existing:
        sim = jaccard_similarity(candidate, ex)
        if sim >= threshold:
            return DuplicateResult(
                verdict=DuplicateVerdict.DUPLICATE if sim >= TOKEN_JACCARD_HARD else DuplicateVerdict.POSSIBLE_DUPLICATE,
                confidence=sim,
                comparison_target=ex,
                layer="token_jaccard",
                evidence={"similarity": sim},
            )
    return DuplicateResult(verdict=DuplicateVerdict.UNIQUE, confidence=0.9, layer="token")


def check_semantic_duplicate(candidate: str, existing: Sequence[str], *, threshold: float = SEMANTIC_PRODUCT_THRESHOLD) -> DuplicateResult:
    """Product-registry similarity + entity overlap for same-event detection."""
    for ex in existing:
        if is_same_product(candidate, ex, threshold=threshold):
            return DuplicateResult(
                verdict=DuplicateVerdict.DUPLICATE,
                confidence=similarity_score(candidate, ex),
                comparison_target=ex,
                layer="semantic_product",
            )
        sim = jaccard_similarity(candidate, ex)
        intent_sim = _intent_similarity(candidate, ex)
        if sim >= SEMANTIC_JACCARD_SOFT or intent_sim >= SEMANTIC_INTENT_THRESHOLD:
            return DuplicateResult(
                verdict=DuplicateVerdict.POSSIBLE_DUPLICATE,
                confidence=max(sim, intent_sim),
                comparison_target=ex,
                layer="semantic_intent",
                evidence={"similarity": sim, "intent_similarity": intent_sim},
            )
    return DuplicateResult(verdict=DuplicateVerdict.UNIQUE, confidence=0.85, layer="semantic")


def analyze_duplicate(
    candidate: str,
    existing: Sequence[str],
    *,
    existing_keys: Optional[Sequence[str]] = None,
    candidate_revision_id: str = "r001",
    allow_intentional_revision: bool = False,
) -> DuplicateResult:
    """Layer 1→4 duplicate strategy — deterministic, no LLM."""
    if not candidate.strip():
        return DuplicateResult(verdict=DuplicateVerdict.UNKNOWN, confidence=0.0, layer="empty", evidence={"reason": "empty_candidate"})

    cand_key = canonical_topic_key(candidate)
    if allow_intentional_revision and candidate_revision_id not in ("", "r001"):
        for ex in existing:
            if cand_key and cand_key == canonical_topic_key(ex):
                return DuplicateResult(
                    verdict=DuplicateVerdict.UNIQUE,
                    confidence=0.9,
                    layer="revision_exempt",
                    comparison_target=ex,
                    evidence={"revision_id": candidate_revision_id, "rule_version": DUPLICATE_RULE_VERSION},
                )

    keys = list(existing_keys or []) + [canonical_topic_key(e) for e in existing]
    r1 = check_exact_duplicate(candidate, existing, candidate_key=cand_key)
    if r1.verdict == DuplicateVerdict.DUPLICATE:
        return r1

    r2 = check_token_duplicate(candidate, existing)
    if r2.verdict in (DuplicateVerdict.DUPLICATE, DuplicateVerdict.POSSIBLE_DUPLICATE):
        return r2

    r3 = check_semantic_duplicate(candidate, existing)
    if r3.verdict != DuplicateVerdict.UNIQUE:
        return r3

    # Layer 4: entity+event — shared proper nouns + action verbs
    cand_toks = set(canonical_topic_key(candidate).split())
    action_synonyms = {"drop", "dropped", "fall", "fell", "fallen", "decline", "declined", "shares", "stock"}
    for ex in existing:
        ex_toks = set(canonical_topic_key(ex).split())
        shared = cand_toks & ex_toks
        shared_entities = {t for t in shared if t not in action_synonyms}
        action_overlap = bool((cand_toks | ex_toks) & action_synonyms) and len(shared) >= 2
        sim = jaccard_similarity(candidate, ex)
        intent_sim = _intent_similarity(candidate, ex)
        if (len(shared_entities) >= 1 and action_overlap and max(sim, intent_sim) >= 0.35) or (
            len(shared) >= ENTITY_EVENT_SHARED_MIN and sim >= ENTITY_EVENT_SIM_MIN
        ) or intent_sim >= SEMANTIC_INTENT_THRESHOLD:
            return DuplicateResult(
                verdict=DuplicateVerdict.POSSIBLE_DUPLICATE,
                confidence=max(sim, intent_sim, len(shared) / max(len(cand_toks | ex_toks), 1)),
                comparison_target=ex,
                layer="entity_event",
                evidence={"shared_tokens": list(shared)[:8], "rule_version": DUPLICATE_RULE_VERSION},
            )

    return DuplicateResult(
        verdict=DuplicateVerdict.UNIQUE,
        confidence=0.88,
        layer="all_passed",
        evidence={"rule_version": DUPLICATE_RULE_VERSION},
    )
