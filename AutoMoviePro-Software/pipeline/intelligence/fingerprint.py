"""Research fingerprint and evidence (BUILD-04G)."""
from __future__ import annotations

from typing import Any, Sequence

from pipeline.idempotency.fingerprint import compute_fingerprint, hash_text
from pipeline.intelligence.contracts import (
    EVALUATOR_VERSION,
    EvidenceClass,
    INTELLIGENCE_CONTRACT_VERSION,
    PROMPT_VERSION,
    ResearchRequest,
)


def compute_research_fingerprint(req: ResearchRequest, *, job_id: str = "", provider: str = "") -> str:
    return compute_fingerprint(
        job_id=job_id or str(req.topic_id),
        stage="research",
        entity_id=f"research-{req.topic_id}",
        contract_version=INTELLIGENCE_CONTRACT_VERSION,
        provider=provider or req.provider,
        model=req.model,
        inputs={
            "canonical_topic": req.canonical_topic.strip(),
            "query": req.query.strip(),
            "language": req.language,
            "region": req.region,
            "time_window": req.time_window,
            "prompt_version": req.prompt_version,
        },
    )


def classify_evidence(source: str, confidence: float = 0.5) -> EvidenceClass:
    s = (source or "").lower()
    if confidence < 0.3:
        return EvidenceClass.WEAK
    if s in ("primary", "official", "peer_reviewed"):
        return EvidenceClass.PRIMARY
    if s in ("secondary", "news", "research_notes"):
        return EvidenceClass.SECONDARY
    if s in ("conflicting", "conflict"):
        return EvidenceClass.CONFLICTING
    if s in ("unknown", ""):
        return EvidenceClass.UNKNOWN
    return EvidenceClass.SUPPORTING


def detect_source_diversity(sources: Sequence[str | dict[str, Any]]) -> dict[str, Any]:
    domains: set[str] = set()
    publishers: set[str] = set()
    texts: list[str] = []
    for s in sources:
        if isinstance(s, dict):
            dom = str(s.get("domain") or s.get("source") or "").lower().strip()
            pub = str(s.get("publisher") or s.get("source") or "").lower().strip()
            txt = str(s.get("claim") or s.get("text") or "")[:200]
            if dom:
                domains.add(_normalize_domain(dom))
            if pub:
                publishers.add(pub)
            if txt:
                texts.append(txt)
        elif s:
            domains.add(_normalize_domain(str(s).lower()))
    syndicated = 0
    for i, a in enumerate(texts):
        for b in texts[i + 1 :]:
            if a and b and (a in b or b in a) and len(min(a, b, key=len)) > 40:
                syndicated += 1
    unique_domains = len(domains)
    return {
        "unique_sources": unique_domains,
        "unique_publishers": len(publishers),
        "syndicated_risk": syndicated,
        "diverse": unique_domains >= 2 and syndicated == 0,
        "relationship_unknown": unique_domains >= 2 and syndicated > 0,
    }


def _normalize_domain(source: str) -> str:
    s = source.replace("https://", "").replace("http://", "").split("/")[0]
    if s.startswith("www."):
        s = s[4:]
    return s


def detect_conflicts(claims: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    import re
    for i, a in enumerate(claims):
        for b in claims[i + 1 :]:
            if a.get("evidence") == "conflicting" or b.get("evidence") == "conflicting":
                conflicts.append({"claim_a": a.get("claim"), "claim_b": b.get("claim"), "type": "explicit"})
            if a.get("verdict") == "CONFLICT" or b.get("verdict") == "CONFLICT":
                conflicts.append({"claim_a": a.get("claim"), "claim_b": b.get("claim"), "type": "verdict"})
            ta = str(a.get("claim") or "").lower()
            tb = str(b.get("claim") or "").lower()
            if ("increase" in ta and "decrease" in tb) or ("decrease" in ta and "increase" in tb):
                if _shared_subject(ta, tb):
                    conflicts.append({"claim_a": a.get("claim"), "claim_b": b.get("claim"), "type": "status"})
            nums_a = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", ta)]
            nums_b = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", tb)]
            if nums_a and nums_b and _shared_subject(ta, tb):
                if max(nums_a) / max(max(nums_b), 0.001) > 10 or max(nums_b) / max(max(nums_a), 0.001) > 10:
                    conflicts.append({"claim_a": a.get("claim"), "claim_b": b.get("claim"), "type": "numeric"})
    return conflicts


def _shared_subject(a: str, b: str) -> bool:
    wa = set(a.split())
    wb = set(b.split())
    return len(wa & wb) >= 2


def topic_identity_fingerprint(
    *,
    job_id: str,
    channel_id: int,
    fmt: str,
    canonical_topic: str,
    prompt_version: str = PROMPT_VERSION,
) -> str:
    return compute_fingerprint(
        job_id=job_id,
        stage="topic",
        entity_id=f"topic-{channel_id}-{fmt}",
        contract_version=INTELLIGENCE_CONTRACT_VERSION,
        provider="intelligence",
        model=EVALUATOR_VERSION,
        inputs={
            "channel_id": channel_id,
            "format": fmt,
            "canonical_topic": canonical_topic,
            "prompt_version": prompt_version,
        },
    )
