"""BUILD-02 pipeline contract wiring tests — offline, no external APIs."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.enums import Verdict
from pipeline.contract_wiring import (
    detect_orphans,
    enrich_queue_payload,
    wire_audio_plan,
    wire_fact_pack,
    wire_pipeline_from_plan,
    wire_research,
    wire_sample_history_pipeline,
    wire_script,
    wire_scenes_from_plan,
    wire_subtitle_plan,
    wire_topic,
    wire_visual_plan,
)
from pipeline.contract_wiring.core import CONTRACT_LAYER_VERSION
from pipeline.fact_pack import build_fact_pack
from pipeline.niche_director import _fallback_history_plan
from pipeline.orchestrator import enqueue


class Stage01TopicTests(unittest.TestCase):
    def test_legacy_topic_to_canonical(self):
        r = wire_topic({"topic": "Chernobyl Disaster", "video_type": "short"}, job_id="job-t1")
        self.assertTrue(r.passed, r.error)
        self.assertEqual(r.canonical.title, "Chernobyl Disaster")
        self.assertTrue(r.canonical.id)

    def test_invalid_topic_fails(self):
        r = wire_topic({"video_type": "short"}, job_id="job-t2")
        self.assertFalse(r.passed)

    def test_topic_serialization(self):
        r = wire_topic({"topic": "Test"}, job_id="j")
        blob = r.canonical.model_dump(mode="json")
        self.assertEqual(blob["schema_version"], "1.0.0")


class Stage02ResearchTests(unittest.TestCase):
    def test_research_from_notes(self):
        t = wire_topic({"topic": "Alexandria"}, job_id="j").canonical
        r = wire_research({"research_notes": "Library held scrolls. Scholars visited from afar."}, topic=t, job_id="j")
        self.assertTrue(r.passed)
        self.assertGreaterEqual(len(r.canonical.evidence), 1)
        self.assertEqual(r.canonical.evidence[0].topic_id, t.id)

    def test_empty_research_allowed(self):
        t = wire_topic({"topic": "Empty research test"}, job_id="j").canonical
        r = wire_research({}, topic=t, job_id="j")
        self.assertTrue(r.passed)
        self.assertEqual(r.canonical.status.value, "requested")


class Stage03FactPackTests(unittest.TestCase):
    def test_factpack_chain(self):
        t = wire_topic({"topic": "Chernobyl"}, job_id="j").canonical
        legacy = build_fact_pack("Chernobyl", notes="Reactor four exploded.")
        r = wire_fact_pack(legacy, topic=t, job_id="j")
        self.assertTrue(r.passed)
        self.assertEqual(r.canonical.topic_id, t.id)
        self.assertGreaterEqual(len(r.canonical.claims), 1)


class Stage04ScriptTests(unittest.TestCase):
    def test_script_from_plan(self):
        plan = _fallback_history_plan("Ancient Civilizations", "Göbekli Tepe", "short", 58, "Ch")
        t = wire_topic(plan, job_id="j").canonical
        fp = wire_fact_pack(build_fact_pack(t.title), topic=t, job_id="j").canonical
        r = wire_script(plan, topic=t, fact_pack=fp, job_id="j")
        self.assertTrue(r.passed)
        self.assertGreaterEqual(len(r.canonical.sections), 1)
        dlg = r.canonical.sections[0].dialogues[0]
        self.assertTrue(dlg.id)
        self.assertEqual(dlg.script_id, r.canonical.id)


class Stage05SceneTests(unittest.TestCase):
    def test_scene_wiring_preserves_legacy_contract(self):
        plan = _fallback_history_plan("Ancient Civilizations", "Lost Library", "short", 58, "Ch")
        t = wire_topic(plan, job_id="j").canonical
        fp = wire_fact_pack(build_fact_pack(t.title), topic=t, job_id="j").canonical
        script = wire_script(plan, topic=t, fact_pack=fp, job_id="j").canonical
        scenes = wire_scenes_from_plan(plan, script=script, job_id="j")
        self.assertGreaterEqual(len(scenes), 1)
        self.assertTrue(all(s.passed for s in scenes), [s.error for s in scenes if not s.passed])
        sc = scenes[0].canonical
        self.assertIsNotNone(sc.visual_plan)
        self.assertIsNotNone(sc.audio_plan)
        self.assertIsNotNone(sc.subtitle_plan)


class Stage06to09PlanTests(unittest.TestCase):
    def test_visual_audio_subtitle_plans(self):
        plan = _fallback_history_plan("History", "Stonehenge", "short", 58, "Ch")
        t = wire_topic(plan, job_id="j").canonical
        fp = wire_fact_pack(build_fact_pack(t.title), topic=t, job_id="j").canonical
        script = wire_script(plan, topic=t, fact_pack=fp, job_id="j").canonical
        scenes = wire_scenes_from_plan(plan, script=script, job_id="j")
        sc = scenes[0].canonical
        self.assertTrue(wire_visual_plan(sc, job_id="j").passed)
        self.assertTrue(wire_audio_plan(sc, job_id="j").passed)
        self.assertTrue(wire_subtitle_plan(sc, job_id="j").passed)


class IntegrationTraceTests(unittest.TestCase):
    def test_full_pipeline_trace(self):
        trace = wire_sample_history_pipeline(job_id="integration-1")
        self.assertTrue(trace.passed, trace.errors)
        self.assertIsNone(trace.stopped_at)

    def test_orphan_detection_clean(self):
        trace = wire_sample_history_pipeline(job_id="integration-2")
        report = detect_orphans(trace)
        self.assertTrue(report.clean, report.orphans)

    def test_failure_propagation_stops(self):
        trace = wire_pipeline_from_plan({"topic": "Bad", "scenes": []}, job_id="fail-1")
        self.assertFalse(trace.passed)
        self.assertEqual(trace.stopped_at, "scene")

    def test_malformed_input_stops_at_topic(self):
        trace = wire_pipeline_from_plan({}, job_id="fail-2")
        self.assertFalse(trace.passed)
        self.assertEqual(trace.stopped_at, "topic")


class OrchestratorBridgeTests(unittest.TestCase):
    def test_enrich_queue_payload(self):
        out = enrich_queue_payload({"topic": "x"})
        self.assertEqual(out["contract_meta"]["contract_layer"], CONTRACT_LAYER_VERSION)

    def test_enqueue_adds_contract_meta(self):
        job = enqueue("generate", payload={"topic": "test"})
        self.assertIn("contract_meta", job["payload"])


class FailureInjectionTests(unittest.TestCase):
    def test_invalid_contract_version_on_topic(self):
        from domain.topic import Topic
        with self.assertRaises(Exception):
            Topic(title="x", schema_version="not-semver")

    def test_validation_fail_does_not_pass_as_success(self):
        r = wire_topic({}, job_id="x")
        self.assertFalse(r.passed)
        self.assertNotEqual(r.output_validation.verdict, Verdict.PASS)


if __name__ == "__main__":
    unittest.main()
