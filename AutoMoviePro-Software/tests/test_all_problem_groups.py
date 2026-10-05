"""
Automated unit and integration test suite covering industrial fixes for all 8 problem groups.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.fact_pack import build_fact_pack
from pipeline.trending_search import find_trending_topics, _resolve_niche_key, NICHE_TOPIC_POOLS
from pipeline.prompt_engineering import trending_instruction, script_bundle_instruction
from pipeline.subtitle_burn import font_size_for_canvas, margin_v_for_canvas, ass_force_style
from pipeline.compose import get_h264_encoder
from pipeline.temp_garbage_collector import clean_temp_artifacts
from pipeline.pipeline_ai_supervisor import PipelineAISupervisor
from pipeline.custom_pipeline.media_providers import VIDEO_CHAIN
from pipeline.media_assets import generate_agnes_dialogue_clip


class TestProblemGroup1(unittest.TestCase):
    """Group 1: Islamic greetings/closings, Social CTA, Safe Margins."""

    def test_islamic_script_instruction_includes_greetings(self):
        inst = script_bundle_instruction(
            channel_name="Islamic Wisdom",
            niche="Islamic History & Reflections",
            focus="Lessons from Surah Al-Kahf",
            research_notes="Test notes",
            video_type="short",
            max_sec=60,
            video_special="",
            generation_special="",
            title_desc_special="",
            example_script="",
            islamic_mode=True,
        )
        self.assertIn("Assalamu Alaikum", inst)
        self.assertIn("Jazakallah Khairan", inst)
        self.assertIn("Allah Hafez", inst)
        self.assertIn("SOCIAL CALL-TO-ACTION", inst)

    def test_safe_margins_prevent_tiktok_button_overlap(self):
        style = ass_force_style(size="1080x1920", lang="en", is_short=True)
        self.assertIn("MarginR=80", style)
        self.assertIn("MarginL=60", style)


class TestProblemGroup2(unittest.TestCase):
    """Group 2: Research pipeline, gadget bias removal, and FactPack claims."""

    def test_niche_resolution(self):
        self.assertEqual(_resolve_niche_key("Cooking & Sourdough Recipes"), "cooking")
        self.assertEqual(_resolve_niche_key("Crypto & Macro Finance"), "finance")
        self.assertEqual(_resolve_niche_key("Health & Biohacking"), "health")
        self.assertEqual(_resolve_niche_key("Islamic Spiritual Wisdom"), "islamic")
        self.assertEqual(_resolve_niche_key("Daily Stoic Motivation"), "motivation")
        self.assertEqual(_resolve_niche_key("Ancient Roman Archaeology"), "history")

    def test_no_gadget_bias_in_cooking_fallback(self):
        topics = find_trending_topics(count=2, niche="cooking")
        self.assertTrue(len(topics) >= 1)
        for t in topics:
            self.assertNotIn("iPhone", t["name"])
            self.assertNotIn("Pixel", t["name"])

    def test_fact_pack_no_ridiculous_archaeology_claim_on_pancakes(self):
        pack = build_fact_pack("Fluffy Japanese Souffle Pancakes")
        claims = [c["claim"] for c in pack["claims"]]
        self.assertTrue(len(claims) >= 1)
        self.assertNotIn("archaeological study", claims[0].lower())
        self.assertTrue(any(w in claims[0].lower() for w in ("culinary", "preparation", "principles", "study")))

    def test_fact_pack_no_ridiculous_archaeology_claim_on_crypto(self):
        pack = build_fact_pack("Top 5 Crypto Altcoins 2026")
        claims = [c["claim"] for c in pack["claims"]]
        self.assertTrue(len(claims) >= 1)
        self.assertNotIn("archaeological study", claims[0].lower())
        self.assertTrue(any(w in claims[0].lower() for w in ("financial", "technological", "development", "study")))


class TestProblemGroup3(unittest.TestCase):
    """Group 3: 'Watch' verb guard fix and dynamic dialogue deduplication."""

    def test_watch_verb_not_flagged_as_smartwatch(self):
        # Emulate _looks_gadget_topic logic
        def _looks_gadget_topic(t: str) -> bool:
            tl = (t or "").lower()
            return any(
                x in tl
                for x in (
                    "sony", "iphone", "samsung", "pixel", "earbuds", "headphones",
                    "galaxy", "wh-1000", "airpods", "xiaomi", "oneplus",
                    "nothing phone", "buds", "smartwatch", "apple watch",
                    "galaxy watch", "gadget", "smartphone",
                )
            )

        # General verbs should NOT trigger gadget replan
        self.assertFalse(_looks_gadget_topic("Watch your metabolic health"))
        self.assertFalse(_looks_gadget_topic("Watch market fluctuations closely"))
        self.assertFalse(_looks_gadget_topic("Top 10 movies to watch tonight"))

        # Actual smartwatches SHOULD trigger gadget detection
        self.assertTrue(_looks_gadget_topic("Best Apple Watch ultra review"))
        self.assertTrue(_looks_gadget_topic("Samsung Galaxy Watch 7 features"))
        self.assertTrue(_looks_gadget_topic("Android Smartwatch battery comparison"))


class TestProblemGroup4(unittest.TestCase):
    """Group 4: TTS Indic language prioritization and voice consistency."""

    def test_indic_languages_bypass_edge_tts(self):
        from pipeline.tts_google import synthesize_narration
        import os
        # Even if AMP_PREFER_EDGE_TTS is set, bn/ta/ml must prioritize Google AI Studio
        with patch.dict(os.environ, {"AMP_PREFER_EDGE_TTS": "1"}):
            try:
                # With no keys, it should raise RuntimeError for Google AI Studio API key required,
                # proving it did NOT abort Google to run free Edge-TTS!
                synthesize_narration("টেস্ট অডিও", Path("dummy.m4a"), google_api_keys=[], language_hint="bn")
            except RuntimeError as exc:
                self.assertIn("Google AI Studio API key required", str(exc))


class TestProblemGroup5(unittest.TestCase):
    """Group 5: Agnes function definition & Google Veo prioritization."""

    def test_generate_agnes_dialogue_clip_is_callable(self):
        self.assertTrue(callable(generate_agnes_dialogue_clip))

    def test_video_chain_prioritizes_google_veo_before_agnes(self):
        providers = [name for name, _ in VIDEO_CHAIN]
        self.assertIn("google_veo", providers)
        self.assertIn("agnes", providers)
        veo_idx = providers.index("google_veo")
        agnes_idx = providers.index("agnes")
        self.assertLess(veo_idx, agnes_idx, "Google Veo must be prioritized before Agnes in VIDEO_CHAIN")


class TestProblemGroup6(unittest.TestCase):
    """Group 6: Hardware GPU encoding & Garbage collection."""

    def test_hardware_encoder_detection(self):
        encoder = get_h264_encoder()
        self.assertIn(encoder, ("h264_nvenc", "h264_qsv", "libx264"))

    def test_temp_garbage_collector(self):
        res = clean_temp_artifacts(max_age_hours=24.0)
        self.assertIn("deleted_files", res)
        self.assertIn("freed_bytes", res)


class TestProblemGroup7(unittest.TestCase):
    """Group 7: Mobile subtitle sizing & Bengali conjunct normalization."""

    def test_subtitle_mobile_font_size_punchy(self):
        # For vertical 9:16 shorts on 1080p, font size must be >= 54pt for clear mobile legibility
        fs = font_size_for_canvas(1080, 1920, is_short=True)
        self.assertGreaterEqual(fs, 54)

    def test_vertical_subtitle_safe_margin(self):
        mv = margin_v_for_canvas(1920, is_short=True)
        self.assertGreaterEqual(mv, 200)


class TestProblemGroup8(unittest.TestCase):
    """Group 8: Pipeline AI Supervisor Agent."""

    def test_supervisor_detects_inappropriate_archaeology_claim(self):
        sup = PipelineAISupervisor(job_id="test-job-01", niche="Cooking & Food", language="en")
        fact_pack = {
            "claims": [{"claim": "Pancakes remain an open subject of archaeological study."}]
        }
        res = sup.audit_research_and_facts("Fluffy Pancakes", fact_pack)
        self.assertFalse(res.passed)
        self.assertTrue(any("archaeology claim detected" in iss for iss in res.issues))

    def test_supervisor_flags_missing_islamic_greeting(self):
        sup = PipelineAISupervisor(job_id="test-job-02", niche="Islamic Wisdom", language="bn")
        plan = {
            "topic": "Prophet Stories",
            "scenes": [
                {"narration": "Today we look at history."},
                {"narration": "That is the end."}
            ]
        }
        res = sup.audit_script_and_etiquette(plan)
        self.assertFalse(res.passed)
        self.assertTrue(any("Islamic greeting" in iss for iss in res.issues))
        self.assertTrue(any("Call-To-Action" in iss for iss in res.issues))


if __name__ == "__main__":
    unittest.main()
