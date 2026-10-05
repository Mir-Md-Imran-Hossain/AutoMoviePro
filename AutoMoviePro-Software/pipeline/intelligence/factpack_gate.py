"""FactPack quality gate — strict (BUILD-04G-H)."""
from __future__ import annotations

import re
from typing import Any

MIN_SUPPORTED_CLAIMS = 2
SUPPORTED_EVIDENCE = frozenset({
    "primary", "secondary", "supporting", "research_notes", "evergreen", "verified",
})
VERIFIED_EVIDENCE = frozenset({"primary", "verified", "peer_reviewed", "official"})


def _classify_claim(c: dict[str, Any]) -> str:
    ev = str(c.get("evidence") or "UNKNOWN").lower()
    if ev in ("conflicting", "conflict"):
        return "CONFLICTING"
    if ev in VERIFIED_EVIDENCE:
        return "VERIFIED"
    if ev in SUPPORTED_EVIDENCE:
        return "SUPPORTED"
    if ev in ("unverified", "unknown", ""):
        return "UNVERIFIED"
    return "UNKNOWN"


def validate_fact_pack(fact_pack: dict[str, Any] | None, *, min_supported: int = MIN_SUPPORTED_CLAIMS) -> dict[str, Any]:
    if not fact_pack:
        return {"verdict": "RESEARCH_REQUIRED", "reason": "missing_fact_pack", "issues": ["missing"]}
    claims = fact_pack.get("claims") or []
    if not claims:
        return {"verdict": "RESEARCH_REQUIRED", "reason": "no_claims", "issues": ["no_claims"]}

    issues: list[str] = []
    conflicts: list[dict[str, Any]] = []
    classified: list[dict[str, Any]] = []
    supported = 0
    verified = 0
    unsupported = 0

    for c in claims:
        if not isinstance(c, dict):
            continue
        cls = _classify_claim(c)
        classified.append({"claim": c.get("claim"), "class": cls, "source": c.get("source")})
        if cls == "CONFLICTING":
            conflicts.append({"claim": c.get("claim"), "evidence": c.get("evidence")})
        elif cls == "VERIFIED":
            verified += 1
            supported += 1
        elif cls == "SUPPORTED":
            supported += 1
        elif cls == "UNVERIFIED":
            unsupported += 1
        if not c.get("source"):
            issues.append(f"missing_source:{c.get('id')}")

    # Numeric/date contradiction heuristic
    conflicts.extend(_detect_contradictions(claims))

    if conflicts:
        return {
            "verdict": "RESEARCH_CONFLICT",
            "reason": "conflicts_detected",
            "issues": issues,
            "conflicts": conflicts,
            "classified": classified,
        }
    if supported < min_supported:
        return {
            "verdict": "RESEARCH_REQUIRED",
            "reason": "insufficient_supported_claims",
            "issues": issues,
            "supported_count": supported,
            "verified_count": verified,
            "unsupported_count": unsupported,
            "classified": classified,
        }
    if unsupported == len(claims):
        return {
            "verdict": "RESEARCH_REQUIRED",
            "reason": "all_unsupported",
            "issues": issues,
            "classified": classified,
        }
    return {
        "verdict": "PASS",
        "reason": "sufficient_evidence",
        "issues": issues,
        "claim_count": len(claims),
        "supported_count": supported,
        "verified_count": verified,
        "unsupported_count": unsupported,
        "classified": classified,
    }


def _detect_contradictions(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    nums: list[tuple[str, float]] = []
    for c in claims:
        text = str(c.get("claim") or "")
        for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*(%|percent|million|billion)?", text.lower()):
            try:
                nums.append((text, float(m.group(1))))
            except ValueError:
                pass
        if "increase" in text.lower() and "decrease" in text.lower():
            out.append({"claim": text, "type": "status_contradiction"})
        if " occurred" in text.lower() and "did not occur" in text.lower():
            out.append({"claim": text, "type": "event_contradiction"})
    for i, a in enumerate(claims):
        ta = str(a.get("claim") or "").lower()
        for b in claims[i + 1 :]:
            tb = str(b.get("claim") or "").lower()
            if ("increase" in ta and "decrease" in tb) or ("decrease" in ta and "increase" in tb):
                if "price" in ta or "price" in tb or len(set(ta.split()) & set(tb.split())) >= 1:
                    out.append({"claim_a": a.get("claim"), "claim_b": b.get("claim"), "type": "status_contradiction"})
    # Same subject wildly different numbers (ignore year/timestamp-like values)
    if len(nums) >= 2:
        filtered = [
            (t, v)
            for t, v in nums
            if not (v >= 1900 and v <= 2100) and v < 1e7  # drop years + cert timestamps
        ]
        if len(filtered) >= 2:
            vals = [v for _, v in filtered]
            texts = {t for t, _ in filtered}
            if (
                max(vals) > 0
                and min(vals) > 0
                and (max(vals) / min(vals)) > 50
                and len(texts) >= 2
            ):
                out.append(
                    {
                        "claim_a": filtered[0][0],
                        "claim_b": filtered[1][0],
                        "type": "numeric_contradiction",
                    }
                )
    return out
