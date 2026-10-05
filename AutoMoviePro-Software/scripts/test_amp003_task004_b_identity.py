#!/usr/bin/env python3
"""AMP-003 T004-B — Scene identity + ordering integrity (B-4)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.adapters import script_from_plan
from pipeline.scene_contract import attach_contracts_to_plan
from pipeline.scene_runtime import SceneValidationError, assert_production_scenes_validated, compute_scene_identity_fingerprint


def _plan(n: int = 3) -> dict:
    scenes = []
    for i in range(n):
        scenes.append(
            {
                "element": f"beat{i}",
                "narration": f"Scene {i} narration about ancient library evidence number {i}.",
                "keyword_triggers": [f"kw{i}"],
            }
        )
    return {"topic": "Library", "title": "Library", "language": "en", "scenes": scenes}


class T004BIdentityTests(unittest.TestCase):
    def test_unique_scene_ids(self):
        scenes, _ = assert_production_scenes_validated(_plan(3), job_id="job-id")
        ids = [s.id for s in scenes]
        self.assertEqual(len(ids), len(set(ids)))

    def test_contiguous_ordering(self):
        scenes, _ = assert_production_scenes_validated(_plan(3), job_id="job-id")
        self.assertEqual([s.scene_index for s in scenes], [0, 1, 2])

    def test_dialogue_binding_unique(self):
        scenes, _ = assert_production_scenes_validated(_plan(2), job_id="job-id")
        dids = [s.dialogue_id for s in scenes]
        self.assertEqual(len(dids), len(set(dids)))

    def test_cross_dialogue_contamination_blocked(self):
        plan = attach_contracts_to_plan(_plan(2))
        script = script_from_plan(plan)
        from pipeline.scene_runtime import build_canonical_scene, _assert_identity_integrity
        from domain.adapters import scene_from_legacy_contract

        s0 = build_canonical_scene(
            plan["scenes"][0],
            plan["scenes"][0]["scene_contract"],
            script=script,
            scene_index=0,
            job_id="j",
        )
        s1 = build_canonical_scene(
            plan["scenes"][1],
            plan["scenes"][1]["scene_contract"],
            script=script,
            scene_index=1,
            job_id="j",
        )
        s1.dialogue_id = s0.dialogue_id
        with self.assertRaises(SceneValidationError):
            _assert_identity_integrity([s0, s1], script)

    def test_fingerprint_stable_same_input(self):
        scenes, _ = assert_production_scenes_validated(_plan(1), job_id="job-fp")
        fp1 = compute_scene_identity_fingerprint(scenes[0], job_id="job-fp")
        fp2 = compute_scene_identity_fingerprint(scenes[0], job_id="job-fp")
        self.assertEqual(fp1, fp2)

    def test_fingerprint_changes_on_dialogue_change(self):
        p1 = _plan(1)
        p2 = _plan(1)
        p2["scenes"][0]["narration"] = "Completely different narration about another ancient topic entirely."
        s1, _ = assert_production_scenes_validated(p1, job_id="job-fp")
        s2, _ = assert_production_scenes_validated(p2, job_id="job-fp")
        fp1 = compute_scene_identity_fingerprint(s1[0], job_id="job-fp")
        fp2 = compute_scene_identity_fingerprint(s2[0], job_id="job-fp")
        self.assertNotEqual(fp1, fp2)


if __name__ == "__main__":
    unittest.main()
