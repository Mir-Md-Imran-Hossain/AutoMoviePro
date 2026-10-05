"""T001 — Dialogue uniqueness regression (no network)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.dialogue_uniqueness import (
    detect_dialogue_uniqueness,
    force_unique_scene_narrations,
    pair_overlap_ratio,
)
from pipeline.niche_director import _fallback_history_plan
from pipeline.av_quality_gates import evaluate_master_shippable


class DialogueUniquenessTests(unittest.TestCase):
    def test_topic_mask_prevents_false_fail_on_shared_proper_noun(self):
        topic = "Lost Library of Alexandria"
        scenes = [
            {"narration": f"Tonight we dig into {topic} — vanished knowledge."},
            {"narration": f"Culture around {topic} left rituals in the ruins."},
        ]
        raw = detect_dialogue_uniqueness(scenes)
        masked = detect_dialogue_uniqueness(scenes, topic=topic)
        # Masked must not treat topic-name-only overlap as critical when lines differ
        self.assertTrue(masked["passed"], masked)
        self.assertLessEqual(masked["max_overlap"], 0.36)

    def test_true_duplicate_still_fails(self):
        scenes = [
            {"narration": "Ash layers dated by carbon samples under a collapsed aisle near the east wing."},
            {"narration": "Ash layers dated by carbon samples under a collapsed aisle near the east wing."},
        ]
        r = detect_dialogue_uniqueness(scenes, topic="Anything")
        self.assertFalse(r["passed"])
        self.assertIn("repeated_dialogue", r["critical_issues"])

    def test_force_kills_shift_to_boilerplate(self):
        topic = "Lost Library of Alexandria"
        scenes = [
            {
                "element": "technique",
                "narration": (
                    f"Shift to {topic} technique number 8: researchers highlight "
                    "ash layers dated by carbon samples under a collapsed aisle."
                ),
            },
            {
                "element": "outro",
                "narration": (
                    f"Shift to {topic} outro number 9: researchers highlight "
                    "bronze stylus tips bent from heavy papyrus use."
                ),
            },
        ]
        fixed = force_unique_scene_narrations(scenes, topic=topic)
        for sc in fixed:
            n = (sc.get("narration") or "").lower()
            self.assertNotIn("shift to", n)
            self.assertNotIn("researchers highlight", n)
        gate = detect_dialogue_uniqueness(fixed, topic=topic)
        self.assertTrue(gate["passed"], gate)

    def test_history_fallback_plan_unique(self):
        plan = _fallback_history_plan(
            "Ancient Civilizations",
            "Lost Library of Alexandria",
            "short",
            58,
            "TestChannel",
        )
        topic = str(plan.get("topic") or "")
        scenes = list(plan.get("scenes") or [])
        raw = detect_dialogue_uniqueness(scenes)
        masked = detect_dialogue_uniqueness(scenes, topic=topic)
        self.assertTrue(raw["passed"], raw)
        self.assertTrue(masked["passed"], masked)
        forced = force_unique_scene_narrations([dict(s) for s in scenes], topic=topic)
        self.assertTrue(detect_dialogue_uniqueness(forced, topic=topic)["passed"])
        self.assertTrue(detect_dialogue_uniqueness(forced)["passed"])

    def test_ship_gate_uses_topic(self):
        topic = "Lost Library of Alexandria"
        # Lines that fail without topic mask but pass with topic (historical failure mode)
        scenes = [
            {
                "element": "technique",
                "narration": (
                    f"The technique behind {topic} was not luck — measured cuts, "
                    "aligned skies, and patient labor."
                ),
            },
            {
                "element": "culture",
                "narration": (
                    f"Culture around {topic} left rituals, symbols, and social ranks "
                    "you can still read in the ruins."
                ),
            },
        ]
        ship = evaluate_master_shippable(
            media=None,
            scenes=scenes,
            niche="Ancient Civilizations",
            topic=topic,
        )
        self.assertTrue(ship.get("ok"), ship)
        self.assertFalse(ship.get("unshippable"), ship)
        crit = ship.get("critical_issues") or []
        self.assertNotIn("repeated_dialogue", crit)

    def test_pad_fillers_not_cloned(self):
        plan = _fallback_history_plan(
            "Ancient Civilizations",
            "Göbekli Tepe",
            "short",
            90,  # force pad beyond base beats
            "Ch",
        )
        narrs = [str(s.get("narration") or "") for s in plan["scenes"]]
        for n in narrs:
            self.assertNotIn("Another distinct beat about", n)
            self.assertNotIn("Shift to", n)
        # pairwise uniqueness after force
        topic = plan["topic"]
        fixed = force_unique_scene_narrations([dict(s) for s in plan["scenes"]], topic=topic)
        self.assertTrue(detect_dialogue_uniqueness(fixed, topic=topic)["passed"])


if __name__ == "__main__":
    unittest.main()
