"""Topic ranking (BUILD-04G)."""
from __future__ import annotations

from typing import Any, Sequence

from pipeline.intelligence.contracts import TopicCandidate, TopicScoreResult
from pipeline.intelligence.scoring import score_candidate, ChannelProfile


def rank_candidates(
    candidates: Sequence[TopicCandidate],
    profile: ChannelProfile,
    *,
    existing_topics: Sequence[str] = (),
    scores: dict[str, TopicScoreResult] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_entities: set[str] = set()

    for c in candidates:
        if scores is not None:
            sr = scores.get(c.topic_id)
            if sr is None:
                results.append({
                    "candidate": c.to_dict(),
                    "score": {
                        "topic_id": c.topic_id,
                        "total_score": 0.0,
                        "hard_blocked": True,
                        "block_reason": "MISSING_RESEARCH_SCORE",
                    },
                    "eligible": False,
                })
                continue
        else:
            sr = score_candidate(c, profile, existing_topics=existing_topics)
        if sr.hard_blocked:
            results.append({"candidate": c.to_dict(), "score": sr.to_dict(), "eligible": False})
            continue
        # Diversity: penalize same canonical key
        key = c.canonical_topic or c.title
        diversity_penalty = 0.15 if key in seen_entities else 0.0
        seen_entities.add(key)
        adjusted = max(0.0, sr.total_score - diversity_penalty)
        results.append({
            "candidate": c.to_dict(),
            "score": {**sr.to_dict(), "total_score": round(adjusted, 4), "diversity_penalty": diversity_penalty},
            "eligible": adjusted >= 0.45,
        })

    results.sort(key=lambda r: float(r["score"].get("total_score") or 0), reverse=True)
    for i, r in enumerate(results):
        if r.get("eligible"):
            r["score"]["ranking_position"] = i + 1
    return results


def select_top(ranked: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    for r in ranked:
        if r.get("eligible"):
            return r
    return None
