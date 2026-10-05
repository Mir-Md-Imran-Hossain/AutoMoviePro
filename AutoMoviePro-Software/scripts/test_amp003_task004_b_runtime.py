#!/usr/bin/env python3
"""AMP-003 T004-B — Production runtime boundary (B-3)."""
from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.scene_runtime import SceneValidationError, assert_production_scenes_validated, VALIDATED_SCENES_FILE


def _valid_plan() -> dict:
    return {
        "topic": "Lost Library",
        "title": "Lost Library",
        "language": "en",
        "scenes": [
            {
                "element": "intro",
                "narration": "The great library held thousands of scrolls from across the ancient world.",
                "keyword_triggers": ["library"],
            }
        ],
    }


class T004BRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_valid_scene_continues_handoff(self):
        scenes, handoff = assert_production_scenes_validated(
            _valid_plan(), job_id="job-rt", work_dir=self.tmp
        )
        self.assertEqual(len(scenes), 1)
        self.assertTrue(handoff[0].get("canonical_scene_id"))
        self.assertTrue((self.tmp / VALIDATED_SCENES_FILE).is_file())

    def test_invalid_scene_blocks(self):
        bad = _valid_plan()
        bad["scenes"][0]["narration"] = "tiny"
        with self.assertRaises(SceneValidationError):
            assert_production_scenes_validated(bad, job_id="job-rt")

    def test_malformed_plan_blocks(self):
        with self.assertRaises(SceneValidationError):
            assert_production_scenes_validated({"scenes": []}, job_id="job-rt")

    def test_video_pipeline_imports_boundary(self):
        from pipeline import video_pipeline

        src = inspect.getsource(video_pipeline.generate_video)
        self.assertIn("assert_production_scenes_validated", src)
        self.assertIn("scene_contract_blocked", src)

    def test_validation_failure_message_fail_closed(self):
        bad = _valid_plan()
        bad["scenes"][0].pop("narration")
        try:
            assert_production_scenes_validated(bad, job_id="x")
            self.fail("expected SceneValidationError")
        except SceneValidationError as exc:
            self.assertIn("scene", str(exc).lower())


if __name__ == "__main__":
    unittest.main()
