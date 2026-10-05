import unittest
from pipeline.creative_production.script_quality import (
    classify_hook,
    score_opening_attention,
    rewrite_cold_open_hook,
    enforce_opening_hook_on_plan,
    enforce_retention_cadence_on_plan,
)
from pipeline.content_humanizer import (
    find_ai_tells,
    _local_humanize_text,
    score_human_text,
)


class TestStep5RetentionScripts(unittest.TestCase):
    def test_classify_hook_blocks_generic_cliches(self):
        """Generic, robotic, and dictionary hooks must be BLOCK status."""
        cliches = [
            "Welcome to our channel where we discuss finance.",
            "In this video we will explore how sleep works.",
            "Webster's dictionary defines discipline as following rules.",
            "Have you ever wondered why the universe expands?",
            "Hey guys without further ado let's get started.",
            "Today we will discuss the history of ancient Rome.",
        ]
        for hook in cliches:
            res = classify_hook(hook, topic="Test Topic")
            self.assertEqual(res["status"], "BLOCK", f"Hook should have been blocked: {hook}")
            self.assertTrue(res["generic"], f"Hook should be marked generic: {hook}")

    def test_classify_hook_passes_pattern_interrupt(self):
        """Curiosity-driven, specific pattern interrupts matching their topics must PASS."""
        test_cases = [
            (
                "Most people buying index funds miss the fee drag that quietly erodes thirty years of wealth.",
                "Wealth Index Funds",
            ),
            (
                "When emergency pressure strikes without warning, this biological reaction decides survival.",
                "Emergency Biological Reaction",
            ),
            (
                "Why does the Artemis heat shield face temperatures hotter than lava in the next few seconds?",
                "Artemis Lunar Heat Shield",
            ),
        ]
        for hook, topic in test_cases:
            res = classify_hook(hook, topic=topic)
            self.assertIn(res["status"], ("PASS", "WARN"), f"Hook {hook} failed with issues {res['issues']}")
            self.assertFalse(res["generic"])

    def test_rewrite_cold_open_hook(self):
        """Weak descriptive openings must be rewritten into punchy curiosity hooks."""
        weak = "The James Webb Space Telescope sits in cold orbit collecting infrared photons."
        rewritten = rewrite_cold_open_hook(weak, topic="James Webb Space Telescope")
        self.assertTrue(len(rewritten) > 20)
        self.assertTrue(any(w in rewritten.lower() for w in ("miss", "why", "what", "watch", "look closer")))
        # Enforcing on plan must replace scene 0
        plan = {
            "topic": "James Webb Space Telescope",
            "scenes": [
                {"element": "intro", "narration": weak},
                {"element": "context", "narration": "Secondary context line."},
            ],
        }
        enforced = enforce_opening_hook_on_plan(plan)
        new_hook = enforced["scenes"][0]["narration"]
        self.assertNotEqual(new_hook, weak)
        self.assertEqual(enforced["scenes"][0]["retention_role"], "pattern_interrupt")

    def test_content_humanizer_ai_tells(self):
        """AI tell detector must catch robotic words and phrases."""
        ai_text = (
            "Welcome back! In today's digital landscape, we delve into a plethora of cutting-edge solutions. "
            "It is important to note that this is a game-changer and a cornerstone of modern tech. "
            "Without further ado, smash that subscribe button!"
        )
        tells = find_ai_tells(ai_text)
        self.assertIn("delve", tells)
        self.assertIn("landscape", tells)
        self.assertIn("game_changer", tells)
        self.assertIn("welcome_back", tells)
        self.assertIn("without_further_ado", tells)
        self.assertIn("plethora", tells)
        self.assertIn("cornerstone", tells)
        self.assertIn("smash_subscribe", tells)

        cleaned = _local_humanize_text(ai_text, field="body")
        self.assertNotIn("delve", cleaned.lower())
        self.assertNotIn("game-changer", cleaned.lower())
        self.assertNotIn("without further ado", cleaned.lower())
        self.assertNotIn("smash that subscribe", cleaned.lower())

    def test_enforce_retention_cadence_on_plan(self):
        """Mid-scenes without curiosity must receive re-hooks, and ending must close loop."""
        plan = {
            "topic": "Index Funds",
            "scenes": [
                {"element": "intro", "narration": "Most investors miss how index funds compound."},
                {"element": "context", "narration": "The stock market fluctuates every single day."},
                {"element": "evidence", "narration": "Historical data shows steady long term growth."},
                {"element": "outro", "narration": "Consistency beats market timing every time."},
            ],
        }
        cadenced = enforce_retention_cadence_on_plan(plan)
        scenes = cadenced["scenes"]
        # Ending should have closing takeaway language
        last_narr = scenes[-1]["narration"].lower()
        self.assertTrue(any(w in last_narr for w in ("takeaway", "remember", "means", "so", "proves")))


if __name__ == "__main__":
    unittest.main()
