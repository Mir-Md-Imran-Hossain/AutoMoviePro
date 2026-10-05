#!/usr/bin/env python3
"""AMP-001 TASK-004 — Fail-closed intelligence gate acceptance tests."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.intelligence.bridge import run_intelligence_gate
from pipeline.intelligence.gate import (
    GATE_BLOCKED_MARKER,
    GateVerdict,
    assert_production_intelligence_validated,
    block_if_not_pass,
    evaluate_gate_result,
)


def _channel(**kw):
    base = {"id": 94004, "niche": "tech", "style_family": "gadget"}
    base.update(kw)
    return base


class Task004GateUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_MODE"] = "PRODUCTION"
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("INTELLIGENCE_MODE", None)
        os.environ.pop("INTELLIGENCE_RESEARCH_MODE", None)

    def test_a_valid_intelligence_passes_gate(self):
        """TEST-A: valid intelligence → PASS verdict."""
        result = run_intelligence_gate(
            self.tmp,
            _channel(),
            "Valid intelligence topic for gate",
            use_mock_research=True,
        )
        verdict = evaluate_gate_result(result, context="test_a")
        self.assertEqual(verdict, GateVerdict.PASS)
        self.assertTrue(result.get("accepted"))

    def test_b_intelligence_none_blocks(self):
        """TEST-B: intelligence = None → NOT_READY → BLOCK."""
        verdict = evaluate_gate_result(None, context="test_b")
        self.assertEqual(verdict, GateVerdict.NOT_READY)
        with self.assertRaises(RuntimeError) as ctx:
            block_if_not_pass(verdict, context="test_b", allow_development_bypass=False)
        self.assertIn(GATE_BLOCKED_MARKER, str(ctx.exception))

    def test_c_intelligence_exception_blocks(self):
        """TEST-C: gate_error / exception path → UNKNOWN → BLOCK."""
        result = {"accepted": False, "reason": "UNKNOWN", "gate_error": "provider down"}
        verdict = evaluate_gate_result(result, context="test_c")
        self.assertEqual(verdict, GateVerdict.UNKNOWN)
        with self.assertRaises(RuntimeError):
            block_if_not_pass(verdict, context="test_c", allow_development_bypass=False)

    def test_d_invalid_intelligence_blocks(self):
        """TEST-D: invalid intelligence → FAIL → BLOCK."""
        result = {"accepted": False, "reason": "DUPLICATE"}
        verdict = evaluate_gate_result(result, context="test_d")
        self.assertEqual(verdict, GateVerdict.FAIL)
        with self.assertRaises(RuntimeError):
            block_if_not_pass(verdict, context="test_d", allow_development_bypass=False)

    def test_e_empty_reserve_blocks_production(self):
        """TEST-E: empty reserve / no topic → production assert blocks."""
        with self.assertRaises(RuntimeError) as ctx:
            assert_production_intelligence_validated(
                passed=False,
                context="test_e",
                detail="empty reserve",
            )
        self.assertIn(GATE_BLOCKED_MARKER, str(ctx.exception))
        self.assertIn("no validated intelligence", str(ctx.exception))

    def test_f_insufficient_research_blocks(self):
        """TEST-F: insufficient research → hard_blocked → BLOCK."""
        with patch("pipeline.intelligence.bridge.run_topic_intelligence") as mock_intel:
            mock_intel.return_value = {
                "evaluated": [{
                    "score": {
                        "hard_blocked": True,
                        "block_reason": "LOW_EVIDENCE",
                        "total_score": 0.0,
                    },
                }],
            }
            result = run_intelligence_gate(
                self.tmp,
                _channel(),
                "Low evidence topic",
                use_mock_research=True,
            )
        verdict = evaluate_gate_result(result, context="test_f")
        self.assertNotEqual(verdict, GateVerdict.PASS)
        with self.assertRaises(RuntimeError):
            block_if_not_pass(verdict, context="test_f", allow_development_bypass=False)

    def test_h_valid_intelligence_continues(self):
        """TEST-H: valid intelligence + valid topic → CONTINUE (no block)."""
        result = run_intelligence_gate(
            self.tmp,
            _channel(),
            "Continue topic with mock research",
            use_mock_research=True,
        )
        verdict = evaluate_gate_result(result, context="test_h")
        block_if_not_pass(verdict, context="test_h", allow_development_bypass=False)
        self.assertEqual(verdict, GateVerdict.PASS)
        self.assertTrue(str(result.get("topic") or "").strip())

    def test_development_mode_allows_unvalidated_when_bypass(self):
        """Test/mock isolation: DEVELOPMENT may bypass block_if_not_pass when allowed."""
        os.environ["INTELLIGENCE_MODE"] = "DEVELOPMENT"
        verdict = evaluate_gate_result({"accepted": False, "reason": "UNKNOWN"})
        block_if_not_pass(verdict, context="dev", allow_development_bypass=True)

    def test_production_assert_allows_development_without_pass(self):
        """DEVELOPMENT mode: assert_production_intelligence_validated does not raise."""
        os.environ["INTELLIGENCE_MODE"] = "DEVELOPMENT"
        assert_production_intelligence_validated(passed=False, context="dev_mode")


class Task004PipelineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_MODE"] = "PRODUCTION"
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("INTELLIGENCE_MODE", None)
        os.environ.pop("INTELLIGENCE_RESEARCH_MODE", None)

    @patch("pipeline.video_pipeline._plan_niche_production_idempotent")
    @patch("pipeline.intelligence.bridge.pick_topic_from_reserve", return_value=None)
    @patch("pipeline.trending_search.find_trending_gadgets")
    def test_g_legacy_fallback_blocked_negative(self, mock_trend, mock_reserve, mock_plan):
        """TEST-G (NEGATIVE): legacy trending available but intelligence unavailable → BLOCK."""
        mock_trend.return_value = [{"name": "Legacy Gadget X"}]
        mock_plan.return_value = {"topic": "should-not-reach", "scenes": [{"text": "x"}]}

        from pipeline.video_pipeline import generate_video

        with self.assertRaises(RuntimeError) as ctx:
            generate_video(
                _channel(),
                video_type="short",
                topic="",
                work_dir=self.tmp,
            )
        msg = str(ctx.exception)
        self.assertIn(GATE_BLOCKED_MARKER, msg)
        mock_trend.assert_not_called()
        mock_plan.assert_not_called()

    @patch("pipeline.video_pipeline._plan_niche_production_idempotent")
    @patch("pipeline.intelligence.bridge.pick_topic_from_reserve", return_value=None)
    def test_pipeline_valid_topic_continues_to_director(self, mock_reserve, mock_plan):
        """TEST-A/H pipeline: validated topic reaches director planning."""
        class StopAfterDirector(Exception):
            pass

        mock_plan.side_effect = StopAfterDirector("director reached")

        from pipeline.video_pipeline import generate_video

        with self.assertRaises(StopAfterDirector):
            generate_video(
                _channel(),
                video_type="short",
                topic="Validated Topic With Mock Research",
                work_dir=self.tmp,
            )
        mock_plan.assert_called_once()


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\nAMP-001 TASK-004 TESTS: {passed} / {result.testsRun}")
    if not result.wasSuccessful():
        raise SystemExit(1)
