#!/usr/bin/env python3
"""AMP-002 RV-006 — Real Research Execution re-verification tests."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.intelligence.config import ResearchMode
from pipeline.intelligence.contracts import ResearchRequest
from pipeline.intelligence.orchestrator import run_topic_intelligence
from pipeline.intelligence.research_provider import (
    LiveResearchProvider,
    MockResearchProviderAdapter,
    get_research_provider,
    research_unavailable_error,
)
from pipeline.intelligence.research_runtime import (
    execute_research_request,
    provider_execution_count,
    reset_cost_ledger,
)
from pipeline.intelligence.scoring import channel_profile_from_row


def _req(**kw) -> ResearchRequest:
    base = dict(
        topic_id="rv006",
        canonical_topic="RV006 research topic",
        query="RV006 research topic",
        language="en",
        region="US",
    )
    base.update(kw)
    return ResearchRequest(**base)


class RV006VerticalSliceTests(unittest.TestCase):
    """INPUT → execute_research_request → persist → read artifact."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "LIVE"
        reset_cost_ledger()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_live_local_vertical_slice_persistence(self):
        req = _req(topic_id="rv006-live", query="  RV006 research topic  ")
        rr = execute_research_request(self.tmp, req, job_id="rv006", use_mock=False)
        self.assertTrue(rr.success, "LIVE local research must succeed")
        self.assertEqual(rr.action, "execute")
        self.assertTrue(rr.fingerprint)

        artifact_path = self.tmp / "research" / "rv006-live.json"
        self.assertTrue(artifact_path.is_file(), "research artifact must persist")
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        research = data["research"]
        self.assertEqual(research["provider"], "live_local")
        self.assertFalse(research["external_api"])
        self.assertEqual(research["provider_kind"], "configured_local")
        self.assertEqual(research["query"], "rv006 research topic")  # normalized
        self.assertIsInstance(research["timestamp"], (int, float))
        self.assertGreater(research["timestamp"], 0)
        self.assertTrue(research.get("evidence"))
        self.assertTrue(research.get("sources"))
        self.assertEqual(data.get("research_fingerprint"), rr.fingerprint)
        self.assertEqual(data.get("provider_mode"), "LIVE")

        # orchestrator production callsite
        profile = channel_profile_from_row({"id": 80601, "niche": "tech"})
        orch = run_topic_intelligence(
            self.tmp / "orch",
            profile,
            [{"title": "RV006 orch topic", "format": "LONG", "channel_id": 80601}],
            use_mock_research=False,
        )
        tid = orch["evaluated"][0]["candidate"]["topic_id"]
        self.assertIn(tid, orch["research"])
        self.assertTrue(orch["research"][tid].get("success"))


class RV006ProviderBoundaryTests(unittest.TestCase):
    def test_live_provider_is_not_mock(self):
        live = get_research_provider(mode=ResearchMode.LIVE)
        mock = get_research_provider(mode=ResearchMode.MOCK)
        self.assertIsInstance(live, LiveResearchProvider)
        self.assertIsInstance(mock, MockResearchProviderAdapter)

    def test_live_not_labeled_external(self):
        req = _req(topic_id="rv006-boundary")
        out = LiveResearchProvider().research(req)
        self.assertEqual(out["research"]["provider"], "live_local")
        self.assertFalse(out["research"]["external_api"])


class RV006NegativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        reset_cost_ledger()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_provider_unavailable_blocks(self):
        req = _req(topic_id="rv006-unavail")

        def _fail():
            return research_unavailable_error(req, "simulated down")

        rr = execute_research_request(self.tmp, req, job_id="rv006", provider_fn=_fail)
        self.assertFalse(rr.success)

    def test_provider_exception_blocks(self):
        req = _req(topic_id="rv006-exc")

        def _raise():
            raise TimeoutError("simulated timeout")

        rr = execute_research_request(self.tmp, req, job_id="rv006", provider_fn=_raise)
        self.assertFalse(rr.success)

    def test_empty_response_blocks(self):
        req = _req(topic_id="rv006-empty")

        def _empty():
            return {"research": {}, "fact_pack": None}

        rr = execute_research_request(self.tmp, req, job_id="rv006", provider_fn=_empty)
        self.assertFalse(rr.success)

    def test_malformed_no_claims_blocks(self):
        req = _req(topic_id="rv006-malformed")

        def _bad():
            return {"research": {"status": "completed"}, "fact_pack": {"claims": []}}

        rr = execute_research_request(self.tmp, req, job_id="rv006", provider_fn=_bad)
        self.assertFalse(rr.success)

    def test_missing_source_blocks(self):
        req = _req(topic_id="rv006-nosrc")

        def _nosrc():
            return {
                "research": {"status": "completed", "provider": "test"},
                "fact_pack": {"claims": [{"claim": "x", "evidence": "secondary", "source": ""}]},
            }

        rr = execute_research_request(self.tmp, req, job_id="rv006", provider_fn=_nosrc)
        self.assertFalse(rr.success)

    def test_missing_evidence_empty_claims_blocks(self):
        req = _req(topic_id="rv006-noev")
        rr = execute_research_request(
            self.tmp,
            req,
            job_id="rv006",
            provider_fn=lambda: {"research": {"status": "ok"}, "fact_pack": {"claims": []}},
        )
        self.assertFalse(rr.success)

    def test_invalid_cache_tampered_artifact_fails_success(self):
        req = _req(topic_id="rv006-cache")
        rr1 = execute_research_request(self.tmp, req, job_id="rv006", use_mock=True)
        self.assertTrue(rr1.success)
        path = Path(rr1.fingerprint and self.tmp / "research" / "rv006-cache.json")
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        data["fact_pack"]["claims"] = [{"claim": "tampered", "evidence": "x", "source": ""}]
        path.write_text(json.dumps(data), encoding="utf-8")
        rr2 = execute_research_request(self.tmp, req, job_id="rv006", use_mock=True)
        self.assertFalse(rr2.success, "tampered cache must not report success")

    def test_duplicate_request_single_execution(self):
        from pipeline.intelligence.mock_research_provider import get_mock_research_provider

        mp = get_mock_research_provider()
        mp.reset()
        req = _req(topic_id="rv006-dup")
        work = self.tmp / "dup"
        work.mkdir()

        def _run():
            execute_research_request(work, req, job_id="dup", use_mock=True, mock_provider=mp)

        threads = [threading.Thread(target=_run) for _ in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(mp.calls), 1)

    def test_live_provider_exception_returns_unavailable(self):
        req = _req(topic_id="rv006-liveexc")
        with patch.object(LiveResearchProvider, "research", side_effect=RuntimeError("build failed")):
            rr = execute_research_request(self.tmp, req, job_id="rv006", use_mock=False)
        self.assertFalse(rr.success)


class RV006IdempotencyReuseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        reset_cost_ledger()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_cache_reuse_without_reexecution(self):
        from pipeline.intelligence.mock_research_provider import get_mock_research_provider

        mp = get_mock_research_provider()
        mp.reset()
        req = _req(topic_id="rv006-reuse")
        rr1 = execute_research_request(self.tmp, req, job_id="reuse", use_mock=True, mock_provider=mp)
        self.assertTrue(rr1.success)
        self.assertEqual(rr1.action, "execute")
        self.assertEqual(len(mp.calls), 1)
        rr2 = execute_research_request(self.tmp, req, job_id="reuse", use_mock=True, mock_provider=mp)
        self.assertTrue(rr2.success)
        self.assertEqual(rr2.action, "reuse")
        self.assertEqual(len(mp.calls), 1, "reuse must not call provider again")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\nAMP-002 RV-006: {passed} / {result.testsRun}")
    if not result.wasSuccessful():
        raise SystemExit(1)
