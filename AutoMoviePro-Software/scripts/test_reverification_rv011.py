#!/usr/bin/env python3
"""AMP-002 RV-011 — Trend + Freshness + SEO + Content-Gap re-verification."""
from __future__ import annotations

import math
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.intelligence.candidates import candidate_from_dict
from pipeline.intelligence.contracts import ChannelProfile, ContentFormat, TrendClass
from pipeline.intelligence.orchestrator import run_topic_intelligence
from pipeline.intelligence.ranking import rank_candidates
from pipeline.intelligence.scoring import DIMENSION_WEIGHTS, score_candidate
from pipeline.intelligence.trend import (
    SCORING_SIGNAL_VERSION,
    SEO_HEURISTIC_SOURCE,
    TREND_SIGNAL_SOURCE,
    apply_trend_decay,
    classify_trend_from_signals,
    content_gap_score,
    freshness_from_timestamps,
    normalize_score_component,
    resolve_freshness_score,
    scoring_rule_fingerprint,
    seo_heuristic_score,
)


def _profile(cid: int = 3000, niche: str = "tech") -> ChannelProfile:
    return ChannelProfile(channel_id=cid, niche=niche, language="en")


def _cand(title: str, cid: int = 3000, fmt: str = "LONG", **meta) -> dict:
    return {
        "title": title,
        "canonical_topic": title,
        "format": fmt,
        "channel_id": cid,
        "niche": "tech",
        "source": "pipeline",
        "metadata": meta,
    }


def _score(title: str, cid: int = 3000, **meta):
    gap = float(meta.pop("gap", 0.7))
    evidence = int(meta.pop("evidence_count", 3))
    c = candidate_from_dict(_cand(title, cid=cid, **meta))
    return score_candidate(c, _profile(cid), evidence_count=evidence, content_gap_score=gap)


class RV011ScoreStructureTests(unittest.TestCase):
    def test_01_score_structure(self):
        sr = _score("RV011 tech smartphone processor launch 2026")
        self.assertIn("CHANNEL_RELEVANCE", sr.dimensions)
        self.assertIn("TREND_SIGNAL", sr.dimensions)
        self.assertIn("RECENCY", sr.dimensions)
        self.assertIn("SEO_HEURISTIC_SCORE", sr.dimensions)
        self.assertIn("CONTENT_GAP", sr.dimensions)
        self.assertAlmostEqual(sum(DIMENSION_WEIGHTS.values()), 1.0, places=4)


class RV011FreshnessTests(unittest.TestCase):
    def test_02_freshness_ordering(self):
        now = time.time()
        fresh = resolve_freshness_score({"discovered_at": now}, now=now)
        old = resolve_freshness_score({"discovered_at": now - 86400 * 60}, now=now)
        self.assertGreater(fresh, old)

    def test_03_stale_timestamp(self):
        now = time.time()
        stale = resolve_freshness_score({"discovered_at": now - 86400 * 120}, now=now)
        self.assertLess(stale, 0.3)

    def test_04_missing_timestamp_default(self):
        self.assertEqual(resolve_freshness_score({}), 0.5)

    def test_explicit_freshness_overrides_timestamp(self):
        now = time.time()
        v = resolve_freshness_score({"freshness": 0.9, "discovered_at": now - 999999}, now=now)
        self.assertEqual(v, 0.9)


class RV011TrendTests(unittest.TestCase):
    def test_05_trend_signal_with_evidence(self):
        tc = classify_trend_from_signals(trend_score=0.85, trend_evidence="live_feed", source_count=2)
        self.assertEqual(tc, TrendClass.TRENDING)

    def test_06_trend_ordering(self):
        base = {"trend_evidence": "live_feed", "source_count": 3, "evidence_count": 3}
        a = _score("RV011 trending topic alpha", trend_score=0.9, **base)
        b = _score("RV011 trending topic beta", trend_score=0.5, **base)
        c = _score("RV011 trending topic gamma", trend_score=0.1, **base)
        self.assertGreater(a.dimensions["TREND_SIGNAL"], b.dimensions["TREND_SIGNAL"])
        self.assertGreater(b.dimensions["TREND_SIGNAL"], c.dimensions["TREND_SIGNAL"])

    def test_15_missing_trend_data(self):
        tc = classify_trend_from_signals()
        self.assertEqual(tc, TrendClass.TREND_SIGNAL_UNAVAILABLE)
        sr = _score("RV011 no trend metadata topic")
        self.assertLessEqual(sr.dimensions["TREND_SIGNAL"], 0.35)


class RV011SEOTests(unittest.TestCase):
    def test_07_seo_signal(self):
        s = seo_heuristic_score("Best Budget tech Smartphone Camera Review 2026", niche="tech")
        self.assertGreater(s, 0.0)
        self.assertLessEqual(s, 1.0)

    def test_08_seo_ordering(self):
        c_strong = candidate_from_dict(_cand("Complete tech Smartphone Buying Guide 2026 for tech audience"))
        c_weak = candidate_from_dict(_cand("Stuff"))
        sr_s = score_candidate(c_strong, _profile(niche="tech"), evidence_count=3, content_gap_score=0.7)
        sr_w = score_candidate(c_weak, _profile(niche="tech"), evidence_count=3, content_gap_score=0.7)
        self.assertGreater(sr_s.dimensions["SEO_HEURISTIC_SCORE"], sr_w.dimensions["SEO_HEURISTIC_SCORE"])

    def test_16_missing_seo_still_scores(self):
        sr = score_candidate(
            candidate_from_dict(_cand("x")),
            _profile(),
            evidence_count=3,
            content_gap_score=0.7,
        )
        self.assertGreaterEqual(sr.dimensions["SEO_HEURISTIC_SCORE"], 0.0)


class RV011ContentGapTests(unittest.TestCase):
    def test_09_content_gap_novel(self):
        gap = content_gap_score("How Black Holes Affect Nearby Stars", ["How Roman Empire Fell"])
        self.assertGreater(gap, 0.5)

    def test_10_content_gap_duplicate_case(self):
        gap = content_gap_score("How Black Holes Form", ["How Black Holes Form"])
        self.assertLessEqual(gap, 0.1)

    def test_11_content_gap_related_not_duplicate(self):
        gap_dup = content_gap_score("How Black Holes Form", ["How Black Holes Form"])
        gap_related = content_gap_score("How Black Holes Affect Nearby Stars", ["How Black Holes Form"])
        self.assertGreater(gap_related, gap_dup)

    def test_17_missing_gap_data_defaults(self):
        gap = content_gap_score("Brand new unique RV011 topic", [])
        self.assertEqual(gap, 0.7)


class RV011NormalizationTests(unittest.TestCase):
    def test_12_score_normalization(self):
        self.assertEqual(normalize_score_component(1.5), 1.0)
        self.assertEqual(normalize_score_component(-0.2), 0.0)
        self.assertEqual(normalize_score_component(None, default=0.4), 0.4)

    def test_13_invalid_numeric_input(self):
        self.assertEqual(normalize_score_component(float("nan"), default=0.5), 0.5)
        self.assertEqual(normalize_score_component(float("inf"), default=0.3), 0.3)


class RV011WeightInfluenceTests(unittest.TestCase):
    def test_14_weight_influence(self):
        low_trend = _score("RV011 weight test", trend_score=0.1, trend_evidence="live", source_count=2)
        high_trend = _score("RV011 weight test", trend_score=0.95, trend_evidence="live", source_count=2)
        delta = high_trend.total_score - low_trend.total_score
        expected_min = (0.95 - 0.35) * DIMENSION_WEIGHTS["TREND_SIGNAL"] * 0.5
        self.assertGreater(delta, 0)
        self.assertLess(delta, 0.3)


class RV011DeterminismTests(unittest.TestCase):
    def test_18_deterministic_ranking(self):
        c1 = candidate_from_dict(_cand("RV011 rank topic A", metadata={"trend_score": 0.9, "trend_evidence": "live", "source_count": 2}))
        c2 = candidate_from_dict(_cand("RV011 rank topic B", metadata={"trend_score": 0.4, "trend_evidence": "live", "source_count": 2}))
        profile = _profile()
        scores = {
            c1.topic_id: score_candidate(c1, profile, evidence_count=3, content_gap_score=0.8),
            c2.topic_id: score_candidate(c2, profile, evidence_count=3, content_gap_score=0.8),
        }
        r1 = rank_candidates([c1, c2], profile, scores=scores)
        r2 = rank_candidates([c1, c2], profile, scores=scores)
        self.assertEqual([x["candidate"]["title"] for x in r1], [x["candidate"]["title"] for x in r2])

    def test_19_daily_reranking_signal_change(self):
        decayed = apply_trend_decay(TrendClass.TRENDING, age_days=21)
        self.assertEqual(decayed, TrendClass.LOW_RECENCY)
        now = time.time()
        fresh_rank = resolve_freshness_score({"discovered_at": now}, now=now)
        stale_rank = resolve_freshness_score({"discovered_at": now - 86400 * 30}, now=now)
        self.assertGreater(fresh_rank, stale_rank)


class RV011FormatTests(unittest.TestCase):
    def test_20_long_short_format_fit(self):
        long_c = candidate_from_dict(_cand("RV011 format topic", fmt="LONG"))
        short_c = candidate_from_dict(_cand("RV011 format topic", fmt="SHORT"))
        profile = _profile()
        sl = score_candidate(long_c, profile, evidence_count=3, content_gap_score=0.7)
        ss = score_candidate(short_c, profile, evidence_count=3, content_gap_score=0.7)
        self.assertEqual(sl.dimensions["FORMAT_FIT"], 0.85)
        self.assertEqual(ss.dimensions["FORMAT_FIT"], 0.9)
        self.assertNotEqual(long_c.topic_id, short_c.topic_id)


class RV011CacheTests(unittest.TestCase):
    def test_21_cache_fingerprint_stable(self):
        self.assertEqual(scoring_rule_fingerprint(), scoring_rule_fingerprint())

    def test_22_cache_invalidation_on_version(self):
        from pipeline.intelligence import trend as trend_mod
        orig = trend_mod.SCORING_SIGNAL_VERSION
        try:
            fp1 = scoring_rule_fingerprint()
            trend_mod.SCORING_SIGNAL_VERSION = "1.0.1-test"
            fp2 = scoring_rule_fingerprint()
            self.assertNotEqual(fp1, fp2)
        finally:
            trend_mod.SCORING_SIGNAL_VERSION = orig


class RV011ConcurrencyTests(unittest.TestCase):
    def test_23_concurrency(self):
        profile = _profile(3023)
        results: list[float] = []
        lock = threading.Lock()

        def worker(i: int):
            c = candidate_from_dict(_cand(f"RV011 concurrent topic {i}", cid=3023, trend_score=0.7, trend_evidence="live", source_count=2))
            sr = score_candidate(c, profile, evidence_count=3, content_gap_score=0.7)
            with lock:
                results.append(sr.total_score)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(results), 20)
        self.assertTrue(all(0 <= s <= 1.0 for s in results))


class RV011ProductionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_24_production_integration(self):
        profile = _profile(3024)
        meta = {"trend_score": 0.8, "trend_evidence": "live", "source_count": 2, "freshness": 0.9}
        result = run_topic_intelligence(
            self.tmp,
            profile,
            [_cand("RV011 production scoring integration topic", cid=3024, **meta)],
            use_mock_research=True,
        )
        ev = result["evaluated"][0]
        dims = ev["score"]["dimensions"]
        self.assertIn("TREND_SIGNAL", dims)
        self.assertIn("SEO_HEURISTIC_SCORE", dims)
        self.assertIn("CONTENT_GAP", dims)
        self.assertIn(ev["candidate"]["topic_id"], result["research"])

    def test_25_research_order_enforcement(self):
        profile = _profile(3025)
        result = run_topic_intelligence(
            self.tmp,
            profile,
            [_cand("RV011 research order topic", cid=3025, trend_score=0.7, trend_evidence="live", source_count=2)],
            use_mock_research=True,
        )
        tid = result["evaluated"][0]["candidate"]["topic_id"]
        self.assertIn(tid, result["research"])
        self.assertEqual(result["research"][tid].get("gate", {}).get("verdict"), "PASS")
        self.assertFalse(result["evaluated"][0]["score"].get("hard_blocked"))


class RV011HonestLabelTests(unittest.TestCase):
    def test_trend_not_external_without_evidence(self):
        self.assertEqual(TREND_SIGNAL_SOURCE, "metadata_heuristic")
        self.assertEqual(SEO_HEURISTIC_SOURCE, "local_heuristic_v1")

    def test_trend_decay(self):
        decayed = apply_trend_decay(TrendClass.TRENDING, age_days=20)
        self.assertEqual(decayed, TrendClass.LOW_RECENCY)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\nAMP-002 RV-011: {passed} / {result.testsRun}")
    sys.exit(0 if result.wasSuccessful() else 1)
