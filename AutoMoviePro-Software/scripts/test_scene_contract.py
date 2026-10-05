"""T005 — SceneContract + preflight tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.scene_contract import (
    attach_contracts_to_plan,
    build_scene_contract,
    plan_allows_generation,
    preflight_scene_contract,
)
from pipeline.niche_director import _fallback_history_plan


class SceneContractTests(unittest.TestCase):
    def test_build_and_pass(self):
        sc = {
            "element": "discovery",
            "narration": "When excavators opened the first trenches, tool marks forced harder questions.",
            "visual_prompt": "excavation trench soil layers continuous motion",
            "keyword_triggers": ["excavation", "trench", "tool"],
        }
        c = build_scene_contract(sc, scene_id=2, topic="Lost Library of Alexandria")
        self.assertEqual(c["claim_id"], "C02")
        self.assertTrue(c["primary_claim"])
        pf = preflight_scene_contract(c)
        # After build, shot fields filled — should PASS
        self.assertEqual(pf["verdict"], "PASS", pf)
        self.assertTrue(pf["allow_api"])

    def test_fail_missing_dialogue(self):
        c = build_scene_contract({"element": "intro", "narration": ""}, scene_id=0, topic="X")
        pf = preflight_scene_contract(c)
        self.assertEqual(pf["verdict"], "FAIL")
        self.assertFalse(pf["allow_api"])

    def test_attach_history_plan(self):
        plan = _fallback_history_plan(
            "Ancient Civilizations",
            "Lost Library of Alexandria",
            "short",
            58,
            "Ch",
        )
        plan2 = attach_contracts_to_plan(plan)
        self.assertTrue(plan2.get("scene_contract_report", {}).get("passed"), plan2.get("scene_contract_report"))
        self.assertTrue(plan_allows_generation(plan2))
        for sc in plan2["scenes"]:
            self.assertIn("SUBJECT:", sc.get("visual_prompt") or "")
            self.assertIn("scene_contract", sc)

    def test_unknown_not_pass(self):
        c = {
            "scene_id": 1,
            "claim_id": "C01",
            "dialogue": "Quantum foam rearranges Babylonian copper alloys overnight.",
            "primary_claim": "Quantum foam rearranges Babylonian copper alloys overnight",
            "visual_evidence": {"must_show": ["cat"], "should_show": [], "must_not_show": []},
            "shot": {
                "subject": "cat",
                "action": "walking",
                "environment": "room",
                "camera": "static",
                "lighting": "soft",
                "composition": "center",
            },
            "prompt_fields": {"visual_prompt": "a cat walking in a room"},
        }
        pf = preflight_scene_contract(c)
        self.assertEqual(pf["verdict"], "UNKNOWN")
        self.assertFalse(pf["allow_api"])


if __name__ == "__main__":
    unittest.main()
