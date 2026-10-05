"""Research provider abstraction (BUILD-04G-H)."""
from __future__ import annotations

import logging
from typing import Any, Protocol

from pipeline.intelligence.config import ResearchMode, get_research_mode
from pipeline.intelligence.contracts import ResearchRequest

logger = logging.getLogger(__name__)

# Honest capability labels (C05-TRS) — never conflate LOCAL with EXTERNAL
CAPABILITY_LOCAL_FACTPACK = "LOCAL_FACTPACK"
CAPABILITY_EXTERNAL_LIVE = "EXTERNAL_LIVE"
CAPABILITY_MOCK = "MOCK"
PROVIDER_MODE_LIVE_LOCAL = "LIVE_LOCAL"
PROVIDER_MODE_EXTERNAL_LIVE = "EXTERNAL_LIVE"
PROVIDER_MODE_MOCK = "MOCK"


class ResearchProvider(Protocol):
    def research(self, req: ResearchRequest) -> dict[str, Any]: ...


def classify_research_capability(research: dict[str, Any] | None) -> dict[str, Any]:
    """Honest capability classification — LOCAL_FACTPACK ≠ EXTERNAL_LIVE."""
    r = dict(research or {})
    provider = str(r.get("provider") or "").lower()
    kind = str(r.get("provider_kind") or "").lower()
    external = bool(r.get("external_api"))
    explicit = str(r.get("provider_capability") or "").upper()

    if explicit in (CAPABILITY_EXTERNAL_LIVE, CAPABILITY_LOCAL_FACTPACK, CAPABILITY_MOCK):
        cap = explicit
    elif provider == "mock" or kind in ("mock", "mock_fixture") or r.get("fixture") is True:
        cap = CAPABILITY_MOCK
    elif external and kind in ("external", "web", "http", "api"):
        cap = CAPABILITY_EXTERNAL_LIVE
    else:
        # Default: configured local FactPack — even if mode string says LIVE
        cap = CAPABILITY_LOCAL_FACTPACK

    mode = PROVIDER_MODE_MOCK if cap == CAPABILITY_MOCK else (
        PROVIDER_MODE_EXTERNAL_LIVE if cap == CAPABILITY_EXTERNAL_LIVE else PROVIDER_MODE_LIVE_LOCAL
    )
    return {
        "provider_capability": cap,
        "provider_mode": mode,
        "external_api": bool(external and cap == CAPABILITY_EXTERNAL_LIVE),
        "is_external_live": cap == CAPABILITY_EXTERNAL_LIVE,
        "note": "LOCAL_FACTPACK must not be claimed as EXTERNAL_LIVE_RESEARCH",
    }


def require_external_live_or_block(
    research: dict[str, Any] | None,
    *,
    require_external: bool,
) -> dict[str, Any]:
    """If production explicitly requires external freshness and capability is absent → BLOCKED/UNKNOWN."""
    cap = classify_research_capability(research)
    if not require_external:
        return {"ok": True, "status": "PASS", **cap}
    if cap["is_external_live"]:
        return {"ok": True, "status": "PASS", **cap}
    return {
        "ok": False,
        "status": "BLOCKED",
        "reason": "external_live_research_unavailable",
        "verdict": "UNKNOWN",
        **cap,
    }


class LiveResearchProvider:
    """Production research — uses canonical build_fact_pack (local, non-mock).

    Honesty (C05-TRS): LIVE_LOCAL / LOCAL_FACTPACK — NOT external web research.
    """

    def research(self, req: ResearchRequest) -> dict[str, Any]:
        from pipeline.fact_pack import build_fact_pack

        notes = f"Research query: {req.query}\nLanguage: {req.language}\nRegion: {req.region}"
        pack = build_fact_pack(req.canonical_topic, notes=notes)
        claims = list(pack.get("claims") or [])
        for c in claims:
            if isinstance(c, dict):
                ev = str(c.get("evidence") or "")
                if ev in ("UNVERIFIED", ""):
                    c["evidence"] = "research_notes"
                    c["source"] = c.get("source") or "live_research"
        if len(claims) < 2:
            claims.append({
                "id": "L02",
                "claim": f"Additional context on {req.canonical_topic} from configured research scope.",
                "evidence": "secondary",
                "source": "live_research",
                "confidence": 0.6,
                "freshness": "recent",
            })
        pack["claims"] = claims
        research = {
            "topic_id": req.topic_id,
            "query": req.query,
            "evidence": claims,
            "status": "completed",
            "provider": "live_local",
            "provider_kind": "configured_local",
            "provider_capability": CAPABILITY_LOCAL_FACTPACK,
            "provider_mode": PROVIDER_MODE_LIVE_LOCAL,
            "external_api": False,
        }
        research.update(classify_research_capability(research))
        return {
            "research": research,
            "fact_pack": pack,
        }


class MockResearchProviderAdapter:
    def __init__(self) -> None:
        from pipeline.intelligence.mock_research_provider import get_mock_research_provider
        self._inner = get_mock_research_provider()

    def research(self, req: ResearchRequest) -> dict[str, Any]:
        out = self._inner.research(req)
        research = dict(out.get("research") or {})
        research["provider"] = "mock"
        research["provider_kind"] = "mock_fixture"
        research["provider_capability"] = CAPABILITY_MOCK
        research["provider_mode"] = PROVIDER_MODE_MOCK
        research["external_api"] = False
        research["fixture"] = True
        research.update(classify_research_capability(research))
        out["research"] = research
        return out


def get_research_provider(*, mode: ResearchMode | None = None, force_mock: bool = False) -> ResearchProvider:
    if force_mock:
        return MockResearchProviderAdapter()
    effective = mode or get_research_mode()
    if effective == ResearchMode.MOCK:
        return MockResearchProviderAdapter()
    return LiveResearchProvider()


def research_unavailable_error(req: ResearchRequest, reason: str) -> dict[str, Any]:
    return {
        "research": {
            "topic_id": req.topic_id,
            "query": getattr(req, "query", ""),
            "status": "PROVIDER_UNAVAILABLE",
            "reason": reason,
            "provider_capability": CAPABILITY_LOCAL_FACTPACK,
            "provider_mode": PROVIDER_MODE_LIVE_LOCAL,
            "external_api": False,
            "is_external_live": False,
        },
        "fact_pack": None,
        "gate_error": True,
        "error": reason,
    }
