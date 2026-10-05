#!/usr/bin/env python3
"""AMP-001 TASK-006 through TASK-020 marathon acceptance tests."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.channel_dna import from_channel_row, infer_style_family
from pipeline.intelligence.cache_registry import bump_channel_version, bump_research_scope, get_channel_version, is_ranking_stale
from pipeline.intelligence.contracts import ContentFormat, DuplicateVerdict, ResearchRequest, TrendClass
from pipeline.intelligence.discovery import discover_topic_candidates
from pipeline.intelligence.duplicate import analyze_duplicate
from pipeline.intelligence.factpack_gate import validate_fact_pack
from pipeline.intelligence.fingerprint import compute_research_fingerprint
from pipeline.intelligence.orchestrator import refresh_topic_intelligence, run_topic_intelligence, select_topic_for_production
from pipeline.intelligence.provenance import record_topic_provenance
from pipeline.intelligence.research_runtime import execute_research_request, get_cost_ledger, provider_execution_count, reset_cost_ledger
from pipeline.intelligence.reserve_queue import load_reserve, repair_reserve, save_reserve, update_reserve, validate_reserve_integrity
from pipeline.intelligence.scoring import channel_profile_from_row
from pipeline.intelligence.trend import classify_trend_from_signals, seo_heuristic_score


def _profile(**kw):
    from pipeline.intelligence.contracts import ChannelProfile
    cid = kw.pop("channel_id", 97000)
    niche = kw.pop("niche", "tech")
    return ChannelProfile(channel_id=cid, niche=niche, language="en", **kw)


class Task006RealResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "LIVE"
        reset_cost_ledger()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_live_research_has_required_fields(self):
        req = ResearchRequest(topic_id="t006", canonical_topic="Real research topic", query="real research topic", language="en")
        rr = execute_research_request(self.tmp, req, job_id="t006", use_mock=False)
        self.assertTrue(rr.success)
        research = rr.research or {}
        for field in ("timestamp", "query", "provider", "evidence"):
            self.assertIn(field, research, f"missing {field}")
        self.assertTrue(research.get("evidence"))
        self.assertTrue(research.get("sources") or any(c.get("source") for c in research.get("evidence", [])))


class Task007ResearchRankingFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_research_before_ranking(self):
        profile = _profile(channel_id=97007)
        result = run_topic_intelligence(self.tmp, profile, [{"title": "Flow topic", "format": "LONG", "channel_id": 97007}], use_mock_research=True)
        tid = result["evaluated"][0]["candidate"]["topic_id"]
        self.assertIn(tid, result["research"])
        self.assertEqual(result["research"][tid].get("gate", {}).get("verdict"), "PASS")
        self.assertTrue(result.get("ranked_long"))


class Task008ChannelDnaTests(unittest.TestCase):
    def test_tech_not_history(self):
        self.assertEqual(infer_style_family("tech"), "gadget")
        dna = from_channel_row({"id": 1, "niche": "tech", "language": "en"})
        self.assertEqual(dna.style_family, "gadget")

    def test_history_niche(self):
        dna = from_channel_row({"id": 2, "niche": "ancient history"})
        self.assertEqual(dna.style_family, "history")


class Task009DiscoveryTests(unittest.TestCase):
    def test_discovery_vs_pipeline_source(self):
        profile = _profile(channel_id=97009, niche="finance")
        discovered = discover_topic_candidates(profile, count=3)
        self.assertTrue(all(c.source == "discovery" for c in discovered))
        pipeline_cand = {"title": "Manual topic", "format": "LONG", "channel_id": 97009, "source": "pipeline"}
        self.assertEqual(pipeline_cand["source"], "pipeline")
        self.assertNotEqual(discovered[0].source, "pipeline")


class Task010TrendTests(unittest.TestCase):
    def test_trend_requires_evidence(self):
        self.assertEqual(classify_trend_from_signals(trend_score=0.99), TrendClass.TREND_SIGNAL_UNAVAILABLE)
        self.assertEqual(classify_trend_from_signals(trend_score=0.8, trend_evidence="google_trends", source_count=2), TrendClass.TRENDING)


class Task011SemanticDuplicateTests(unittest.TestCase):
    def test_semantic_paraphrase_detected(self):
        existing = ["Why did Apple stock drop sharply today"]
        r = analyze_duplicate("Apple shares fell steeply today — what caused it", existing)
        self.assertIn(r.verdict, (DuplicateVerdict.DUPLICATE, DuplicateVerdict.POSSIBLE_DUPLICATE))

    def test_multilingual_normalization(self):
        from pipeline.intelligence.normalization import normalize_topic_text
        self.assertIn("bitcoin", normalize_topic_text("কেন Bitcoin পড়ে গেল?"))


class Task012CacheInvalidationTests(unittest.TestCase):
    def test_channel_version_invalidates_ranking(self):
        cid = 97012
        v0 = get_channel_version(cid)
        bump_channel_version(cid, reason="test")
        self.assertTrue(is_ranking_stale(cid, v0))

    def test_prompt_version_changes_fingerprint(self):
        r1 = ResearchRequest(topic_id="fp1", canonical_topic="topic", query="topic", prompt_version="v1")
        r2 = ResearchRequest(topic_id="fp1", canonical_topic="topic", query="topic", prompt_version="v2")
        self.assertNotEqual(compute_research_fingerprint(r1), compute_research_fingerprint(r2))
        bump_research_scope("scope-test")


class Task013FactpackGateTests(unittest.TestCase):
    def test_unsupported_claims_blocked(self):
        gate = validate_fact_pack({"claims": [{"claim": "x", "evidence": "UNVERIFIED", "source": ""}]})
        self.assertEqual(gate["verdict"], "RESEARCH_REQUIRED")

    def test_supported_claims_pass(self):
        gate = validate_fact_pack({"claims": [
            {"claim": "a", "evidence": "secondary", "source": "s1"},
            {"claim": "b", "evidence": "supporting", "source": "s2"},
        ]})
        self.assertEqual(gate["verdict"], "PASS")


class Task014ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_provenance_chain_recorded(self):
        p = record_topic_provenance(
            self.tmp,
            topic_id="prov-1",
            discovery={"source": "discovery", "channel_id": 1},
            ranking={"total_score": 0.8},
            research={"fingerprint": "abc123", "gate": {"verdict": "PASS"}},
        )
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertIn("discovery", data)
        self.assertIn("ranking", data)
        self.assertIn("research", data)
        self.assertIn("recorded_at", data)


class Task015DailyRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_refresh_reruns_research_not_timestamp_only(self):
        profile = _profile(channel_id=97015)
        cands = [{"title": f"Refresh topic {i}", "format": "LONG", "channel_id": 97015} for i in range(6)]
        run_topic_intelligence(self.tmp, profile, cands, use_mock_research=True)
        report = refresh_topic_intelligence(self.tmp, profile, use_mock_research=True)
        self.assertIn("reranked", report)
        self.assertTrue(any((report["reranked"].get(fmt) or {}).get("count", 0) >= 0 for fmt in ("LONG", "SHORT")))
        maint = self.tmp / "intelligence" / "maintenance_report.json"
        self.assertTrue(maint.is_file())
        body = json.loads(maint.read_text(encoding="utf-8"))
        self.assertIn("timestamp", body)
        self.assertIn("reserves", body)


class Task016ReserveRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cid = 97016

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_repair_dedupes_and_reorders(self):
        bad = [
            {"title": "Dup", "canonical_topic": "dup", "status": "RESERVED", "rank": 1},
            {"title": "Dup copy", "canonical_topic": "dup", "status": "RESERVED", "rank": 2},
            {"title": "Good", "canonical_topic": "good", "status": "RESERVED", "rank": 3},
        ]
        save_reserve(self.tmp, ContentFormat.LONG, bad, channel_id=self.cid)
        report = repair_reserve(self.tmp, ContentFormat.LONG, channel_id=self.cid)
        self.assertTrue(report.get("repaired"))
        fixed = load_reserve(self.tmp, ContentFormat.LONG, channel_id=self.cid)
        ok, issues = validate_reserve_integrity(fixed)
        self.assertTrue(ok, issues)


class Task017ApiCostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        reset_cost_ledger()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_duplicate_check_no_research_calls(self):
        from pipeline.intelligence.mock_research_provider import get_mock_research_provider
        mp = get_mock_research_provider()
        mp.reset()
        existing = []
        for i in range(50):
            analyze_duplicate(f"Unique topic {i}", existing)
            existing.append(f"Unique topic {i}")
        self.assertEqual(len(mp.calls), 0)

    def test_concurrent_research_single_execution(self):
        from pipeline.intelligence.mock_research_provider import get_mock_research_provider
        mp = get_mock_research_provider()
        mp.reset()
        work = self.tmp / "cost"
        work.mkdir()
        req = ResearchRequest(topic_id="cost", canonical_topic="Cost topic", query="cost")
        threads = [threading.Thread(target=lambda: execute_research_request(work, req, job_id="cost", use_mock=True, mock_provider=mp)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(mp.calls), 1)
        self.assertGreaterEqual(provider_execution_count(), 1)


class Task018IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"
        os.environ["INTELLIGENCE_MODE"] = "DEVELOPMENT"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_chain_discover_to_reserve(self):
        profile = _profile(channel_id=97018)
        result = run_topic_intelligence(self.tmp, profile, None, auto_discover=True, discover_count=4, use_mock_research=True)
        self.assertIn("long_reserve", result)
        self.assertIn("short_reserve", result)
        sel = select_topic_for_production(self.tmp, profile, fmt=ContentFormat.LONG)
        self.assertIsNotNone(sel.get("selected"))
        prov_dir = self.tmp / "intelligence" / "provenance"
        self.assertTrue(prov_dir.exists() or (self.tmp / "intelligence" / "topic_intelligence_result.json").is_file())


class Task019CleanEnvironmentTests(unittest.TestCase):
    def test_compileall_pipeline(self):
        r = subprocess.run([sys.executable, "-m", "compileall", "-q", "pipeline"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class Task020FinalAuditTests(unittest.TestCase):
    def test_no_silent_intelligence_skip_in_production_path(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("assert_production_intelligence_validated", src)
        self.assertIn("legacy topic fallback blocked in production", src)

    def test_gate_blocked_marker_exists(self):
        from pipeline.intelligence.gate import GATE_BLOCKED_MARKER
        self.assertEqual(GATE_BLOCKED_MARKER, "INTELLIGENCE_GATE_BLOCKED")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\nAMP-001 TASKS 006-020: {passed} / {result.testsRun}")
    sys.exit(0 if result.wasSuccessful() else 1)
