#!/usr/bin/env python3
"""AMP-002 RV-008 — Channel DNA + niche relevance re-verification."""
from __future__ import annotations

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

from pipeline.channel_dna import from_channel_row, infer_style_family, validate_topic_against_dna
from pipeline.intelligence.cache_registry import bump_channel_version, get_channel_version, is_ranking_stale, ranking_cache_key
from pipeline.intelligence.candidates import candidate_from_dict
from pipeline.intelligence.contracts import ContentFormat
from pipeline.intelligence.duplicate import analyze_duplicate
from pipeline.intelligence.normalization import canonical_topic_key, normalize_topic_text
from pipeline.intelligence.orchestrator import run_topic_intelligence
from pipeline.intelligence.scoring import channel_profile_from_row, score_candidate


def _ch(cid: int, niche: str) -> dict:
    return {"id": cid, "niche": niche, "youtube_name": f"ch{cid}"}


def _score(channel: dict, title: str, *, evidence_count: int = 2, fmt: str = "LONG"):
    profile = channel_profile_from_row(channel)
    c = candidate_from_dict({
        "title": title,
        "canonical_topic": title,
        "format": fmt,
        "channel_id": channel["id"],
        "niche": channel["niche"],
    })
    dup = analyze_duplicate(title, [])
    return score_candidate(c, profile, duplicate_result=dup, evidence_count=evidence_count)


class RV008NicheClassificationTests(unittest.TestCase):
    def test_tech_not_classified_as_history(self):
        self.assertEqual(infer_style_family("tech"), "gadget")
        self.assertNotEqual(infer_style_family("tech"), "history")

    def test_history_niche(self):
        self.assertEqual(infer_style_family("ancient history"), "history")

    def test_finance_niche(self):
        self.assertEqual(infer_style_family("finance"), "finance")

    def test_science_niche(self):
        self.assertEqual(infer_style_family("science"), "science")

    def test_07_unknown_empty_niche_defaults_general(self):
        self.assertEqual(infer_style_family(""), "general")
        self.assertEqual(infer_style_family("   "), "general")
        dna = from_channel_row({"id": 1, "niche": ""})
        self.assertEqual(dna.style_family, "general")

    def test_08_invalid_niche_not_forced_to_history(self):
        dna = from_channel_row({"id": 2, "niche": "xyz_unknown_niche_999"})
        self.assertNotEqual(dna.style_family, "history")
        self.assertNotEqual(dna.style_family, "finance")
        self.assertIn(dna.style_family, ("general", "mystery", "gadget"))


class RV008RelevanceScoreTests(unittest.TestCase):
    def test_01_tech_relevant_scores_high(self):
        sr = _score(_ch(801, "tech"), "New smartphone processor architecture")
        self.assertGreater(sr.dimensions.get("CHANNEL_RELEVANCE", 0), 0.5)
        self.assertFalse(sr.hard_blocked)

    def test_02_tech_irrelevant_scores_lower_than_relevant(self):
        rel = _score(_ch(802, "tech"), "New smartphone processor architecture")
        irr = _score(_ch(802, "tech"), "Ancient Roman political history")
        self.assertGreater(rel.dimensions["CHANNEL_RELEVANCE"], irr.dimensions["CHANNEL_RELEVANCE"])

    def test_03_history_relevant_scores_high(self):
        sr = _score(_ch(803, "ancient history"), "Causes of the French Revolution in ancient civilization")
        self.assertGreater(sr.dimensions["CHANNEL_RELEVANCE"], 0.5)

    def test_04_history_irrelevant_scores_lower(self):
        rel = _score(_ch(804, "ancient history"), "Causes of the French Revolution")
        irr = _score(_ch(804, "ancient history"), "Latest GPU benchmark comparison 2026")
        self.assertGreater(rel.dimensions["CHANNEL_RELEVANCE"], irr.dimensions["CHANNEL_RELEVANCE"])

    def test_05_finance_relevant(self):
        sr = _score(_ch(805, "finance"), "Why interest rates affect stock markets")
        self.assertGreater(sr.dimensions["CHANNEL_RELEVANCE"], 0.5)

    def test_06_science_relevant(self):
        sr = _score(_ch(806, "science"), "How black holes form in distant galaxies")
        self.assertGreater(sr.dimensions["CHANNEL_RELEVANCE"], 0.4)

    def test_12_keyword_trap_semantic_mismatch(self):
        trap = _score(_ch(812, "tech"), "The technology of ancient Roman weapons")
        real = _score(_ch(812, "tech"), "New smartphone processor architecture")
        self.assertGreater(real.dimensions["CHANNEL_RELEVANCE"], trap.dimensions["CHANNEL_RELEVANCE"])


class RV008CrossChannelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_09_cross_channel_isolation(self):
        results: dict[int, dict] = {}

        def _run(cid: int, niche: str, title: str):
            work = self.tmp / f"ch{cid}"
            work.mkdir()
            profile = channel_profile_from_row(_ch(cid, niche))
            out = run_topic_intelligence(
                work, profile,
                [{"title": title, "format": "LONG", "channel_id": cid, "niche": niche}],
                use_mock_research=True,
            )
            results[cid] = out

        threads = [
            threading.Thread(target=_run, args=(901, "tech", "RV008 tech smartphone chip")),
            threading.Thread(target=_run, args=(902, "ancient history", "RV008 French Revolution causes")),
            threading.Thread(target=_run, args=(903, "finance", "RV008 stock market interest rates")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(results[901]["evaluated"][0]["candidate"]["channel_id"], 901)
        self.assertEqual(results[902]["evaluated"][0]["candidate"]["channel_id"], 902)
        self.assertEqual(results[903]["evaluated"][0]["candidate"]["channel_id"], 903)

    def test_10_same_candidate_different_channels_different_scores(self):
        title = "RV008 borderline history of artificial intelligence"
        tech = _score(_ch(910, "tech"), title)
        hist = _score(_ch(911, "ancient history"), title)
        self.assertNotEqual(tech.dimensions["CHANNEL_RELEVANCE"], hist.dimensions["CHANNEL_RELEVANCE"])


class RV008MultilingualTests(unittest.TestCase):
    def test_11_multilingual_preserves_identity(self):
        bn = normalize_topic_text("কেন Bitcoin পড়ে গেল?")
        self.assertIn("bitcoin", bn)
        key_en = canonical_topic_key("Why did Bitcoin fall today")
        key_bn = canonical_topic_key("কেন Bitcoin পড়ে গেল")
        self.assertIn("bitcoin", key_en)
        self.assertIn("bitcoin", key_bn)


class RV008CacheAndDNAChangeTests(unittest.TestCase):
    def test_13_channel_dna_change_affects_score(self):
        ch = _ch(920, "tech")
        title = "Ancient Roman political history"
        before = _score(ch, title)
        ch_hist = _ch(920, "ancient history")
        after = _score(ch_hist, title)
        self.assertGreater(after.dimensions["CHANNEL_RELEVANCE"], before.dimensions["CHANNEL_RELEVANCE"])

    def test_14_cache_invalidation_on_channel_bump(self):
        cid = 921
        v0 = get_channel_version(cid)
        bump_channel_version(cid, reason="niche_change")
        v1 = get_channel_version(cid)
        self.assertTrue(is_ranking_stale(cid, v0))
        self.assertFalse(is_ranking_stale(cid, v1))
        self.assertNotEqual(ranking_cache_key(cid, "LONG"), f"rank-{cid}-LONG-v{v0}")


class RV008ProductionPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_15_production_integration_via_orchestrator(self):
        profile = channel_profile_from_row(_ch(930, "tech"))
        self.assertEqual(profile.niche, "tech")
        dna = from_channel_row(_ch(930, "tech"))
        self.assertEqual(dna.style_family, "gadget")
        result = run_topic_intelligence(
            self.tmp,
            profile,
            [{"title": "RV008 production tech chip launch", "format": "LONG", "channel_id": 930, "niche": "tech"}],
            use_mock_research=True,
        )
        self.assertGreater(len(result["evaluated"]), 0)
        self.assertIn("ranked_long", result)

    def test_long_short_same_dna(self):
        profile = channel_profile_from_row(_ch(931, "science"))
        long_sr = _score(_ch(931, "science"), "How black holes form", fmt="LONG")
        short_sr = _score(_ch(931, "science"), "How black holes form", fmt="SHORT")
        self.assertEqual(long_sr.dimensions["CHANNEL_RELEVANCE"], short_sr.dimensions["CHANNEL_RELEVANCE"])

    def test_history_blocks_gadget_topic(self):
        dna = from_channel_row(_ch(932, "ancient history"))
        gate = validate_topic_against_dna("iPhone 16 Pro Max unboxing review", dna)
        self.assertFalse(gate["passed"])
        issues = " ".join(gate.get("issues") or [])
        self.assertTrue(
            "forbidden_topic" in issues or "gadget_topic_on_nongadget" in issues,
            f"expected history channel to block gadget topic, got {issues!r}",
        )


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\nAMP-002 RV-008: {passed} / {result.testsRun}")
    sys.exit(0 if result.wasSuccessful() else 1)
