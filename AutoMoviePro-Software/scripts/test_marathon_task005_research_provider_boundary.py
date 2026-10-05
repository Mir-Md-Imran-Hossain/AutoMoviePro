#!/usr/bin/env python3
"""AMP-001 TASK-005 — Research provider boundary acceptance tests."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.intelligence.config import ResearchMode, get_research_mode
from pipeline.intelligence.contracts import ResearchRequest
from pipeline.intelligence.gate import GATE_BLOCKED_MARKER, resolve_research_use_mock
from pipeline.intelligence.research_provider import LiveResearchProvider, MockResearchProviderAdapter, get_research_provider
from pipeline.intelligence.research_runtime import execute_research_request, reset_cost_ledger


class Task005ProviderBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        reset_cost_ledger()
        os.environ.pop("INTELLIGENCE_RESEARCH_MODE", None)
        os.environ.pop("INTELLIGENCE_MODE", None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("INTELLIGENCE_RESEARCH_MODE", None)
        os.environ.pop("INTELLIGENCE_MODE", None)

    def _req(self) -> ResearchRequest:
        return ResearchRequest(
            topic_id="t005",
            canonical_topic="Provider boundary topic",
            query="provider boundary topic",
            language="en",
            region="US",
        )

    def test_default_mode_is_live_not_mock(self):
        """MOCK production default নয় — LIVE default."""
        self.assertEqual(get_research_mode(), ResearchMode.LIVE)

    def test_mock_requires_explicit_env(self):
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"
        self.assertEqual(get_research_mode(), ResearchMode.MOCK)

    def test_mock_forbidden_in_production_live(self):
        os.environ["INTELLIGENCE_MODE"] = "PRODUCTION"
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "LIVE"
        with self.assertRaises(RuntimeError) as ctx:
            resolve_research_use_mock(True)
        self.assertIn(GATE_BLOCKED_MARKER, str(ctx.exception))

    def test_live_provider_not_mock_adapter(self):
        live = get_research_provider(mode=ResearchMode.LIVE)
        mock = get_research_provider(mode=ResearchMode.MOCK)
        self.assertIsInstance(live, LiveResearchProvider)
        self.assertIsInstance(mock, MockResearchProviderAdapter)
        self.assertNotEqual(type(live), type(mock))

    def test_live_result_not_labeled_external_or_mock(self):
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "LIVE"
        rr = execute_research_request(self.tmp, self._req(), job_id="t005-live", use_mock=False)
        self.assertEqual(rr.provider_mode, "LIVE")
        research = rr.research or {}
        self.assertEqual(research.get("provider"), "live_local")
        self.assertFalse(research.get("external_api"))
        claims = (rr.fact_pack or {}).get("claims") or []
        for c in claims:
            src = str(c.get("source") or "")
            self.assertNotIn("mock", src.lower())

    def test_mock_result_explicitly_mock(self):
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"
        rr = execute_research_request(self.tmp, self._req(), job_id="t005-mock", use_mock=True)
        self.assertEqual(rr.provider_mode, "MOCK")
        research = rr.research or {}
        self.assertEqual(research.get("provider"), "mock")
        self.assertFalse(research.get("external_api"))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Task005ProviderBoundaryTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\nAMP-001 TASK-005 TESTS: {passed} / {result.testsRun}")
    if not result.wasSuccessful():
        raise SystemExit(1)
