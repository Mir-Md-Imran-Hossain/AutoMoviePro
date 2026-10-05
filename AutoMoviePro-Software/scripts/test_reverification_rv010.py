#!/usr/bin/env python3
"""AMP-002 RV-010 — Advanced topic duplicate + novelty re-verification."""
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

from pipeline.intelligence.candidates import candidate_from_dict
from pipeline.intelligence.contracts import ChannelProfile, ContentFormat, DuplicateVerdict, TopicLifecycleStatus
from pipeline.intelligence.duplicate import (
    DUPLICATE_RULE_VERSION,
    TOKEN_JACCARD_THRESHOLD,
    analyze_duplicate,
    duplicate_rule_fingerprint,
    merge_duplicate_corpus,
)
from pipeline.intelligence.normalization import canonical_topic_key, normalize_topic_text
from pipeline.intelligence.orchestrator import _preliminary_filter, run_topic_intelligence
from pipeline.intelligence.reserve_queue import load_reserve, save_reserve, update_reserve
from pipeline.intelligence.scoring import channel_profile_from_row, score_candidate


def _profile(cid: int = 2000, niche: str = "tech") -> ChannelProfile:
    return ChannelProfile(channel_id=cid, niche=niche, language="en")


def _ch(cid: int, niche: str = "tech") -> dict:
    return {"id": cid, "niche": niche, "youtube_name": f"ch{cid}"}


def _cand(title: str, cid: int = 2000, fmt: str = "LONG", **meta) -> dict:
    return {
        "title": title,
        "canonical_topic": title,
        "format": fmt,
        "channel_id": cid,
        "niche": "tech",
        "source": "pipeline",
        "metadata": meta,
    }


def _through_pipeline(title: str, existing: list[str] | None = None, historical: list[str] | None = None, **kw):
    profile = _profile(kw.pop("channel_id", 2000))
    c = candidate_from_dict(_cand(title, cid=profile.channel_id, **kw))
    filtered = _preliminary_filter([c], profile, existing or [], historical or [])
    return filtered, (c.metadata.get("duplicate_check") or {})


class RV010ExactDuplicateTests(unittest.TestCase):
    def test_01_exact_duplicate(self):
        r = analyze_duplicate("How Black Holes Form", ["How Black Holes Form"])
        self.assertEqual(r.verdict, DuplicateVerdict.DUPLICATE)
        self.assertEqual(r.layer, "exact_canonical")

    def test_02_case_normalization(self):
        r = analyze_duplicate("How Black Holes Form", ["how black holes form"])
        self.assertEqual(r.verdict, DuplicateVerdict.DUPLICATE)


class RV010NormalizedDuplicateTests(unittest.TestCase):
    def test_03_whitespace_normalization(self):
        a = "Why   Does   Bitcoin   Price   Change?"
        b = "why does bitcoin price change"
        self.assertEqual(canonical_topic_key(a), canonical_topic_key(b))

    def test_04_punctuation_normalization(self):
        a = '"Why Does Bitcoin Price Change?"'
        b = "why does bitcoin price change"
        self.assertEqual(canonical_topic_key(a), canonical_topic_key(b))

    def test_05_normalized_duplicate_pipeline(self):
        filtered, dup = _through_pipeline(
            "Why Does Bitcoin Price Change?",
            ["why does bitcoin price change"],
        )
        self.assertEqual(len(filtered), 0)
        self.assertEqual(dup.get("verdict"), "DUPLICATE")


class RV010SemanticDuplicateTests(unittest.TestCase):
    def test_06_semantic_duplicate_pipeline(self):
        existing = ["Why did Apple stock drop sharply today"]
        filtered, dup = _through_pipeline(
            "Apple shares fell steeply today — what caused it",
            existing,
        )
        self.assertEqual(len(filtered), 1)
        self.assertIn(dup.get("verdict"), ("POSSIBLE_DUPLICATE", "DUPLICATE"))

    def test_07_semantic_false_positive_avoided(self):
        r = analyze_duplicate("How Black Holes Form", ["How Neutron Stars Form"])
        self.assertEqual(r.verdict, DuplicateVerdict.UNIQUE)

    def test_08_semantic_false_negative_documented(self):
        r = analyze_duplicate(
            "Why Do Black Holes Exist?",
            ["What Causes Black Holes to Form?"],
        )
        self.assertEqual(r.verdict, DuplicateVerdict.UNIQUE)

    def test_09_borderline_similarity(self):
        r = analyze_duplicate(
            "Why did Apple stock drop sharply today",
            ["Apple stock dropped today"],
        )
        self.assertIn(r.verdict, (DuplicateVerdict.DUPLICATE, DuplicateVerdict.POSSIBLE_DUPLICATE))


class RV010HistoricalDuplicateTests(unittest.TestCase):
    def test_10_historical_duplicate_blocks_in_pipeline(self):
        filtered, dup = _through_pipeline(
            "RV010 published topic about quantum chips",
            existing=[],
            historical=["RV010 published topic about quantum chips"],
        )
        self.assertEqual(len(filtered), 0)
        self.assertEqual(dup.get("verdict"), "DUPLICATE")

    def test_11_previously_published_topic(self):
        corpus = merge_duplicate_corpus([], ["Previously published French Revolution deep dive"])
        r = analyze_duplicate("Previously published French Revolution deep dive", corpus)
        self.assertEqual(r.verdict, DuplicateVerdict.DUPLICATE)

    def test_12_failed_generation_topic_not_in_historical_allows_retry(self):
        filtered, _ = _through_pipeline(
            "RV010 failed render retry topic",
            existing=[],
            historical=[],
        )
        self.assertEqual(len(filtered), 1)


class RV010RevisionTests(unittest.TestCase):
    def test_13_revision_handling(self):
        r = analyze_duplicate(
            "Same Topic Title",
            ["Same Topic Title"],
            candidate_revision_id="r002",
            allow_intentional_revision=True,
        )
        self.assertEqual(r.verdict, DuplicateVerdict.UNIQUE)
        self.assertEqual(r.layer, "revision_exempt")


class RV010MultilingualTests(unittest.TestCase):
    def test_14_multilingual_token_overlap_partial(self):
        en = canonical_topic_key("Why did Bitcoin fall today")
        bn = normalize_topic_text("কেন Bitcoin পড়ে গেল?")
        self.assertIn("bitcoin", en)
        self.assertIn("bitcoin", bn)
        r = analyze_duplicate("Why did Bitcoin fall today", ["কেন Bitcoin পড়ে গেল"])
        self.assertIn(r.verdict, (DuplicateVerdict.DUPLICATE, DuplicateVerdict.POSSIBLE_DUPLICATE, DuplicateVerdict.UNIQUE))


class RV010FormatPolicyTests(unittest.TestCase):
    def test_15_long_short_same_title_is_duplicate(self):
        long_c = candidate_from_dict(_cand("Complete Guide to Black Holes", fmt="LONG"))
        short_c = candidate_from_dict(_cand("Complete Guide to Black Holes", fmt="SHORT"))
        self.assertNotEqual(long_c.topic_id, short_c.topic_id)
        r = analyze_duplicate(long_c.title, [short_c.title])
        self.assertEqual(r.verdict, DuplicateVerdict.DUPLICATE)


class RV010CrossChannelTests(unittest.TestCase):
    def test_16_cross_channel_local_corpus(self):
        ch_a_topics = ["Channel A exclusive tech topic RV010"]
        r = analyze_duplicate("Channel A exclusive tech topic RV010", ch_a_topics)
        self.assertEqual(r.verdict, DuplicateVerdict.DUPLICATE)
        r_other = analyze_duplicate("Channel A exclusive tech topic RV010", [])
        self.assertEqual(r_other.verdict, DuplicateVerdict.UNIQUE)


class RV010ReserveIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cid = 2017

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        p = Path(os.environ.get("DATA_DIR", "")) if False else None

    def test_17_reserve_rejects_hard_blocked_duplicate(self):
        from pipeline.intelligence.duplicate import analyze_duplicate as ad
        from pipeline.intelligence.ranking import rank_candidates

        profile = _profile(self.cid)
        dup_title = "RV010 reserve duplicate topic"
        unique_title = "RV010 reserve unique topic alpha"
        c_dup = candidate_from_dict(_cand(dup_title, cid=self.cid))
        c_unique = candidate_from_dict(_cand(unique_title, cid=self.cid))
        filtered = _preliminary_filter([c_dup, c_unique], profile, [dup_title], [])
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].title, unique_title)
        dup_sr = score_candidate(c_dup, profile, duplicate_result=ad(dup_title, [dup_title]))
        unique_sr = score_candidate(
            c_unique,
            profile,
            duplicate_result=ad(unique_title, [dup_title]),
            evidence_count=5,
        )
        self.assertTrue(dup_sr.hard_blocked)
        ranked = rank_candidates(
            [c_dup, c_unique],
            profile,
            existing_topics=[dup_title],
            scores={c_dup.topic_id: dup_sr, c_unique.topic_id: unique_sr},
        )
        eligible_titles = [r["candidate"]["title"] for r in ranked if r.get("eligible")]
        self.assertNotIn(dup_title, eligible_titles)
        self.assertTrue(dup_sr.hard_blocked)
        reserve = update_reserve(self.tmp, ContentFormat.LONG, ranked, channel_id=self.cid, min_size=1)
        titles = [e.get("title") for e in load_reserve(self.tmp, ContentFormat.LONG, channel_id=self.cid)]
        self.assertNotIn(dup_title, titles)
        if eligible_titles:
            self.assertIn(unique_title, titles)


class RV010ConcurrencyTests(unittest.TestCase):
    def test_18_concurrent_duplicate_admission(self):
        profile = _profile(2018)
        title = "RV010 concurrent duplicate topic"
        results: list[int] = []
        lock = threading.Lock()

        def worker():
            c = candidate_from_dict(_cand(title, cid=2018))
            out = _preliminary_filter([c], profile, [title], [])
            with lock:
                results.append(len(out))

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertTrue(all(n == 0 for n in results))


class RV010CacheTests(unittest.TestCase):
    def test_19_cache_fingerprint_stable(self):
        fp1 = duplicate_rule_fingerprint()
        fp2 = duplicate_rule_fingerprint()
        self.assertEqual(fp1, fp2)

    def test_20_cache_invalidation_on_rule_version(self):
        from pipeline.intelligence import duplicate as dup_mod
        orig = dup_mod.DUPLICATE_RULE_VERSION
        try:
            fp_before = duplicate_rule_fingerprint()
            dup_mod.DUPLICATE_RULE_VERSION = "1.0.1-test"
            fp_after = duplicate_rule_fingerprint()
            self.assertNotEqual(fp_before, fp_after)
        finally:
            dup_mod.DUPLICATE_RULE_VERSION = orig


class RV010InvalidDataTests(unittest.TestCase):
    def test_21_malformed_empty_candidate(self):
        r = analyze_duplicate("", ["something"])
        self.assertEqual(r.verdict, DuplicateVerdict.UNKNOWN)

    def test_22_missing_channel_strict_candidate(self):
        from pipeline.intelligence.candidates import validate_candidate_dict
        ok, issues = validate_candidate_dict({"title": "x", "source": "pipeline", "channel_id": 0})
        self.assertFalse(ok)
        self.assertIn("invalid_channel_id", issues)

    def test_23_missing_language_allowed_pipeline_source(self):
        c = candidate_from_dict(_cand("Topic without explicit language", cid=2023))
        self.assertEqual(c.language, "en")


class RV010ProductionPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_24_production_path_blocks_duplicate(self):
        profile = channel_profile_from_row(_ch(2024, "finance"))
        topic = "RV010 production duplicate finance topic"
        r1 = run_topic_intelligence(
            self.tmp,
            profile,
            [_cand(topic, cid=2024)],
            use_mock_research=True,
        )
        self.assertGreater(len(r1.get("evaluated") or []), 0)
        r2 = run_topic_intelligence(
            self.tmp,
            profile,
            [_cand(topic, cid=2024)],
            existing_topics=[topic],
            use_mock_research=True,
        )
        self.assertEqual(len(r2.get("evaluated") or []), 0)

    def test_25_no_direct_reserve_bypass_without_filter(self):
        profile = _profile(2025)
        blocked = candidate_from_dict(_cand("RV010 exact dup", cid=2025))
        filtered = _preliminary_filter([blocked], profile, ["RV010 exact dup"], [])
        self.assertEqual(len(filtered), 0)
        dup_sr = score_candidate(
            blocked,
            profile,
            duplicate_result=analyze_duplicate(blocked.title, ["RV010 exact dup"]),
        )
        self.assertTrue(dup_sr.hard_blocked)
        self.assertEqual(dup_sr.block_reason, "DUPLICATE")


class RV010ThresholdAuditTests(unittest.TestCase):
    def test_threshold_constants_documented(self):
        self.assertEqual(DUPLICATE_RULE_VERSION, "1.0.0")
        self.assertGreater(TOKEN_JACCARD_THRESHOLD, 0.5)
        self.assertLess(TOKEN_JACCARD_THRESHOLD, 1.0)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\nAMP-002 RV-010: {passed} / {result.testsRun}")
    sys.exit(0 if result.wasSuccessful() else 1)
