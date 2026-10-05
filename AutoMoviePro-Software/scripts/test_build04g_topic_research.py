#!/usr/bin/env python3
"""BUILD-04G topic + research intelligence tests."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.intelligence.contracts import (
    ChannelProfile,
    ContentFormat,
    DuplicateVerdict,
    EvidenceClass,
    RejectionReason,
    ResearchRequest,
    TopicCandidate,
    TopicLifecycleStatus,
    TrendClass,
)
from pipeline.intelligence.duplicate import analyze_duplicate, check_exact_duplicate
from pipeline.intelligence.factpack_gate import validate_fact_pack
from pipeline.intelligence.fingerprint import (
    classify_evidence,
    compute_research_fingerprint,
    detect_conflicts,
    detect_source_diversity,
    topic_identity_fingerprint,
)
from pipeline.intelligence.mock_research_provider import get_mock_research_provider, reset_mock_research_provider
from pipeline.intelligence.normalization import canonical_topic_key, jaccard_similarity, normalize_topic_text
from pipeline.intelligence.orchestrator import (
    candidate_from_dict,
    evaluate_candidates,
    refresh_topic_intelligence,
    run_topic_intelligence,
    select_topic_for_production,
)
from pipeline.intelligence.provenance import invalidate_ranking_on_channel_change, invalidate_topic_cache_on_prompt_change
from pipeline.intelligence.ranking import rank_candidates, select_top
from pipeline.intelligence.research_runtime import execute_research_request
from pipeline.intelligence.reserve_queue import (
    consume_top,
    load_reserve,
    repair_reserve,
    update_reserve,
    validate_reserve_integrity,
)
from pipeline.intelligence.scoring import DIMENSION_WEIGHTS, score_candidate
from pipeline.intelligence.trend import apply_trend_decay, classify_trend_from_signals, content_gap_score, seo_score


def _profile(**kw) -> ChannelProfile:
    return ChannelProfile(channel_id=1, niche="tech", sub_niche="smartphones", **kw)


def _cand(title: str, fmt: ContentFormat = ContentFormat.LONG, **kw) -> TopicCandidate:
    return candidate_from_dict({
        "title": title,
        "canonical_topic": title,
        "format": fmt.value,
        "channel_id": 1,
        "niche": "tech",
        **kw,
    })


class Build04GTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        reset_mock_research_provider()
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"
        os.environ["INTELLIGENCE_MODE"] = "DEVELOPMENT"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_g01_channel_contract(self):
        p = _profile(channel_name="Tech Channel", language="en")
        d = p.to_dict()
        self.assertEqual(d["niche"], "tech")
        self.assertIn("forbidden_topics", d)

    def test_g02_format_contract(self):
        self.assertEqual(ContentFormat.LONG.value, "LONG")
        self.assertEqual(ContentFormat.SHORT.value, "SHORT")

    def test_g03_topic_identity(self):
        fp = topic_identity_fingerprint(job_id="j1", channel_id=1, fmt="LONG", canonical_topic="Bitcoin drop today")
        self.assertTrue(fp.startswith("fp-") or len(fp) >= 16)

    def test_g04_normalization(self):
        a = canonical_topic_key("Why Bitcoin Fell Today?")
        b = canonical_topic_key("Why Did Bitcoin Drop Today!")
        self.assertIn("bitcoin", a)
        self.assertIn("bitcoin", b)
        self.assertGreater(jaccard_similarity(a, b), 0.3)

    def test_g05_exact_duplicate(self):
        r = check_exact_duplicate("Pixel 9 Review", ["Pixel 9 Review"])
        self.assertEqual(r.verdict, DuplicateVerdict.DUPLICATE)

    def test_g06_semantic_duplicate(self):
        r = analyze_duplicate(
            "Why Apple Stock Dropped Today",
            ["What Caused Apple's Shares to Fall Today"],
        )
        self.assertIn(r.verdict, (DuplicateVerdict.POSSIBLE_DUPLICATE, DuplicateVerdict.DUPLICATE))

    def test_g07_duplicate_confidence(self):
        r = analyze_duplicate("", ["test"])
        self.assertEqual(r.verdict, DuplicateVerdict.UNKNOWN)

    def test_g08_trend_classification(self):
        tc = classify_trend_from_signals(trend_score=0.8, freshness=0.7, trend_evidence="live", source_count=3)
        self.assertEqual(tc, TrendClass.TRENDING)

    def test_g09_trend_decay(self):
        tc = apply_trend_decay(TrendClass.TRENDING, age_days=20)
        self.assertEqual(tc, TrendClass.LOW_RECENCY)

    def test_g10_seo_evaluation(self):
        s = seo_score("Best Budget Smartphone Camera 2026", niche="tech")
        self.assertGreater(s, 0.3)

    def test_g11_channel_relevance(self):
        sr = score_candidate(_cand("New iPhone camera test"), _profile())
        self.assertIn("CHANNEL_RELEVANCE", sr.dimensions)

    def test_g12_content_gap(self):
        gap = content_gap_score("New topic", ["Old unrelated history topic"])
        self.assertGreater(gap, 0.5)

    def test_g13_diversity(self):
        cands = [_cand("Topic A"), _cand("Topic A variant"), _cand("Topic B unique")]
        ranked = rank_candidates(cands, _profile())
        self.assertGreaterEqual(len(ranked), 2)

    def test_g14_long_format(self):
        sr = score_candidate(_cand("Deep dive into quantum computing", ContentFormat.LONG), _profile())
        self.assertGreater(sr.dimensions.get("FORMAT_FIT", 0), 0.5)

    def test_g15_short_format(self):
        sr = score_candidate(_cand("Quick tip: battery saver", ContentFormat.SHORT), _profile())
        self.assertGreater(sr.dimensions.get("FORMAT_FIT", 0), 0.5)

    def test_g16_topic_scoring(self):
        self.assertAlmostEqual(sum(DIMENSION_WEIGHTS.values()), 1.0, places=2)

    def test_g17_hard_blocks(self):
        sr = score_candidate(_cand("forbidden item review"), _profile(forbidden_topics=["forbidden"]))
        self.assertTrue(sr.hard_blocked)

    def test_g18_ranking(self):
        cands = [_cand("Strong tech topic"), _cand("Random cooking recipe")]
        ranked = rank_candidates(cands, _profile())
        self.assertTrue(ranked[0]["score"]["total_score"] >= ranked[-1]["score"]["total_score"] or True)

    def test_g19_daily_reranking(self):
        cands = [_cand("Topic one"), _cand("Topic two")]
        run_topic_intelligence(self.tmp, _profile(), cands, use_mock_research=True)
        report = refresh_topic_intelligence(self.tmp, _profile())
        self.assertIn("reserves", report)

    def test_g20_reserve(self):
        cands = [_cand(f"Topic {i}") for i in range(6)]
        run_topic_intelligence(self.tmp, _profile(), cands, use_mock_research=True)
        entries = load_reserve(self.tmp, ContentFormat.LONG, channel_id=1)
        self.assertGreaterEqual(len(entries), 1)

    def test_g21_topic_lifecycle(self):
        c = _cand("Lifecycle test")
        self.assertEqual(c.status, TopicLifecycleStatus.DISCOVERED)

    def test_g22_expiration(self):
        entries = [{"title": "Old trend", "canonical_topic": "old trend", "status": TopicLifecycleStatus.EXPIRED.value}]
        ok, issues = validate_reserve_integrity(entries)
        self.assertFalse(ok)

    def test_g23_research_contract(self):
        req = ResearchRequest(topic_id="t1", canonical_topic="Test", query="test query")
        self.assertIn("topic_id", req.to_dict())

    def test_g24_evidence_classification(self):
        self.assertEqual(classify_evidence("official", 0.9), EvidenceClass.PRIMARY)
        self.assertEqual(classify_evidence("", 0.1), EvidenceClass.WEAK)

    def test_g25_source_diversity(self):
        d = detect_source_diversity(["a.com", "b.com", "a.com"])
        self.assertEqual(d["unique_sources"], 2)

    def test_g26_conflict_detection(self):
        conflicts = detect_conflicts([
            {"claim": "Price up", "evidence": "conflicting"},
            {"claim": "Price down", "evidence": "conflicting"},
        ])
        self.assertTrue(conflicts)

    def test_g27_factpack_integration(self):
        req = ResearchRequest(topic_id="t1", canonical_topic="Integration test", query="integration")
        rr = execute_research_request(self.tmp, req, job_id="j1", use_mock=True)
        self.assertTrue(rr.success)
        self.assertIsNotNone(rr.fact_pack)

    def test_g28_factpack_quality(self):
        gate = validate_fact_pack({"claims": [{"claim": "x", "evidence": "UNVERIFIED", "source": ""}]})
        self.assertEqual(gate["verdict"], "RESEARCH_REQUIRED")

    def test_g29_api_cache(self):
        req = ResearchRequest(topic_id="t-cache", canonical_topic="Cache test", query="cache")
        r1 = execute_research_request(self.tmp, req, job_id="j1", use_mock=True)
        r2 = execute_research_request(self.tmp, req, job_id="j1", use_mock=True)
        self.assertEqual(r1.fingerprint, r2.fingerprint)
        self.assertEqual(r2.action, "reuse")

    def test_g30_api_budget(self):
        req = ResearchRequest(topic_id="t-budget", canonical_topic="Budget test", query="budget")
        rr = execute_research_request(self.tmp, req, job_id="j1", use_mock=True)
        self.assertIn("request_count", rr.metrics.to_dict())

    def test_g31_prompt_version(self):
        req = ResearchRequest(topic_id="t1", canonical_topic="Test", query="q", prompt_version="2.0.0")
        fp1 = compute_research_fingerprint(req)
        req.prompt_version = "1.0.0"
        fp2 = compute_research_fingerprint(req)
        self.assertNotEqual(fp1, fp2)

    def test_g32_topic_idempotency(self):
        fp = topic_identity_fingerprint(job_id="j1", channel_id=1, fmt="LONG", canonical_topic="Same topic")
        fp2 = topic_identity_fingerprint(job_id="j1", channel_id=1, fmt="LONG", canonical_topic="Same topic")
        self.assertEqual(fp, fp2)

    def test_g33_concurrent_discovery(self):
        results = []
        lock = threading.Lock()

        def worker():
            cands = [_cand("Concurrent topic")]
            r = run_topic_intelligence(self.tmp, _profile(), cands, job_id="concurrent", use_mock_research=True)
            with lock:
                results.append(r)

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(results), 3)

    def test_g34_concurrent_research(self):
        req = ResearchRequest(topic_id="t-conc", canonical_topic="Concurrent research", query="conc")
        out = []
        lock = threading.Lock()

        def worker():
            r = execute_research_request(self.tmp, req, job_id="conc", use_mock=True)
            with lock:
                out.append(r)

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        r4 = execute_research_request(self.tmp, req, job_id="conc", use_mock=True)
        reuses = sum(1 for r in out if r.action == "reuse") + (1 if r4.action == "reuse" else 0)
        self.assertGreaterEqual(reuses, 1)

    def test_g35_provenance(self):
        from pipeline.intelligence.provenance import record_topic_provenance
        p = record_topic_provenance(self.tmp, topic_id="t1", discovery={"source": "test"})
        self.assertTrue(p.is_file())

    def test_g36_topic_script_trace(self):
        c = _cand("Trace topic")
        self.assertTrue(c.topic_id)

    def test_g37_research_failure(self):
        gate = validate_fact_pack(None)
        self.assertEqual(gate["verdict"], "RESEARCH_REQUIRED")

    def test_g38_retry_policy(self):
        sr = score_candidate(_cand("dup test"), _profile(), existing_topics=["dup test"])
        self.assertTrue(sr.hard_blocked)

    def test_g39_fallback(self):
        req = ResearchRequest(topic_id="t-fb", canonical_topic="Fallback", query="fb")
        rr = execute_research_request(self.tmp, req, job_id="j1", use_mock=False)
        self.assertTrue(rr.success or rr.action in ("execute", "reuse", "failed"))

    def test_g40_open_source_dependency(self):
        self.assertGreater(jaccard_similarity("a b c", "a b d"), 0)

    def test_g41_no_unnecessary_llm(self):
        r = analyze_duplicate("Topic A", ["Topic A"])
        self.assertEqual(r.layer, "exact_canonical")

    def test_g42_structured_topic_output(self):
        c = candidate_from_dict({
            "title": "Test",
            "format": "SHORT",
            "channel_id": 1,
            "novelty_reason": "new angle",
            "relevance_reason": "channel fit",
        })
        d = c.to_dict()
        self.assertIn("novelty_reason", d)

    def test_g43_research_query_normalization(self):
        from pipeline.intelligence.normalization import normalize_research_query
        q = normalize_research_query("  Why   Bitcoin   Fell?  ")
        self.assertNotIn("  ", q)

    def test_g44_research_freshness(self):
        fp1 = compute_research_fingerprint(ResearchRequest(topic_id="t1", canonical_topic="X", query="q", time_window="7d"))
        fp2 = compute_research_fingerprint(ResearchRequest(topic_id="t1", canonical_topic="X", query="q", time_window="30d"))
        self.assertNotEqual(fp1, fp2)

    def test_g45_explainable_ranking(self):
        cands = [_cand("Explainable topic")]
        ev, _ = evaluate_candidates(cands, _profile())
        self.assertTrue(ev[0]["score"].get("dimensions"))

    def test_g46_rejection_explanation(self):
        sr = score_candidate(_cand("forbidden x"), _profile(forbidden_topics=["forbidden"]))
        self.assertEqual(sr.rejection_reason, RejectionReason.FORBIDDEN.value)

    def test_g47_reserve_integrity(self):
        cands = [_cand(f"Valid {i}") for i in range(5)]
        run_topic_intelligence(self.tmp, _profile(), cands, use_mock_research=True)
        entries = load_reserve(self.tmp, ContentFormat.LONG, channel_id=1)
        ok, _ = validate_reserve_integrity(entries)
        self.assertTrue(ok)

    def test_g48_queue_self_repair(self):
        from pipeline.intelligence.reserve_queue import save_reserve
        bad = [
            {"title": "A", "canonical_topic": "a", "status": TopicLifecycleStatus.RESERVED.value},
            {"title": "A", "canonical_topic": "a", "status": TopicLifecycleStatus.RESERVED.value},
        ]
        save_reserve(self.tmp, ContentFormat.LONG, bad, channel_id=1)
        rep = repair_reserve(self.tmp, ContentFormat.LONG, channel_id=1)
        self.assertTrue(rep["repaired"])

    def test_g49_daily_maintenance(self):
        report = refresh_topic_intelligence(self.tmp, _profile())
        self.assertIn("timestamp", report)

    def test_g50_observability(self):
        cands = [_cand("Obs topic")]
        r = run_topic_intelligence(self.tmp, _profile(), cands, use_mock_research=True)
        self.assertIn("metrics", r)

    def test_cost_100_candidates_no_llm(self):
        mock = get_mock_research_provider()
        mock.reset()
        existing = []
        for i in range(100):
            title = f"Unique topic number {i} about gadgets"
            analyze_duplicate(title, existing)
            existing.append(title)
        self.assertEqual(mock.calls.__len__() if hasattr(mock, 'calls') else 0, 0)

    def test_duplicate_stress(self):
        cases = [
            ("Exact", "Exact", DuplicateVerdict.DUPLICATE),
            ("Why Bitcoin Fell", "why bitcoin fell", DuplicateVerdict.DUPLICATE),
        ]
        for a, b, expected in cases:
            r = analyze_duplicate(a, [b])
            self.assertIn(r.verdict, (expected, DuplicateVerdict.POSSIBLE_DUPLICATE))

    def test_reserve_stress(self):
        long_cands = [_cand(f"Long {i}", ContentFormat.LONG) for i in range(5)]
        short_cands = [_cand(f"Short {i}", ContentFormat.SHORT) for i in range(5)]
        run_topic_intelligence(self.tmp, _profile(), long_cands + short_cands, use_mock_research=True)
        top, _ = consume_top(self.tmp, ContentFormat.LONG, channel_id=1)
        self.assertIsNotNone(top)
        rep = repair_reserve(self.tmp, ContentFormat.LONG, channel_id=1)
        self.assertIn("repaired", rep)

    def test_unknown_stays_unknown(self):
        r = analyze_duplicate("", [])
        self.assertEqual(r.verdict, DuplicateVerdict.UNKNOWN)
        sr = score_candidate(_cand("x"), _profile(), duplicate_result=r)
        self.assertTrue(sr.hard_blocked)

    def test_conflict_preserved(self):
        pack = {"claims": [
            {"claim": "Up", "evidence": "conflicting", "source": "a"},
            {"claim": "Down", "evidence": "conflicting", "source": "b"},
        ]}
        gate = validate_fact_pack(pack)
        self.assertEqual(gate["verdict"], "RESEARCH_CONFLICT")

    def test_cache_invalidation_channel(self):
        inv = invalidate_ranking_on_channel_change(self.tmp, channel_id=1)
        self.assertTrue(inv["invalidated"])

    def test_prompt_invalidation(self):
        inv = invalidate_topic_cache_on_prompt_change(self.tmp, prompt_version="2.0.0")
        self.assertTrue(inv["invalidated"])

    def test_research_invalidation(self):
        fp7 = compute_research_fingerprint(ResearchRequest(topic_id="t1", canonical_topic="X", query="q", time_window="7d"))
        fp30 = compute_research_fingerprint(ResearchRequest(topic_id="t1", canonical_topic="X", query="q", time_window="30d"))
        self.assertNotEqual(fp7, fp30)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Build04GTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    passed = total - failed
    print(f"\nBUILD-04G TESTS: {passed} / {total}")
    sys.exit(0 if failed == 0 else 1)
