#!/usr/bin/env python3
"""AMP-003 TASK-002 — Pipeline Contract Wiring + Orchestration."""
from __future__ import annotations

import inspect
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.enums import Verdict
from pipeline.contract_wiring import (
    CANONICAL_STAGE_ORDER,
    ProductionWiringError,
    assert_production_plan_wiring,
    detect_orphans,
    enrich_queue_payload,
    load_work_trace,
    persist_work_trace,
    stage_order_valid,
    validate_production_plan_wiring,
    wire_pipeline_from_plan,
    wire_sample_history_pipeline,
    wire_topic,
)
from pipeline.contract_wiring.core import CONTRACT_LAYER_VERSION
from pipeline.niche_director import _fallback_history_plan
from pipeline.orchestrator import enqueue


def _valid_plan() -> dict:
    return _fallback_history_plan(
        "Ancient Civilizations",
        "Lost Library of Alexandria",
        "short",
        58,
        "TestChannel",
    )


class T002ValidPipelineTests(unittest.TestCase):
    def test_01_valid_pipeline_full_trace(self):
        trace = wire_sample_history_pipeline(job_id="t002-valid")
        self.assertTrue(trace.passed, trace.errors)
        self.assertIsNone(trace.stopped_at)
        self.assertIn("topic", trace.executed_stages)
        self.assertIn("publication", trace.executed_stages)

    def test_02_stage_order_canonical(self):
        trace = wire_sample_history_pipeline(job_id="t002-order")
        self.assertTrue(stage_order_valid(trace.executed_stages), trace.executed_stages)

    def test_03_production_bridge_persists_trace(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            plan = _valid_plan()
            trace = validate_production_plan_wiring(
                plan,
                job_id="t002-persist",
                work_dir=tmp,
                research_notes="Library held scrolls.",
            )
            self.assertTrue(trace.passed, trace.errors)
            path = tmp / "CONTRACT_WIRING_TRACE.json"
            self.assertTrue(path.is_file())
            loaded = load_work_trace(tmp)
            self.assertTrue(loaded.get("passed"))
            self.assertIn("executed_stages", loaded)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class T002NegativeTests(unittest.TestCase):
    def test_04_invalid_contract_stops_at_topic(self):
        trace = wire_pipeline_from_plan({}, job_id="t002-bad-topic")
        self.assertFalse(trace.passed)
        self.assertEqual(trace.stopped_at, "topic")

    def test_05_missing_upstream_scenes_stops(self):
        trace = wire_pipeline_from_plan({"topic": "No scenes plan"}, job_id="t002-noscene")
        self.assertFalse(trace.passed)
        self.assertIn(trace.stopped_at, ("scene", "script"))
        self.assertNotIn("render", trace.executed_stages)

    def test_06_failed_upstream_blocks_downstream(self):
        trace = wire_pipeline_from_plan({"topic": "Bad", "scenes": []}, job_id="t002-fail")
        self.assertFalse(trace.passed)
        self.assertNotIn("render", trace.executed_stages)

    def test_07_malformed_payload_unknown_field_on_model(self):
        from domain.topic import Topic

        with self.assertRaises(Exception):
            Topic.model_validate({"title": "x", "schema_version": "1.0.0", "rogue": True})

    def test_08_assert_production_raises_on_invalid(self):
        with self.assertRaises(ProductionWiringError) as ctx:
            assert_production_plan_wiring({"scenes": []}, job_id="t002-assert")
        self.assertIsNotNone(ctx.exception.trace.stopped_at)


class T002FailurePropagationTests(unittest.TestCase):
    def test_09_input_validation_does_not_execute_stage(self):
        r = wire_topic({}, job_id="t002-noinput")
        self.assertFalse(r.passed)
        self.assertIsNone(r.canonical)
        self.assertEqual(r.output_validation.verdict, Verdict.FAIL)

    def test_10_upstream_failure_verdict_not_pass(self):
        r = wire_topic({}, job_id="t002-upfail")
        self.assertNotEqual(r.output_validation.verdict, Verdict.PASS)


class T002BypassAuditTests(unittest.TestCase):
    def test_11_video_pipeline_calls_contract_gate(self):
        src = Path(ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("assert_production_plan_wiring", src)

    def test_12_enqueue_adds_contract_meta_not_bypass(self):
        job = enqueue("generate", payload={"topic": "enqueue wiring test"})
        self.assertEqual(job["payload"]["contract_meta"]["contract_layer"], CONTRACT_LAYER_VERSION)

    def test_13_orchestrator_enrich_is_production_path(self):
        src = Path(ROOT / "pipeline" / "orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("enrich_queue_payload", src)


class T002StateTraceabilityTests(unittest.TestCase):
    def test_14_topic_to_script_identity_chain(self):
        trace = wire_sample_history_pipeline(job_id="t002-identity")
        topic_id = trace.topic.canonical.id
        self.assertEqual(trace.fact_pack.canonical.topic_id, topic_id)
        self.assertEqual(trace.script.canonical.topic_id, topic_id)

    def test_15_orphan_detection_clean(self):
        trace = wire_sample_history_pipeline(job_id="t002-orphan")
        report = detect_orphans(trace)
        self.assertTrue(report.clean, report.orphans)

    def test_16_resume_trace_reload(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            plan = _valid_plan()
            validate_production_plan_wiring(plan, job_id="t002-resume", work_dir=tmp)
            reloaded = load_work_trace(tmp)
            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded["job_id"], "t002-resume")
            stages = reloaded.get("executed_stages") or []
            self.assertTrue(stage_order_valid(stages), stages)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class T002RuntimeOrchestrationTests(unittest.TestCase):
    def test_17_exact_stage_order_markers(self):
        trace = wire_sample_history_pipeline(job_id="t002-markers")
        idx_topic = trace.executed_stages.index("topic")
        idx_research = trace.executed_stages.index("research")
        idx_script = trace.executed_stages.index("script")
        idx_render = trace.executed_stages.index("render")
        self.assertLess(idx_topic, idx_research)
        self.assertLess(idx_research, idx_script)
        self.assertLess(idx_script, idx_render)

    def test_18_canonical_stage_order_constant(self):
        self.assertEqual(CANONICAL_STAGE_ORDER[0], "topic")
        self.assertEqual(CANONICAL_STAGE_ORDER[-1], "publication")

    def test_19_production_bridge_integration_on_plan(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            trace = assert_production_plan_wiring(
                _valid_plan(),
                job_id="t002-integ",
                work_dir=tmp,
            )
            self.assertTrue(trace.passed)
            blob = json.loads((tmp / "CONTRACT_WIRING_TRACE.json").read_text(encoding="utf-8"))
            self.assertTrue(blob["stages"]["script"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class T002ContractBoundaryTests(unittest.TestCase):
    def test_20_wire_topic_has_schema_version(self):
        r = wire_topic({"topic": "Boundary test"}, job_id="t002-bound")
        self.assertTrue(r.passed)
        self.assertEqual(r.canonical.schema_version, "1.0.0")

    def test_21_stage_result_has_validation(self):
        r = wire_topic({"topic": "Validation envelope"}, job_id="t002-val")
        self.assertTrue(r.input_validation.passed)
        self.assertTrue(r.output_validation.passed)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\nAMP-003 TASK-002 TESTS: {passed} / {result.testsRun}")
    if not result.wasSuccessful():
        raise SystemExit(1)
