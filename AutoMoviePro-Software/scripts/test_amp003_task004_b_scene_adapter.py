#!/usr/bin/env python3
"""AMP-003 T004-B — Legacy dict → canonical Scene adapter (B-2)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.adapters import script_from_plan
from pipeline.scene_contract import attach_contracts_to_plan
from pipeline.scene_runtime import SceneValidationError, assert_production_scenes_validated, build_canonical_scene


def _valid_plan(**overrides) -> dict:
    base = {
        "topic": "Lost Library",
        "title": "Lost Library",
        "language": "en",
        "scenes": [
            {
                "element": "intro",
                "narration": "The great library held thousands of scrolls from across the ancient world.",
                "keyword_triggers": ["library", "scrolls"],
            },
            {
                "element": "discovery",
                "narration": "Archaeologists found ash layers under a collapsed reading hall aisle.",
                "keyword_triggers": ["archaeology"],
            },
        ],
    }
    base.update(overrides)
    return base


class T004BAdapterTests(unittest.TestCase):
    def test_legacy_valid_converts(self):
        scenes, handoff = assert_production_scenes_validated(_valid_plan(), job_id="job-1")
        self.assertEqual(len(scenes), 2)
        self.assertTrue(all(h.get("_validated") for h in handoff))

    def test_legacy_incomplete_rejected(self):
        plan = _valid_plan(scenes=[{"element": "intro"}])
        with self.assertRaises(SceneValidationError):
            assert_production_scenes_validated(plan, job_id="job-1")

    def test_legacy_malformed_rejected(self):
        plan = _valid_plan(scenes=[{"element": "intro", "narration": "short"}])
        with self.assertRaises(SceneValidationError):
            assert_production_scenes_validated(plan, job_id="job-1")

    def test_invalid_duration_rejected(self):
        plan = _valid_plan()
        plan["scenes"][0]["start_hint_s"] = 10
        plan["scenes"][0]["end_hint_s"] = 5
        with self.assertRaises(SceneValidationError):
            assert_production_scenes_validated(plan, job_id="job-1")

    def test_missing_visual_via_empty_narration(self):
        plan = _valid_plan(scenes=[{"element": "intro", "narration": ""}])
        with self.assertRaises(SceneValidationError):
            assert_production_scenes_validated(plan, job_id="job-1")

    def test_wrong_job_binding_preserved(self):
        scenes, _ = assert_production_scenes_validated(_valid_plan(), job_id="job-A")
        self.assertEqual(scenes[0].metadata.get("job_id"), "job-A")

    def test_build_canonical_requires_dialogue(self):
        plan = attach_contracts_to_plan(_valid_plan())
        script = script_from_plan(plan)
        row = plan["scenes"][0]
        contract = row["scene_contract"]
        contract["dialogue"] = ""
        with self.assertRaises(SceneValidationError):
            build_canonical_scene(row, contract, script=script, scene_index=0, job_id="j")

    def test_serialization_roundtrip(self):
        import json
        import tempfile

        tmp = Path(tempfile.mkdtemp())
        scenes, _ = assert_production_scenes_validated(_valid_plan(), job_id="job-ser", work_dir=tmp)
        raw = json.loads((tmp / "VALIDATED_SCENES.json").read_text(encoding="utf-8"))
        loaded = __import__("domain.scene", fromlist=["Scene"]).Scene.from_json_dict(raw["scenes"][0])
        self.assertEqual(loaded.id, scenes[0].id)
        self.assertEqual(loaded.scene_index, scenes[0].scene_index)
        self.assertEqual(loaded.dialogue_id, scenes[0].dialogue_id)


if __name__ == "__main__":
    unittest.main()
