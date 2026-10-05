"""Mock research provider (BUILD-04G)."""
from __future__ import annotations

from typing import Any

from pipeline.intelligence.contracts import ResearchRequest


class MockResearchProvider:
    def __init__(self) -> None:
        self.calls: list[ResearchRequest] = []

    def reset(self) -> None:
        self.calls.clear()

    def research(self, req: ResearchRequest) -> dict[str, Any]:
        self.calls.append(req)
        claims = [
            {
                "id": "R01",
                "claim": f"{req.canonical_topic} has documented recent developments.",
                "evidence": "secondary",
                "source": "mock_news",
                "confidence": 0.75,
                "freshness": "recent",
            },
            {
                "id": "R02",
                "claim": f"Analysis of {req.canonical_topic} shows measurable audience interest.",
                "evidence": "supporting",
                "source": "mock_analytics",
                "confidence": 0.65,
                "freshness": "recent",
            },
        ]
        pack = {
            "topic": req.canonical_topic,
            "claims": claims,
            "research_fingerprint": req.topic_id,
        }
        return {
            "research": {
                "topic_id": req.topic_id,
                "query": req.query,
                "evidence": claims,
                "status": "completed",
                "provider": "mock",
            },
            "fact_pack": pack,
        }


_PROVIDER: MockResearchProvider | None = None


def get_mock_research_provider() -> MockResearchProvider:
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = MockResearchProvider()
    return _PROVIDER


def reset_mock_research_provider() -> None:
    global _PROVIDER
    _PROVIDER = None
