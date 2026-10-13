"""Unit tests for Sector 1: Video Production Pipeline Upgrades.
Verifies Topic Research, Script Generation & Pacing, Voiceover & Audio Ducking, and FFmpeg Render Upgrades.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.bgm_ducking import build_ducking_filter_complex
from pipeline.channel_dna import ChannelDNA
from pipeline.compose import detect_hardware_acceleration, get_h264_encoder
from pipeline.final_video_composer import ProductionVideoComposer
from pipeline.human_speech_engine import performance_editor
from pipeline.prompt_hardening import harden_prompt, validate_pacing_and_dialogue_redundancy
from pipeline.script_engine import (
    DialoguePacingEngine,
    PatternInterruptEngine,
    ProductionScript,
    ScriptEngine,
    ScriptScene,
)
from pipeline.topic_scoring import rank_topics, score_topic
from pipeline.trending_search import (
    CompetitorPatternAnalyzer,
    analyze_competitor_patterns,
    find_trending_topics,
)
from pipeline.tts_google import KEY_ROTATOR, AsyncZeroLatencyKeyRotator


class TestSector1PipelineUpgrades(unittest.TestCase):
    def test_competitor_headline_pattern_analysis(self):
        """CompetitorPatternAnalyzer identifies curiosity, power words, and winning archetypes."""
        headlines = [
            "Why You Should Never Buy Index Funds in 2026 (Warning)",
            "5 Shocking Secrets About Fasting That Doctors Hide",
            "The Unbelievable Truth Behind Quantum Batteries Revealed",
        ]
        res = CompetitorPatternAnalyzer.analyze_headlines(headlines)
        self.assertEqual(res["sample_count"], 3)
        self.assertGreater(res["curiosity_score"], 0.0)
        self.assertGreater(res["power_word_density"], 0.0)
        self.assertTrue(len(res["extracted_power_words"]) > 0)
        self.assertTrue(len(res["recommended_headline_formula"]) > 10)

    def test_competitor_thumbnail_pattern_analysis(self):
        """CompetitorPatternAnalyzer returns tailored thumbnail blueprints per niche."""
        niches = ["health", "finance", "cooking", "motivation", "islamic", "history", "gadget"]
        for niche in niches:
            thumb = CompetitorPatternAnalyzer.analyze_thumbnail_patterns(niche)
            self.assertEqual(thumb["niche"], niche)
            blueprint = thumb["visual_blueprint"]
            self.assertIn("composition", blueprint)
            self.assertIn("dominant_accents", blueprint)
            self.assertIn("rule_of_thirds_anchor", blueprint)
            self.assertGreater(len(thumb["thumbnail_prompt_directives"]), 2)

    def test_topic_scoring_with_competitor_analysis(self):
        """score_topic gracefully incorporates competitor intelligence synergy without regression."""
        dna = ChannelDNA(channel_id=1, niche="Technology", style_family="gadget", preferred_topics=["ai"])
        comp_intel = analyze_competitor_patterns(
            ["The Secret AI Breakthrough That Shocked Engineers"],
            niche="gadget",
        )
        scored = score_topic(
            "Autonomous AI Robotics 2026",
            dna,
            trend_score=0.8,
            trend_evidence="VERIFIED",
            competitor_analysis=comp_intel,
        )
        self.assertTrue(scored["passed"])
        self.assertIn("competitor_analysis", scored)
        self.assertIsNotNone(scored["competitor_analysis"])

        # Also verify rank_topics passes competitor_analysis
        candidates = [
            {"topic": "Autonomous AI Robotics 2026", "trend_score": 0.8, "competitor_analysis": comp_intel},
            {"topic": "Traditional Steam Engines", "trend_score": 0.3},
        ]
        ranked = rank_topics(candidates, dna)
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0]["topic"], "Autonomous AI Robotics 2026")

    def test_pattern_interrupt_hook_engine_across_niches(self):
        """PatternInterruptEngine generates niche-tailored 3-5s curiosity hooks in EN and BN."""
        niches = ["health", "finance", "cooking", "motivation", "islamic", "history", "gadget"]
        for n in niches:
            hook_en = PatternInterruptEngine.get_pattern_interrupt_hook("Test Subject", niche=n, language="en")
            hook_bn = PatternInterruptEngine.get_pattern_interrupt_hook("টেস্ট বিষয়", niche=n, language="bn")
            self.assertIn("Test Subject", hook_en)
            self.assertIn("টেস্ট বিষয়", hook_bn)
            self.assertTrue("?" in hook_en or "!" in hook_en or "..." in hook_en)
            self.assertTrue("?" in hook_bn or "!" in hook_bn or "..." in hook_bn)

    def test_dialogue_pacing_and_semantic_redundancy_curation(self):
        """DialoguePacingEngine optimizes duration and curates semantic duplication."""
        dur_short = DialoguePacingEngine.optimize_scene_duration("This is a fast five word line", video_format="short")
        self.assertGreaterEqual(dur_short, 4.0)
        self.assertLessEqual(dur_short, 14.0)

        # Create scenes with semantic duplicate clichés
        scenes = [
            ScriptScene(scene_index=1, narration="The shocking reality about this breakthrough is here.", visual_prompt="v1", estimated_duration_sec=5.0),
            ScriptScene(scene_index=2, narration="Another shocking reality about this breakthrough emerges.", visual_prompt="v2", estimated_duration_sec=6.0),
        ]
        curated = DialoguePacingEngine.curate_semantic_redundancy(scenes, language="en")
        self.assertIn("shocking reality", curated[0].narration.lower())
        self.assertNotIn("shocking reality", curated[1].narration.lower())
        self.assertIn("Curated semantic redundancy", curated[1].agent_notes)

    def test_script_engine_pattern_interrupt_integration(self):
        """ScriptEngine uses Pattern Interrupt retention hooks on Scene 1."""
        engine = ScriptEngine()
        script = engine.generate_script(
            topic_title="Quantum Battery Revolution",
            niche="gadget",
            video_format="short",
            language="en",
            include_islamic_touch=False,
        )
        self.assertEqual(script.scenes[0].scene_index, 1)
        self.assertIn("Quantum Battery Revolution", script.scenes[0].narration)
        self.assertTrue("?" in script.scenes[0].narration or "!" in script.scenes[0].narration)
        self.assertEqual(script.scenes[0].hook_type, "greeting_hook")

    def test_prompt_hardening_pattern_interrupt_and_pacing(self):
        """harden_prompt injects pattern interrupt visual hook directives on intro beats."""
        hardened = harden_prompt("base shot of robot", element="intro", narration="Did you know about this?", duration_sec=3.5)
        self.assertIn("PATTERN INTERRUPT RETENTION HOOK", hardened)

        pacing_check = validate_pacing_and_dialogue_redundancy("Spoken words for testing verbal pace across three seconds", duration_sec=3.0)
        self.assertTrue(pacing_check["cadence_optimal"])
        self.assertGreater(pacing_check["words_per_second"], 1.6)

    def test_async_zero_latency_key_rotator(self):
        """KEY_ROTATOR rotates keys in O(1) order without delay."""
        rotator = AsyncZeroLatencyKeyRotator(max_background_workers=2)
        keys = ["key_A", "key_B", "key_C"]
        r1 = rotator.get_rotated_keys(keys, "en")
        r2 = rotator.get_rotated_keys(keys, "en")
        self.assertEqual(r1[0], "key_A")
        self.assertEqual(r2[0], "key_B")
        # Test non-blocking background dispatch
        rotator.record_success_async("key_A", "en")
        rotator.record_rejection_async("key_B", "en", reason="rate_limit")

    def test_human_speech_engine_drama_controls(self):
        """performance_editor annotates speech drama mode, intensity, and fine-tuned pauses."""
        lines = [
            "Why did the old timeline refuse to fit?",
            "Tool marks force harder questions about the ancient ruins.",
            "That single alignment changes what the ruins are allowed to mean.",
        ]
        perf = performance_editor(lines, drama_level=1.2)
        beats = perf["beats"]
        self.assertEqual(len(beats), 3)
        self.assertEqual(beats[0]["drama_mode"], "dramatic_cadence")
        self.assertGreater(beats[0]["pause_after_sec"], 0.4)
        self.assertIn("drama_intensity", beats[0])

    def test_sidechain_ducking_attack_time(self):
        """build_ducking_filter_complex uses fine-tuned 0.1s (100ms) attack time."""
        fc = build_ducking_filter_complex(duck_db=-16.0, attack_ms=100.0)
        self.assertIn("attack=100", fc)
        self.assertIn("sidechaincompress", fc)

    def test_hardware_acceleration_detection(self):
        """detect_hardware_acceleration returns valid encoder and CPU threads."""
        info = detect_hardware_acceleration(force_refresh=True)
        self.assertIn(info["encoder"], ("h264_nvenc", "h264_qsv", "h264_amf", "libx264"))
        self.assertIn("hw_type", info)
        self.assertGreater(info["cpu_threads"], 0)
        enc = get_h264_encoder()
        self.assertIn(enc, ("h264_nvenc", "h264_qsv", "h264_amf", "libx264"))

    def test_production_composer_choose_encoder(self):
        """ProductionVideoComposer supports nvenc, qsv, amf, and cpu."""
        composer = ProductionVideoComposer(Path("temp/out"), Path("temp/work"))
        self.assertEqual(composer._choose_encoder("cpu"), "libx264")
        chosen = composer._choose_encoder("auto")
        self.assertIn(chosen, ("h264_nvenc", "h264_qsv", "h264_amf", "libx264"))


if __name__ == "__main__":
    unittest.main()
