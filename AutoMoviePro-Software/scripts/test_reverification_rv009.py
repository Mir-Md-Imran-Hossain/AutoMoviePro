#!/usr/bin/env python3
"""AMP-002 RV-009 — Topic Discovery deep runtime re-verification."""
from __future__ import annotations

import json
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

from pipeline.intelligence.candidates import candidate_from_dict, make_topic_id, validate_candidate_dict
from pipeline.intelligence.contracts import ChannelProfile, ContentFormat
from pipeline.intelligence.discovery import (
    DEFAULT_DISCOVERY_MAX_AGE_SEC,
    DISCOVERY_EXTERNAL_API,
    DISCOVERY_PROVIDER,
    DISCOVERY_SOURCE_TYPE,
    DiscoveryEmptyError,
    DiscoveryUnavailableError,
    discover_topic_candidates,
    discovery_input_fingerprint,
    is_discovery_stale,
    load_discovery_artifact,
    save_discovery_artifact,
)
from pipeline.intelligence.duplicate import analyze_duplicate
from pipeline.intelligence.normalization import canonical_topic_key, normalize_topic_text
from pipeline.intelligence.orchestrator import run_topic_intelligence
from pipeline.intelligence.scoring import channel_profile_from_row, score_candidate


def _profile(cid: int, niche: str, **kw) -> ChannelProfile:
    return ChannelProfile(
        channel_id=cid,
        niche=niche,
        sub_niche=kw.pop("sub_niche", niche),
        language="en",
        preferred_topics=kw.pop("preferred_topics", []),
        forbidden_topics=kw.pop("forbidden_topics", []),
        **kw,
    )


def _ch(cid: int, niche: str) -> dict:
    return {"id": cid, "niche": niche, "youtube_name": f"ch{cid}"}


class RV009DiscoverySuccessTests(unittest.TestCase):
    def test_01_discovery_success(self):
        profile = _profile(1001, "tech", preferred_topics=["flagship phones"])
        cands = discover_topic_candidates(profile, count=4)
        self.assertGreater(len(cands), 0)
        for c in cands:
            self.assertEqual(c.source, "discovery")
            self.assertEqual(c.channel_id, 1001)
            prov = c.metadata.get("provenance") or {}
            self.assertEqual(prov.get("source_type"), DISCOVERY_SOURCE_TYPE)
            self.assertEqual(prov.get("provider"), DISCOVERY_PROVIDER)
            self.assertFalse(prov.get("external_api"))
            self.assertTrue(prov.get("discovered_at"))
            self.assertTrue(c.topic_id.startswith("t-"))


class RV009DiscoveryFailureTests(unittest.TestCase):
    def test_02_provider_unavailable(self):
        profile = _profile(1002, "tech")
        with self.assertRaises(DiscoveryUnavailableError):
            discover_topic_candidates(profile, provider_available=False)

    def test_03_empty_discovery_not_silent_success(self):
        profile = _profile(1003, "tech")
        seed_preview = discover_topic_candidates(profile, count=20)
        blocked = [c.title for c in seed_preview]
        result = discover_topic_candidates(profile, count=5, blocked=blocked)
        self.assertEqual(len(result), 0)
        with self.assertRaises(DiscoveryEmptyError):
            discover_topic_candidates(profile, count=5, blocked=blocked, require_non_empty=True)

    def test_04_malformed_candidate_rejected(self):
        ok, issues = validate_candidate_dict({"title": "", "source": "discovery", "channel_id": 1})
        self.assertFalse(ok)
        self.assertIn("missing_title", issues)
        with self.assertRaises(ValueError):
            candidate_from_dict({"title": "", "source": "pipeline", "channel_id": 1}, strict=True)

    def test_05_missing_source_rejected(self):
        ok, issues = validate_candidate_dict({"title": "Valid title", "channel_id": 5})
        self.assertFalse(ok)
        self.assertIn("missing_source", issues)

    def test_06_missing_timestamp_rejected_for_discovery(self):
        ok, issues = validate_candidate_dict({
            "title": "Topic",
            "source": "discovery",
            "channel_id": 6,
            "format": "LONG",
            "metadata": {"provenance": {"provider": "x", "external_api": False}},
        })
        self.assertFalse(ok)
        self.assertIn("missing_discovered_at", issues)


class RV009DuplicateAndNormalizationTests(unittest.TestCase):
    def test_07_duplicate_candidates_deduplicated(self):
        profile = _profile(1007, "finance")
        cands = discover_topic_candidates(profile, count=6)
        keys = [c.canonical_topic.lower() for c in cands]
        self.assertEqual(len(keys), len(set(keys)))

    def test_08_normalized_duplicate(self):
        a = "Why Did Apple Stock Fall Today?"
        b = "why did apple stock fall today"
        self.assertEqual(canonical_topic_key(a), canonical_topic_key(b))
        dup = analyze_duplicate(a, [b])
        self.assertEqual(dup.verdict.value, "DUPLICATE")

    def test_09_unrelated_candidate_retained(self):
        dup = analyze_duplicate(
            "Ancient Roman political history",
            ["Latest smartphone processor benchmark"],
        )
        self.assertEqual(dup.verdict.value, "UNIQUE")

    def test_normalization_unicode_and_punctuation(self):
        a = normalize_topic_text('"Why  Did   Apple—Stock   Fall?"')
        b = normalize_topic_text("why did apple stock fall")
        self.assertIn("apple", a)
        self.assertIn("apple", b)


class RV009ChannelIsolationTests(unittest.TestCase):
    def test_10_channel_isolation(self):
        tech = discover_topic_candidates(_profile(1010, "tech"), count=3)
        hist = discover_topic_candidates(_profile(1011, "ancient history"), count=3)
        self.assertTrue(all(c.channel_id == 1010 for c in tech))
        self.assertTrue(all(c.channel_id == 1011 for c in hist))
        self.assertNotEqual(tech[0].niche, hist[0].niche)

    def test_11_tech_relevance_in_discovery_context(self):
        cands = discover_topic_candidates(_profile(1011, "tech", sub_niche="gadgets"), count=2)
        ctx = cands[0].metadata.get("discovery_context") or {}
        self.assertEqual(ctx.get("niche"), "tech")

    def test_12_history_relevance(self):
        cands = discover_topic_candidates(_profile(1012, "ancient history"), count=2)
        self.assertIn("history", cands[0].title.lower() + cands[0].niche.lower())

    def test_13_finance_relevance(self):
        cands = discover_topic_candidates(_profile(1013, "finance", sub_niche="markets"), count=2)
        self.assertIn("finance", cands[0].metadata["discovery_context"]["niche"])

    def test_14_science_relevance(self):
        cands = discover_topic_candidates(_profile(1014, "science", sub_niche="physics"), count=2)
        self.assertEqual(cands[0].metadata["discovery_context"]["sub_niche"], "physics")

    def test_channel_dna_affects_scoring_not_leak(self):
        title = "RV009 shared borderline topic about markets"
        tech = score_candidate(
            candidate_from_dict({"title": title, "format": "LONG", "channel_id": 1, "niche": "tech", "source": "pipeline"}),
            channel_profile_from_row(_ch(1, "tech")),
        )
        fin = score_candidate(
            candidate_from_dict({"title": title, "format": "LONG", "channel_id": 2, "niche": "finance", "source": "pipeline"}),
            channel_profile_from_row(_ch(2, "finance")),
        )
        self.assertNotEqual(tech.dimensions.get("CHANNEL_RELEVANCE"), fin.dimensions.get("CHANNEL_RELEVANCE"))


class RV009FormatTests(unittest.TestCase):
    def test_15_long_short_isolation(self):
        profile = _profile(1015, "science")
        long_c = discover_topic_candidates(profile, fmt=ContentFormat.LONG, count=3)
        short_c = discover_topic_candidates(profile, fmt=ContentFormat.SHORT, count=3)
        self.assertTrue(all(c.format == ContentFormat.LONG for c in long_c))
        self.assertTrue(all(c.format == ContentFormat.SHORT for c in short_c))
        long_ids = {make_topic_id(1015, ContentFormat.LONG, c.canonical_topic) for c in long_c}
        short_ids = {make_topic_id(1015, ContentFormat.SHORT, c.canonical_topic) for c in short_c}
        self.assertTrue(long_ids.isdisjoint(short_ids) or long_c[0].canonical_topic != short_c[0].canonical_topic)


class RV009FreshnessTests(unittest.TestCase):
    def test_16_stale_candidate_detected(self):
        profile = _profile(1016, "tech")
        c = discover_topic_candidates(profile, count=1)[0]
        prov = c.metadata["provenance"]
        prov["discovered_at"] = time.time() - DEFAULT_DISCOVERY_MAX_AGE_SEC - 10
        c.metadata["provenance"] = prov
        self.assertTrue(is_discovery_stale(c))

    def test_17_invalid_identity_rejected(self):
        ok, issues = validate_candidate_dict({"title": "Valid", "source": "pipeline", "channel_id": 0})
        self.assertFalse(ok)
        self.assertIn("invalid_channel_id", issues)
        with self.assertRaises(ValueError):
            candidate_from_dict({"title": "Valid", "source": "pipeline", "channel_id": 0}, strict=True)


class RV009PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_18_persisted_candidate_reload(self):
        profile = _profile(1018, "finance")
        cands = discover_topic_candidates(profile, count=2)
        fp = discovery_input_fingerprint(profile, fmt=ContentFormat.LONG, count=2, historical=(), reserved=(), blocked=())
        path = save_discovery_artifact(self.tmp / "discovery.json", cands, fingerprint=fp)
        loaded = load_discovery_artifact(path)
        self.assertEqual(loaded["fingerprint"], fp)
        self.assertEqual(len(loaded["candidates"]), 2)
        reloaded = candidate_from_dict(loaded["candidates"][0])
        self.assertEqual(reloaded.topic_id, cands[0].topic_id)
        self.assertEqual(reloaded.canonical_topic, cands[0].canonical_topic)

    def test_19_corrupted_artifact_rejected(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_discovery_artifact(bad)
        empty = self.tmp / "empty.json"
        empty.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_discovery_artifact(empty)


class RV009IdempotencyTests(unittest.TestCase):
    def test_20_same_input_idempotency(self):
        profile = _profile(1020, "tech")
        fp1 = discovery_input_fingerprint(profile, fmt=ContentFormat.LONG, count=3, historical=(), reserved=(), blocked=())
        fp2 = discovery_input_fingerprint(profile, fmt=ContentFormat.LONG, count=3, historical=(), reserved=(), blocked=())
        self.assertEqual(fp1, fp2)
        c1 = discover_topic_candidates(profile, count=3)
        c2 = discover_topic_candidates(profile, count=3)
        self.assertEqual([c.topic_id for c in c1], [c.topic_id for c in c2])

    def test_21_changed_input_regeneration(self):
        profile = _profile(1021, "tech")
        fp_a = discovery_input_fingerprint(profile, fmt=ContentFormat.LONG, count=3, historical=(), reserved=(), blocked=())
        fp_b = discovery_input_fingerprint(profile, fmt=ContentFormat.SHORT, count=3, historical=(), reserved=(), blocked=())
        self.assertNotEqual(fp_a, fp_b)
        long_c = discover_topic_candidates(profile, fmt=ContentFormat.LONG, count=2)
        short_c = discover_topic_candidates(profile, fmt=ContentFormat.SHORT, count=2)
        self.assertNotEqual(long_c[0].topic_id, short_c[0].topic_id)


class RV009FalseDiscoveryLabelTests(unittest.TestCase):
    def test_mock_not_labeled_external(self):
        profile = _profile(1022, "history")
        c = discover_topic_candidates(profile, count=1)[0]
        prov = c.metadata["provenance"]
        self.assertEqual(prov["source_type"], "local_generated")
        self.assertFalse(prov["external_api"])
        self.assertNotIn("trending", prov["provider"])
        self.assertNotIn("live", prov["provider"])
        self.assertNotEqual(prov["source_type"], "external")


class RV009ProductionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"
        os.environ.pop("INTELLIGENCE_DISCOVERY_DISABLED", None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_22_production_auto_discover_integration(self):
        profile = channel_profile_from_row(_ch(1022, "tech"))
        result = run_topic_intelligence(
            self.tmp,
            profile,
            None,
            auto_discover=True,
            discover_count=3,
            use_mock_research=True,
        )
        self.assertGreater(len(result.get("evaluated") or []), 0)
        cand = result["evaluated"][0]["candidate"]
        self.assertEqual(cand.get("source"), "discovery")
        prov = (cand.get("metadata") or {}).get("provenance") or {}
        self.assertEqual(prov.get("source_type"), DISCOVERY_SOURCE_TYPE)
        self.assertFalse(prov.get("external_api"))
        self.assertTrue(result.get("ranked_long") or result.get("ranked_short"))

    def test_concurrent_discovery_isolation(self):
        results: dict[int, list] = {}

        def _run(cid: int, niche: str):
            p = channel_profile_from_row(_ch(cid, niche))
            cands = discover_topic_candidates(p, count=2)
            results[cid] = cands

        threads = [
            threading.Thread(target=_run, args=(1023, "tech")),
            threading.Thread(target=_run, args=(1024, "finance")),
            threading.Thread(target=_run, args=(1025, "science")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results[1023][0].channel_id, 1023)
        self.assertEqual(results[1024][0].channel_id, 1024)
        self.assertEqual(results[1025][0].channel_id, 1025)

    def test_env_discovery_disabled(self):
        os.environ["INTELLIGENCE_DISCOVERY_DISABLED"] = "1"
        try:
            with self.assertRaises(DiscoveryUnavailableError):
                discover_topic_candidates(_profile(1026, "tech"))
        finally:
            os.environ.pop("INTELLIGENCE_DISCOVERY_DISABLED", None)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\nAMP-002 RV-009: {passed} / {result.testsRun}")
    sys.exit(0 if result.wasSuccessful() else 1)
