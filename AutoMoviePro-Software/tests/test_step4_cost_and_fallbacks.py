import unittest
from pipeline.niche_director import (
    _fallback_plan,
    _detect_niche_family,
    _pad_scenes_to_budget,
)


class TestStep4CostAndFallbacks(unittest.TestCase):
    def test_detect_niche_families(self):
        """Test niche family classification covers all major categories."""
        self.assertEqual(_detect_niche_family("Islamic History"), "islamic")
        self.assertEqual(_detect_niche_family("Personal Finance & Crypto"), "finance")
        self.assertEqual(_detect_niche_family("Health and Longevity"), "health")
        self.assertEqual(_detect_niche_family("Daily Motivation & Habits"), "motivation")
        self.assertEqual(_detect_niche_family("Space Science & NASA"), "science")
        self.assertEqual(_detect_niche_family("True Crime Forensics"), "true_crime")
        self.assertEqual(_detect_niche_family("Unexplained Ocean Mysteries"), "mystery")
        self.assertEqual(_detect_niche_family("Wildlife Safari & Nature"), "nature")
        self.assertEqual(_detect_niche_family("Geopolitical News & War"), "news")
        self.assertEqual(_detect_niche_family("Tech Gadget Review"), "gadget")
        self.assertEqual(_detect_niche_family("Ancient Civilizations"), "history")
        self.assertEqual(_detect_niche_family("Culinary Arts"), "general")

    def test_fallback_islamic_plan(self):
        """Islamic fallback must be spiritual/historical, not gadgets or rockets."""
        plan = _fallback_plan(
            niche="Islamic Teachings",
            topic="Steadfastness in Hardship",
            video_type="short",
            max_seconds=45,
            channel_name="Deen Guidance",
        )
        self.assertEqual(plan["style_family"], "islamic")
        self.assertTrue(len(plan["scenes"]) >= 5)
        # Check narration doesn't have robot cliches
        for sc in plan["scenes"]:
            narr = sc["narration"].lower()
            self.assertNotIn("welcome back", narr)
            self.assertNotIn("in this video", narr)
            self.assertNotIn("point 1: add only", narr)
            self.assertNotIn("artemis", narr)
            self.assertNotIn("papyrus", narr)
        # Check visual prompts are respectful / faceless
        for sc in plan["scenes"]:
            vp = sc.get("visual_prompt", "").lower()
            self.assertTrue(any(w in vp for w in ("serene", "manuscript", "sun", "sky", "light", "courtyard", "tranquil")))

    def test_fallback_finance_plan(self):
        """Finance fallback must cover compounding/risk, not gadgets or papyrus."""
        plan = _fallback_plan(
            niche="Personal Finance",
            topic="Compound Interest Formula",
            video_type="short",
            max_seconds=60,
            channel_name="Money Lab",
        )
        self.assertEqual(plan["style_family"], "finance")
        self.assertTrue(len(plan["scenes"]) >= 5)
        text = " ".join(sc["narration"] for sc in plan["scenes"]).lower()
        self.assertTrue(any(w in text for w in ("invest", "compounding", "asset", "capital", "financial")))
        self.assertNotIn("artemis", text)
        self.assertNotIn("papyrus", text)
        self.assertNotIn("earbuds", text)

    def test_fallback_health_plan(self):
        """Health fallback must focus on biological mechanisms."""
        plan = _fallback_plan(
            niche="Health & Longevity",
            topic="Intermittent Fasting",
            video_type="short",
            max_seconds=50,
            channel_name="Vitality Today",
        )
        self.assertEqual(plan["style_family"], "health")
        text = " ".join(sc["narration"] for sc in plan["scenes"]).lower()
        self.assertTrue(any(w in text for w in ("biological", "cellular", "recovery", "circadian", "energy")))
        self.assertNotIn("point 1: add only", text)

    def test_fallback_gadget_plan_clean_hooks(self):
        """Gadget fallback must not use generic AI cliches like 'Welcome to Channel'."""
        plan = _fallback_plan(
            niche="Tech Reviews",
            topic="Google Pixel 9a",
            video_type="long",
            max_seconds=120,
            channel_name="Tech Verge",
        )
        self.assertEqual(plan["style_family"], "gadget")
        intro_sc = plan["scenes"][0]["narration"].lower()
        self.assertNotIn("welcome to", intro_sc)
        self.assertNotIn("today we go deep on", intro_sc)
        outro_sc = plan["scenes"][-1]["narration"].lower()
        self.assertNotIn("questions? drop them in the comments", outro_sc)

    def test_pad_scenes_to_budget_no_meta_jargon(self):
        """Pad scenes to budget must generate natural sentences, not 'Point X: add only new information'."""
        scenes = [
            {"element": "intro", "narration": "Intro line.", "visual_query": "q", "visual_prompt": "p"},
            {"element": "outro", "narration": "Outro line.", "visual_query": "q", "visual_prompt": "p"},
        ]
        padded = _pad_scenes_to_budget(
            scenes=scenes,
            max_seconds=120,
            video_type="long",
            product="Portfolio Risk Management",
            niche="finance",
        )
        self.assertTrue(len(padded) >= 6)
        all_narr = " ".join(sc["narration"] for sc in padded)
        self.assertNotIn("point 1: add only", all_narr.lower())
        self.assertNotIn("point 2: add only", all_narr.lower())
        self.assertNotIn("the viewer has not heard yet", all_narr.lower())


if __name__ == "__main__":
    unittest.main()
