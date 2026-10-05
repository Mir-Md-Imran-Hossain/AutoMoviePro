"""Comprehensive unit & integration tests for Step 5: Industrial Scriptwriting & Local Agent QA.
Standard library unittest implementation (zero external dependency).

Tests:
- Short vs. Long form script generation
- Islamic greetings and closing etiquette preservation
- Social CTA scene presence
- Local agent inspection, pacing audit & robotic filler auto-repair
- Surgical single-scene regeneration (Quota Saver)
"""
import os
import sys
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.script_engine import ProductionScript, ScriptEngine, ScriptScene


class TestScriptEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ScriptEngine()

    def test_short_form_script_generation(self):
        """Generates a fast-paced short script between 50-70 seconds."""
        script = self.engine.generate_script(
            topic_title="5 AI Inventions of 2026",
            niche="Technology & AI Innovations",
            video_format="short",
            language="bn",
        )
        self.assertEqual(script.video_format, "short")
        self.assertGreaterEqual(len(script.scenes), 5)
        self.assertLessEqual(len(script.scenes), 9)
        self.assertGreaterEqual(script.total_estimated_duration_sec, 40.0)
        self.assertLessEqual(script.total_estimated_duration_sec, 85.0)

    def test_long_form_script_generation(self):
        """Generates a structured long-form script with extended scenes."""
        script = self.engine.generate_script(
            topic_title="The Rise and Fall of the Ottoman Empire",
            niche="World History & Geopolitics",
            video_format="long",
            language="en",
        )
        self.assertEqual(script.video_format, "long")
        self.assertGreaterEqual(len(script.scenes), 10)
        self.assertGreaterEqual(script.total_estimated_duration_sec, 180.0)

    def test_islamic_greetings_and_closing_preservation(self):
        """Ensures Islamic greetings and closings are included in scene 1 and closing scene."""
        script = self.engine.generate_script(
            topic_title="Life Lessons from Islamic History",
            niche="Islamic History & Moral Stories",
            video_format="short",
            language="bn",
            include_islamic_touch=True,
        )
        first_scene = script.scenes[0]
        self.assertIn("আসসালামু আলাইকুম", first_scene.narration)

        last_scene = script.scenes[-1]
        self.assertIn("আল্লাহ", last_scene.narration)

    def test_social_cta_scene(self):
        """Verifies presence of the social subscription call-to-action scene."""
        script = self.engine.generate_script(
            topic_title="Dopamine Detox Habits",
            niche="Motivation & Self Improvement",
            video_format="short",
            language="bn",
            include_social_cta=True,
        )
        cta_scenes = [s for s in script.scenes if s.hook_type == "cta"]
        self.assertEqual(len(cta_scenes), 1)
        self.assertIn("সাবস্ক্রাইব", cta_scenes[0].narration)

    def test_local_agent_robotic_filler_repair(self):
        """Local agent detects and auto-cleans robotic filler phrases."""
        script = self.engine.generate_script(
            topic_title="Quantum Computing",
            niche="Technology & AI Innovations",
            video_format="short",
            language="en",
        )
        # Manually inject robotic filler into a scene
        script.scenes[1].narration = "As an AI language model, quantum computing is evolving fast."
        script = self.engine.inspect_and_repair_script(script)

        self.assertNotIn("as an ai language model", script.scenes[1].narration.lower())
        self.assertIn("Removed robotic filler", script.scenes[1].agent_notes)

    def test_surgical_single_scene_regeneration(self):
        """Regenerates only scene #2 without modifying remaining scenes."""
        script = self.engine.generate_script(
            topic_title="Space Exploration Breakthroughs",
            niche="Science, Mystery & Facts",
            video_format="short",
            language="en",
        )
        old_scene3_text = script.scenes[2].narration
        updated = self.engine.regenerate_single_scene(
            script,
            scene_index=2,
            new_direction="Hyper-detailed Mars Rover discovery footage",
        )

        # Scene 2 updated
        self.assertIn("Revised with high engagement", updated.scenes[1].narration)
        self.assertIn("Mars Rover discovery", updated.scenes[1].visual_prompt)
        # Scene 3 untouched
        self.assertEqual(updated.scenes[2].narration, old_scene3_text)


if __name__ == "__main__":
    unittest.main()
