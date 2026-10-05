"""Protocol gap-closure tests for §01–155 remaining modules."""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.human_speech_engine import run_human_speech_pipeline, attach_speech_to_plan
from pipeline.retention_architecture import attach_retention_to_plan, retention_blueprint
from pipeline.resource_locks import acquire, release, is_held, LockError
from pipeline.orchestrator import enqueue, next_job, snapshot
from pipeline.comm_fsm import CommentFSM, MessageFSM, is_sensitive_message, InvalidCommTransition
from pipeline.remote_job_store import save_remote_job, get_remote_job
from pipeline.loop_detector import LoopDetector, classify_watchdog_state
from pipeline.browser_manager import BrowserManager
from pipeline.golden_harness import run_golden_suite, inject_failure, expected_recovery
from pipeline.motion_priority import select_motion_fallback, parallax_lite_plan
from pipeline.niche_director import _fallback_history_plan


class ProtocolGapTests(unittest.TestCase):
    def test_human_speech_pipeline(self):
        out = run_human_speech_pipeline(
            "Lost Library of Alexandria",
            fact_claims=["Ash layers dated under aisle three."],
        )
        self.assertTrue(out["story"]["hook"])
        self.assertGreaterEqual(len(out["human"]["lines"]), 5)
        self.assertTrue(out["performance"]["beats"])

    def test_retention_windows(self):
        bp = retention_blueprint("short")
        self.assertEqual(bp["windows"][0]["end_sec"], 2)
        self.assertEqual(bp["windows"][1]["end_sec"], 5)
        plan = attach_retention_to_plan(_fallback_history_plan("Ancient Civilizations", "X", "short", 58, "Ch"))
        self.assertEqual(plan["scenes"][0]["retention"]["role"], "pattern_interrupt")

    def test_resource_locks(self):
        key = f"t{time.time()}"
        acquire("generation", key, owner="a", ttl_sec=30)
        self.assertTrue(is_held("generation", key))
        with self.assertRaises(LockError):
            acquire("generation", key, owner="b", ttl_sec=30)
        self.assertTrue(release("generation", key, owner="a"))

    def test_orchestrator_priority(self):
        enqueue("health", priority="P5", payload={})
        enqueue("user_gen", priority="P0", payload={})
        j = next_job()
        self.assertEqual(j["priority"], "P0")
        self.assertIn("queued", snapshot())

    def test_comment_message_fsm(self):
        c = CommentFSM(comment_id="1")
        c.transition("CLASSIFIED")
        c.transition("DRAFT")
        c.transition("VALIDATE")
        c.transition("SEND")
        c.transition("VERIFY")
        c.transition("VERIFIED")
        m = MessageFSM(message_id="m1", sensitive=is_sensitive_message("need refund payment"))
        m.transition("CLASSIFIED")
        with self.assertRaises(InvalidCommTransition):
            m.transition("NEEDS_REPLY")  # sensitive should escalate from CLASSIFIED
        m2 = MessageFSM(message_id="m2", sensitive=True)
        m2.transition("CLASSIFIED")
        m2.transition("ESCALATE")

    def test_remote_job_store(self):
        with tempfile.TemporaryDirectory() as td:
            save_remote_job(Path(td), generation_key="k1", remote_job_id="vid123", provider="agnes")
            self.assertEqual(get_remote_job(Path(td), "k1")["remote_job_id"], "vid123")

    def test_loop_detector(self):
        d = LoopDetector(window=6, repeat_threshold=3)
        self.assertFalse(d.observe("a")["loop_detected"])
        self.assertFalse(d.observe("a")["loop_detected"])
        self.assertTrue(d.observe("a")["loop_detected"])
        self.assertEqual(d.observe("a")["state"], "LOOP_DETECTED")
        self.assertEqual(classify_watchdog_state({"hung": True, "silent_sec": 10, "deadline_sec": 5}), "STALLED")
        self.assertEqual(classify_watchdog_state({"hung": True, "silent_sec": 20, "deadline_sec": 5}), "HANG_DETECTED")

    def test_browser_manager(self):
        bm = BrowserManager(platform="youtube", channel_id=1)
        bm.session_ready()
        bm.authenticate(storage_state="x")
        bm.navigate("https://youtube.com")
        bm.capture("before")
        self.assertTrue(bm.health()["session_alive"])

    def test_golden_and_injection(self):
        g = run_golden_suite(5)
        self.assertTrue(g["passed"], g)
        self.assertEqual(expected_recovery("api_429"), "BACKOFF_RETRY")
        self.assertEqual(expected_recovery("duplicate_upload"), "ABORT_NO_RETRY")
        self.assertTrue(inject_failure("browser_crash")["injected"])

    def test_motion_priority(self):
        self.assertEqual(select_motion_fallback({"ken_burns": True}), "ken_burns")
        self.assertEqual(select_motion_fallback({"real_video": True, "ken_burns": True}), "real_video")
        self.assertEqual(parallax_lite_plan()["method"], "parallax_lite")

    def test_attach_speech_plan(self):
        plan = _fallback_history_plan("Ancient Civilizations", "Library", "short", 58, "Ch")
        out = attach_speech_to_plan(plan)
        self.assertIn("human_speech_engine", out)


if __name__ == "__main__":
    unittest.main()
