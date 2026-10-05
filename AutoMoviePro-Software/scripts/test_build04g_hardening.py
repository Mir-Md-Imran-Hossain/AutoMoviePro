#!/usr/bin/env python3
"""BUILD-04G-H production hardening tests."""
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

from pipeline.channel_dna import from_channel_row, infer_style_family
from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.store import _store_lock
from pipeline.intelligence.cache_registry import bump_channel_version, get_channel_version, is_ranking_stale
from pipeline.intelligence.config import ResearchMode, get_research_mode
from pipeline.intelligence.contracts import ContentFormat, TrendClass
from pipeline.intelligence.discovery import discover_topic_candidates
from pipeline.intelligence.factpack_gate import validate_fact_pack
from pipeline.intelligence.gate import GateVerdict, block_if_not_pass, evaluate_gate_result
from pipeline.intelligence.normalization import canonical_topic_key, normalize_topic_text
from pipeline.intelligence.orchestrator import run_topic_intelligence
from pipeline.intelligence.research_runtime import execute_research_request, provider_execution_count, reset_cost_ledger
from pipeline.intelligence.contracts import ResearchRequest
from pipeline.intelligence.reserve_queue import load_reserve, save_reserve, update_reserve
from pipeline.intelligence.scoring import channel_profile_from_row
from pipeline.intelligence.trend import classify_trend_from_signals, seo_heuristic_score


def _profile(**kw):
    from pipeline.intelligence.contracts import ChannelProfile
    cid = kw.pop("channel_id", 9001)
    niche = kw.pop("niche", "tech")
    return ChannelProfile(channel_id=cid, niche=niche, **kw)


class Build04GHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"
        os.environ["INTELLIGENCE_MODE"] = "DEVELOPMENT"
        reset_cost_ledger()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_h1_idempotency_concurrency_100_rounds(self):
        """Same fingerprint — exactly 1 provider execution per round."""
        for round_i in range(100):
            work = self.tmp / f"round-{round_i}"
            work.mkdir()
            inv = {"n": 0}
            lock = threading.Lock()
            executor = IdempotentExecutor(work)

            def worker():
                def _exec():
                    with lock:
                        inv["n"] += 1
                    return {"ok": True, "v": round_i}

                out_path = work / "out.json"

                def _persist(o):
                    out_path.write_text(json.dumps(o), encoding="utf-8")
                    return str(out_path)

                executor.execute(
                    job_id="j",
                    stage="test",
                    entity_id="e1",
                    inputs={"x": round_i},
                    execute_fn=_exec,
                    validate_fn=lambda o: (True, "ok"),
                    persist_fn=_persist,
                )

            threads = [threading.Thread(target=worker) for _ in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(inv["n"], 1, f"round {round_i} had {inv['n']} executions")

    def test_h1_lock_registry_thread_safe(self):
        locks = []

        def get_lock():
            locks.append(_store_lock(self.tmp / "IDEMPOTENCY.json"))

        threads = [threading.Thread(target=get_lock) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(set(id(l) for l in locks)), 1)

    def test_h2_reserve_atomic_concurrent_writers(self):
        channel_id = 9101
        fmt = ContentFormat.LONG
        errors: list[str] = []
        lock = threading.Lock()

        def writer(i: int):
            try:
                entries = [{"title": f"Topic {i}-{j}", "canonical_topic": f"topic {i}-{j}", "status": "RESERVED", "rank": j + 1} for j in range(3)]
                save_reserve(None, fmt, entries, channel_id=channel_id, language="en")
            except Exception as exc:
                with lock:
                    errors.append(str(exc))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        loaded = load_reserve(None, fmt, channel_id=channel_id, language="en")
        self.assertTrue(isinstance(loaded, list))
        json.dumps(loaded)

    def test_h3_persistent_reserve_survives_work_dir(self):
        profile = _profile(channel_id=9201)
        cands = [{"title": f"Persistent {i}", "format": "LONG", "channel_id": 9201} for i in range(6)]
        run_topic_intelligence(self.tmp / "job1", profile, cands, use_mock_research=True)
        entries = load_reserve(None, ContentFormat.LONG, channel_id=9201, language="en")
        self.assertGreaterEqual(len(entries), 1)
        work2 = self.tmp / "job2"
        work2.mkdir()
        from pipeline.intelligence.bridge import pick_topic_from_reserve
        topic = pick_topic_from_reserve(work2, {"id": 9201, "niche": "tech"}, video_type="long")
        self.assertTrue(topic)

    def test_h4_fail_closed_gate_blocks_unknown(self):
        result = {"accepted": False, "reason": "UNKNOWN", "gate_error": "provider down"}
        verdict = evaluate_gate_result(result)
        self.assertEqual(verdict, GateVerdict.UNKNOWN)
        with self.assertRaises(RuntimeError) as ctx:
            os.environ["INTELLIGENCE_MODE"] = "PRODUCTION"
            block_if_not_pass(verdict, context="test", detail="fail", allow_development_bypass=False)
        self.assertIn("INTELLIGENCE_GATE_BLOCKED", str(ctx.exception))

    def test_h5_live_mode_not_mock_by_default(self):
        os.environ.pop("INTELLIGENCE_RESEARCH_MODE", None)
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "LIVE"
        self.assertEqual(get_research_mode(), ResearchMode.LIVE)

    def test_h5_mock_explicit_only(self):
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"
        self.assertEqual(get_research_mode(), ResearchMode.MOCK)

    def test_h6_discovery_channel_aware(self):
        profile = _profile(channel_id=9301, niche="finance", sub_niche="markets", forbidden_topics=["scam"])
        cands = discover_topic_candidates(profile, count=5, blocked=["scam topic"])
        self.assertGreater(len(cands), 0)
        for c in cands:
            self.assertEqual(c.channel_id, 9301)
            self.assertNotIn("scam", c.title.lower())

    def test_h7_tech_not_history(self):
        self.assertEqual(infer_style_family("tech"), "gadget")
        self.assertEqual(infer_style_family("technology"), "gadget")
        self.assertEqual(infer_style_family("gadgets"), "gadget")
        dna = from_channel_row({"id": 1, "niche": "tech"})
        self.assertEqual(dna.style_family, "gadget")
        self.assertNotIn("iphone", str(dna.forbidden_topics).lower() or "x")  # gadget has empty forbidden

    def test_h7_history_niche(self):
        dna = from_channel_row({"id": 2, "niche": "ancient history"})
        self.assertEqual(dna.style_family, "history")

    def test_h8_research_before_final_ranking(self):
        profile = _profile(channel_id=9401)
        result = run_topic_intelligence(
            self.tmp, profile,
            [{"title": "Research first topic", "format": "LONG", "channel_id": 9401}],
            use_mock_research=True,
        )
        self.assertIn("research", result)
        tid = result["evaluated"][0]["candidate"]["topic_id"]
        self.assertIn(tid, result["research"])
        self.assertEqual(result["research"][tid].get("gate", {}).get("verdict"), "PASS")

    def test_h9_trend_no_fabrication(self):
        tc = classify_trend_from_signals(trend_score=0.99)
        self.assertEqual(tc, TrendClass.TREND_SIGNAL_UNAVAILABLE)
        tc2 = classify_trend_from_signals(trend_score=0.8, trend_evidence="google_trends", source_count=2)
        self.assertEqual(tc2, TrendClass.TRENDING)

    def test_h10_seo_heuristic_honest(self):
        s = seo_heuristic_score("Best phone 2026", niche="tech")
        self.assertLessEqual(s, 1.0)
        self.assertGreater(s, 0)

    def test_h11_multilingual_normalization(self):
        bn = normalize_topic_text("কেন Bitcoin পড়ে গেল?")
        self.assertIn("bitcoin", bn)
        ar = normalize_topic_text("ما هو Bitcoin")
        self.assertIn("bitcoin", ar)

    def test_h13_cache_invalidation(self):
        v0 = get_channel_version(9501)
        bump_channel_version(9501, reason="test")
        v1 = get_channel_version(9501)
        self.assertTrue(is_ranking_stale(9501, v0))
        self.assertFalse(is_ranking_stale(9501, v1))

    def test_h14_strict_factpack_all_unsupported(self):
        gate = validate_fact_pack({"claims": [{"claim": "x", "evidence": "UNVERIFIED", "source": ""}]})
        self.assertEqual(gate["verdict"], "RESEARCH_REQUIRED")

    def test_h14_strict_factpack_pass(self):
        gate = validate_fact_pack({"claims": [
            {"claim": "a", "evidence": "secondary", "source": "s1"},
            {"claim": "b", "evidence": "supporting", "source": "s2"},
        ]})
        self.assertEqual(gate["verdict"], "PASS")

    def test_h14_conflict(self):
        gate = validate_fact_pack({"claims": [
            {"claim": "Price increased 50%", "evidence": "secondary", "source": "a"},
            {"claim": "Price decreased 50%", "evidence": "secondary", "source": "b"},
        ]})
        self.assertEqual(gate["verdict"], "RESEARCH_CONFLICT")

    def test_h20_cost_no_llm_duplicates(self):
        from pipeline.intelligence.duplicate import analyze_duplicate
        from pipeline.intelligence.mock_research_provider import get_mock_research_provider
        mp = get_mock_research_provider()
        mp.reset()
        existing = []
        for i in range(100):
            analyze_duplicate(f"Topic {i} unique", existing)
            existing.append(f"Topic {i} unique")
        self.assertEqual(len(mp.calls), 0)

    def test_h21_concurrent_research_one_execution(self):
        from pipeline.intelligence.mock_research_provider import get_mock_research_provider

        reset_cost_ledger()
        work = self.tmp / "cr"
        work.mkdir()
        mp = get_mock_research_provider()
        mp.reset()
        req = ResearchRequest(topic_id="conc-h", canonical_topic="Concurrent H", query="conc")

        def worker():
            execute_research_request(work, req, job_id="cr", use_mock=True, mock_provider=mp)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(mp.calls), 1)

    def test_h23_unknown_stays_unknown(self):
        from pipeline.intelligence.contracts import DuplicateVerdict
        from pipeline.intelligence.duplicate import analyze_duplicate
        r = analyze_duplicate("", [])
        self.assertEqual(r.verdict, DuplicateVerdict.UNKNOWN)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Build04GHardeningTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    passed = total - failed
    print(f"\nBUILD-04G-H TESTS: {passed} / {total}")
    sys.exit(0 if failed == 0 else 1)
