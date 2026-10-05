"""T004 — Job FSM unit tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.job_fsm import InvalidTransition, JobFSM, assert_transition, normalize_state


class JobFSMTests(unittest.TestCase):
    def test_happy_path(self):
        fsm = JobFSM(job_id="j1")
        for s in (
            "PLANNING",
            "SCRIPTING",
            "GENERATING",
            "VERIFYING",
            "ASSEMBLING",
            "READY",
            "UPLOADING",
            "PUBLISHED",
            "VERIFIED",
        ):
            fsm.transition(s, reason="ok")
        self.assertEqual(fsm.state, "VERIFIED")

    def test_rejects_skip(self):
        fsm = JobFSM()
        with self.assertRaises(InvalidTransition):
            fsm.transition("UPLOADING")

    def test_failed_retry(self):
        fsm = JobFSM()
        fsm.transition("PLANNING")
        fsm.transition("FAILED", reason="boom")
        fsm.transition("PLANNING", reason="retry")
        self.assertEqual(fsm.state, "PLANNING")

    def test_blocked_to_upload(self):
        fsm = JobFSM()
        fsm.transition("PLANNING")
        fsm.transition("SCRIPTING")
        fsm.transition("GENERATING")
        fsm.transition("VERIFYING")
        fsm.transition("ASSEMBLING")
        fsm.transition("READY")
        fsm.transition("UPLOADING")
        fsm.transition("BLOCKED", reason="captcha")
        fsm.transition("UPLOADING", reason="unlocked")
        self.assertEqual(fsm.state, "UPLOADING")

    def test_phase_alias(self):
        self.assertEqual(normalize_state("generate_short"), "GENERATING")
        self.assertEqual(normalize_state("cancelled"), "CANCELLED")
        ok, msg = assert_transition("READY", "UPLOADING")
        self.assertTrue(ok)
        ok2, _ = assert_transition("CREATED", "VERIFIED")
        self.assertFalse(ok2)

    def test_roundtrip_dict(self):
        fsm = JobFSM(job_id="x")
        fsm.transition("PLANNING")
        fsm2 = JobFSM.from_dict(fsm.to_dict())
        self.assertEqual(fsm2.state, "PLANNING")
        self.assertEqual(fsm2.job_id, "x")


if __name__ == "__main__":
    unittest.main()
