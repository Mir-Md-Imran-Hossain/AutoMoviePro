"""Topic intelligence orchestrator (BUILD-04G-H)."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional, Sequence

from app.config import DATA_DIR
from pipeline.intelligence.cache_registry import get_channel_version, ranking_cache_key
from pipeline.intelligence.contracts import (
    ApiCostMetrics,
    ChannelProfile,
    ContentFormat,
    DuplicateVerdict,
    RejectionReason,
    ResearchRequest,
    TopicCandidate,
    TopicLifecycleStatus,
    TopicScoreResult,
)
from pipeline.intelligence.candidates import candidate_from_dict
from pipeline.intelligence.discovery import discover_topic_candidates
from pipeline.intelligence.duplicate import analyze_duplicate, merge_duplicate_corpus
from pipeline.intelligence.factpack_gate import validate_fact_pack
from pipeline.intelligence.fingerprint import detect_source_diversity
from pipeline.intelligence.provenance import record_topic_provenance
from pipeline.intelligence.ranking import rank_candidates, select_top
from pipeline.intelligence.research_runtime import execute_research_request
from pipeline.intelligence.reserve_queue import (
    consume_top,
    load_reserve,
    repair_reserve,
    update_reserve,
    validate_reserve_integrity,
)
from pipeline.intelligence.scoring import score_candidate
from pipeline.intelligence.trend import seo_heuristic_score

logger = logging.getLogger(__name__)

PRELIMINARY_THRESHOLD = 0.25
RESEARCH_TTL_SEC = 86400


def _preliminary_filter(
    candidates: Sequence[TopicCandidate],
    profile: ChannelProfile,
    existing_topics: Sequence[str],
    historical_topics: Sequence[str] = (),
) -> list[TopicCandidate]:
    corpus = merge_duplicate_corpus(existing_topics, historical_topics)
    out: list[TopicCandidate] = []
    for c in candidates:
        c.status = TopicLifecycleStatus.NORMALIZED
        dup = analyze_duplicate(
            c.title,
            corpus,
            candidate_revision_id=c.revision_id,
            allow_intentional_revision=bool(c.metadata.get("intentional_revision")),
        )
        c.metadata["duplicate_check"] = dup.to_dict()
        c.status = TopicLifecycleStatus.CHECKING_DUPLICATE
        if dup.verdict in (DuplicateVerdict.DUPLICATE, DuplicateVerdict.UNKNOWN):
            c.status = TopicLifecycleStatus.REJECTED
            c.metadata["rejection"] = dup.verdict.value
            continue
        for bad in profile.forbidden_topics:
            if bad and bad.lower() in c.title.lower():
                c.status = TopicLifecycleStatus.BLOCKED
                continue
        out.append(c)
    return out


def _research_candidate(
    work_dir: Path,
    profile: ChannelProfile,
    c: TopicCandidate,
    *,
    job_id: str,
    use_mock_research: bool | None,
) -> dict[str, Any]:
    c.status = TopicLifecycleStatus.RESEARCHING
    req = ResearchRequest(
        topic_id=c.topic_id,
        canonical_topic=c.canonical_topic,
        query=c.canonical_topic,
        language=profile.language,
        region=profile.target_region,
    )
    rr = execute_research_request(work_dir, req, job_id=job_id, use_mock=use_mock_research)
    gate = validate_fact_pack(rr.fact_pack)
    claims = (rr.fact_pack or {}).get("claims") or []
    diversity = detect_source_diversity(claims)
    return {
        "research": rr.research,
        "fact_pack": rr.fact_pack,
        "gate": gate,
        "fingerprint": rr.fingerprint,
        "action": rr.action,
        "evidence_count": len(claims),
        "source_diversity": diversity,
        "provider_mode": rr.provider_mode,
        "success": rr.success and gate.get("verdict") == "PASS",
    }


def evaluate_candidates(
    candidates: Sequence[TopicCandidate],
    profile: ChannelProfile,
    *,
    existing_topics: Sequence[str] = (),
    historical_topics: Sequence[str] = (),
    do_research: bool = False,
    work_dir: Path | None = None,
    job_id: str = "eval",
    use_mock_research: bool | None = True,
) -> tuple[list[dict[str, Any]], dict[str, TopicScoreResult]]:
    """Evaluate candidates — research optional (legacy test API)."""
    work_dir = Path(work_dir or DATA_DIR / "intelligence" / "eval_tmp")
    work_dir.mkdir(parents=True, exist_ok=True)
    filtered = _preliminary_filter(list(candidates), profile, existing_topics, historical_topics)
    scores: dict[str, TopicScoreResult] = {}
    for c in filtered:
        from pipeline.intelligence.trend import content_gap_score as cgs
        gap = cgs(c.title, list(historical_topics))
        evidence_count = 0
        if do_research:
            rr = _research_candidate(work_dir, profile, c, job_id=job_id, use_mock_research=use_mock_research)
            evidence_count = int(rr.get("evidence_count") or 0)
            if not rr.get("success"):
                scores[c.topic_id] = TopicScoreResult(
                    topic_id=c.topic_id, total_score=0.0, hard_blocked=True,
                    block_reason="LOW_EVIDENCE", rejection_reason=RejectionReason.LOW_EVIDENCE.value,
                )
                continue
        dup = analyze_duplicate(
            c.title,
            merge_duplicate_corpus(existing_topics, historical_topics),
            candidate_revision_id=c.revision_id,
            allow_intentional_revision=bool(c.metadata.get("intentional_revision")),
        )
        sr = score_candidate(c, profile, existing_topics=existing_topics, duplicate_result=dup, evidence_count=evidence_count, content_gap_score=gap)
        c.metadata["seo_heuristic_score"] = seo_heuristic_score(c.title, profile.niche)
        scores[c.topic_id] = sr
    evaluated = [{"candidate": c.to_dict(), "score": scores[c.topic_id].to_dict()} for c in filtered if c.topic_id in scores]
    return evaluated, scores


def run_topic_intelligence(
    work_dir: Path,
    profile: ChannelProfile,
    candidates: Sequence[TopicCandidate | dict[str, Any]] | None = None,
    *,
    job_id: str = "",
    existing_topics: Sequence[str] = (),
    historical_topics: Sequence[str] = (),
    do_research: bool = True,
    use_mock_research: bool | None = None,
    auto_discover: bool = False,
    discover_count: int = 8,
) -> dict[str, Any]:
    work_dir = Path(work_dir)
    job_id = job_id or work_dir.name
    metrics = ApiCostMetrics()
    channel_version = get_channel_version(profile.channel_id)

    # Always enrich anti-repeat corpus from persisted channel history when callers omit it
    hist = list(historical_topics or [])
    if not hist and profile.channel_id:
        try:
            from pipeline.intelligence.topic_history import load_channel_topic_history

            hist = load_channel_topic_history(
                int(profile.channel_id),
                niche=str(profile.niche or ""),
            )
        except Exception:
            hist = []
    historical_topics = hist
    existing_topics = list(existing_topics or []) or list(hist)

    if candidates is None or (auto_discover and not candidates):
        reserved = [e.get("title") or "" for e in load_reserve(None, ContentFormat.LONG, channel_id=profile.channel_id, language=profile.language)]
        reserved += [e.get("title") or "" for e in load_reserve(None, ContentFormat.SHORT, channel_id=profile.channel_id, language=profile.language)]
        objs = discover_topic_candidates(profile, fmt=ContentFormat.LONG, count=discover_count, historical=historical_topics, reserved=reserved, blocked=existing_topics)
        short_cands = discover_topic_candidates(profile, fmt=ContentFormat.SHORT, count=discover_count, historical=historical_topics, reserved=reserved, blocked=existing_topics)
        objs = objs + short_cands
    else:
        objs = [c if isinstance(c, TopicCandidate) else candidate_from_dict(c) for c in candidates]

    filtered = _preliminary_filter(objs, profile, existing_topics, historical_topics)
    research_results: dict[str, Any] = {}
    scores: dict[str, TopicScoreResult] = {}

    for c in filtered:
        from pipeline.intelligence.trend import content_gap_score as cgs
        gap = cgs(c.title, list(historical_topics))
        rr_data: dict[str, Any] = {}
        evidence_count = 0
        if do_research:
            rr_data = _research_candidate(work_dir, profile, c, job_id=job_id, use_mock_research=use_mock_research)
            metrics.request_count += 1 if rr_data.get("action") == "execute" else 0
            if rr_data.get("action") == "reuse":
                metrics.cache_hits += 1
                metrics.avoided_calls += 1
            research_results[c.topic_id] = rr_data
            evidence_count = int(rr_data.get("evidence_count") or 0)
            research = rr_data.get("research") or {}
            c.metadata["researched_at"] = research.get("timestamp") or time.time()
            c.metadata["trend_evidence"] = str(c.metadata.get("trend_evidence") or research.get("trend_evidence") or "UNVERIFIED")
            if not rr_data.get("success"):
                sr = TopicScoreResult(
                    topic_id=c.topic_id,
                    total_score=0.0,
                    hard_blocked=True,
                    block_reason=str((rr_data.get("gate") or {}).get("verdict") or "LOW_EVIDENCE"),
                    rejection_reason=RejectionReason.LOW_EVIDENCE.value,
                )
                scores[c.topic_id] = sr
                c.status = TopicLifecycleStatus.REJECTED
                continue

        dup = analyze_duplicate(
            c.title,
            merge_duplicate_corpus(existing_topics, historical_topics),
            candidate_revision_id=c.revision_id,
            allow_intentional_revision=bool(c.metadata.get("intentional_revision")),
        )
        sr = score_candidate(
            c, profile,
            existing_topics=existing_topics,
            duplicate_result=dup,
            evidence_count=evidence_count,
            content_gap_score=gap,
        )
        c.metadata["seo_heuristic_score"] = seo_heuristic_score(c.title, profile.niche)
        c.metadata["channel_version"] = channel_version
        scores[c.topic_id] = sr
        c.status = TopicLifecycleStatus.EVALUATED if not sr.hard_blocked else TopicLifecycleStatus.REJECTED

    evaluated = [{"candidate": c.to_dict(), "score": scores[c.topic_id].to_dict()} for c in filtered if c.topic_id in scores]

    ranked_long = rank_candidates([c for c in filtered if c.format == ContentFormat.LONG and c.topic_id in scores], profile, existing_topics=existing_topics, scores=scores)
    ranked_short = rank_candidates([c for c in filtered if c.format == ContentFormat.SHORT and c.topic_id in scores], profile, existing_topics=existing_topics, scores=scores)

    long_reserve = update_reserve(None, ContentFormat.LONG, ranked_long, channel_id=profile.channel_id, language=profile.language)
    short_reserve = update_reserve(None, ContentFormat.SHORT, ranked_short, channel_id=profile.channel_id, language=profile.language)

    for fmt, ranked in ((ContentFormat.LONG, ranked_long), (ContentFormat.SHORT, ranked_short)):
        top = select_top(ranked)
        if top and top.get("candidate"):
            cand = top["candidate"]
            tid = str(cand.get("topic_id") or "")
            record_topic_provenance(
                work_dir,
                topic_id=tid,
                discovery={
                    "source": cand.get("source"),
                    "channel_id": profile.channel_id,
                    **((cand.get("metadata") or {}).get("provenance") or {}),
                },
                ranking=top.get("score"),
                research=research_results.get(tid),
            )

    out = {
        "evaluated": evaluated,
        "ranked_long": ranked_long,
        "ranked_short": ranked_short,
        "research": research_results,
        "metrics": metrics.to_dict(),
        "long_reserve": long_reserve,
        "short_reserve": short_reserve,
        "ranking_cache_key": ranking_cache_key(profile.channel_id, "ALL"),
        "channel_version": channel_version,
        "timestamp": time.time(),
    }
    out_path = work_dir / "intelligence" / "topic_intelligence_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def select_topic_for_production(
    work_dir: Path,
    profile: ChannelProfile,
    *,
    fmt: ContentFormat = ContentFormat.LONG,
) -> dict[str, Any]:
    """Pop next diverse, non-placeholder reserve topic; refill from discovery if needed."""
    from pipeline.intelligence.topic_history import (
        is_repeat_of_history,
        load_channel_topic_history,
        record_topic_use,
    )
    from pipeline.intelligence.topic_quality import validate_topic_quality

    work_dir = Path(work_dir)
    historical = load_channel_topic_history(
        int(profile.channel_id or 0),
        niche=str(profile.niche or ""),
    )
    # Drop placeholder / invalid rows still sitting in old reserves
    try:
        from pipeline.intelligence.reserve_queue import purge_low_quality_reserve

        purge_low_quality_reserve(
            None, fmt, channel_id=profile.channel_id, language=profile.language, niche=profile.niche
        )
    except Exception:
        pass

    skipped: list[str] = []
    for _attempt in range(20):
        top, remaining = consume_top(
            None, fmt, channel_id=profile.channel_id, language=profile.language
        )
        if not top:
            # Refill reserve with history-aware discovery
            try:
                run_topic_intelligence(
                    work_dir,
                    profile,
                    None,
                    job_id=f"refill-{profile.channel_id}-{fmt.value}",
                    historical_topics=historical,
                    existing_topics=historical,
                    auto_discover=True,
                    discover_count=10,
                    do_research=False,
                    use_mock_research=True,
                )
            except Exception as exc:
                logger.warning("reserve refill failed: %s", exc)
            top, remaining = consume_top(
                None, fmt, channel_id=profile.channel_id, language=profile.language
            )
            if not top:
                return {
                    "selected": None,
                    "reason": "empty_reserve",
                    "remaining": 0,
                    "status": "RESERVE_DEPLETED",
                    "skipped": skipped,
                }

        title = str(top.get("title") or top.get("canonical_topic") or "").strip()
        quality = validate_topic_quality(title, niche=str(profile.niche or ""))
        if not quality.get("ok"):
            skipped.append(title or "(empty)")
            continue
        if is_repeat_of_history(title, historical, recent_n=16):
            skipped.append(title)
            continue

        record_topic_provenance(
            work_dir,
            topic_id=str(top.get("topic_id") or title or "unknown"),
            discovery={
                "selected_from_reserve": True,
                "channel_id": profile.channel_id,
                "format": fmt.value,
            },
            ranking={"rank": top.get("rank"), "score": top.get("score")},
        )
        record_topic_use(
            int(profile.channel_id or 0),
            title,
            source="reserve_consume",
            video_type=fmt.value.lower(),
            niche=str(profile.niche or ""),
        )
        explanation = []
        if top.get("relevance_reason"):
            explanation.append(str(top["relevance_reason"]))
        explanation.append("Research-validated reserve topic")
        explanation.append("Anti-repeat history applied")
        return {
            "selected": top,
            "selection_reason": "; ".join(explanation),
            "ranking_position": 1,
            "remaining": len(remaining),
            "skipped_repeats": skipped,
        }

    return {
        "selected": None,
        "reason": "all_reserve_topics_repeat_or_invalid",
        "remaining": 0,
        "status": "RESERVE_DEPLETED",
        "skipped": skipped,
    }


def refresh_topic_intelligence(work_dir: Path, profile: ChannelProfile, *, use_mock_research: bool | None = None) -> dict[str, Any]:
    """Daily maintenance — repair, rerank with research freshness."""
    from pipeline.intelligence.topic_history import load_channel_topic_history

    work_dir = Path(work_dir)
    report: dict[str, Any] = {"repaired": {}, "reserves": {}, "reranked": {}}
    historical = load_channel_topic_history(
        int(profile.channel_id or 0),
        niche=str(profile.niche or ""),
    )

    for fmt in (ContentFormat.LONG, ContentFormat.SHORT):
        report["repaired"][fmt.value] = repair_reserve(None, fmt, channel_id=profile.channel_id, language=profile.language)
        try:
            from pipeline.intelligence.reserve_queue import purge_low_quality_reserve

            report.setdefault("purged", {})[fmt.value] = purge_low_quality_reserve(
                None, fmt, channel_id=profile.channel_id, language=profile.language, niche=profile.niche
            )
        except Exception:
            pass
        entries = load_reserve(None, fmt, channel_id=profile.channel_id, language=profile.language)
        ok, issues = validate_reserve_integrity(entries)
        report["reserves"][fmt.value] = {"integrity_ok": ok, "issues": issues, "count": len(entries)}

        # Re-evaluate existing reserve entries
        cands = [candidate_from_dict({**e, "format": fmt.value, "channel_id": profile.channel_id}) for e in entries]
        if cands:
            result = run_topic_intelligence(
                work_dir, profile, cands,
                job_id=f"refresh-{profile.channel_id}",
                historical_topics=historical,
                existing_topics=historical,
                do_research=True,
                use_mock_research=use_mock_research,
            )
            report["reranked"][fmt.value] = {"count": len(result.get("evaluated") or [])}

    if report["reserves"].get("LONG", {}).get("count", 0) < 5 or report["reserves"].get("SHORT", {}).get("count", 0) < 5:
        disc = run_topic_intelligence(
            work_dir, profile, None,
            job_id=f"discover-{profile.channel_id}",
            historical_topics=historical,
            existing_topics=historical,
            auto_discover=True,
            do_research=True,
            use_mock_research=use_mock_research,
        )
        report["discovery_refill"] = disc.get("long_reserve"), disc.get("short_reserve")

    report["historical_count"] = len(historical)
    report["timestamp"] = time.time()
    maint_path = work_dir / "intelligence" / "maintenance_report.json"
    maint_path.parent.mkdir(parents=True, exist_ok=True)
    maint_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
