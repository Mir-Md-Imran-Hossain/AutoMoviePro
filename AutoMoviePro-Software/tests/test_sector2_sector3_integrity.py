"""Tests for Sector 2 & 3:
- SEO & Metadata Engine: Emotional Power & Curiosity Gap title scoring algorithm
- Multi-Variant Thumbnail Generation: Minimalist, High Emotion Face, Split Screen A/B variants
- Automated Video Chapters & Timestamps generator (00:00 Intro, 02:15 The Secret)
- Production Integrity & Mock Elimination:
    - MockPublishProvider strictly blocked in live production runtime
    - /api/mobile/captcha/simulate real mobile telemetry payload integration
    - pipeline/idempotency/* strictly prevents use_mock=True in customer production runtime
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from pipeline.metadata_thumbnail_engine import (
    MetadataThumbnailEngine,
    VideoMetadataPackage,
    inspect_thumbnail_image,
    score_title_emotional_curiosity,
    generate_video_chapters,
)
from publishers.customer_publish_provider import (
    MockPublishProvider,
    get_publish_provider,
    resolve_publish_provider,
)
from pipeline.idempotency.mock_guard import assert_no_mock_in_production, is_customer_production_runtime
from pipeline.idempotency.audio_runtime import execute_audio_request
from pipeline.idempotency.audio_request import AudioRequestSpec
from pipeline.idempotency.render_runtime import execute_render_request
from pipeline.idempotency.render_request import RenderRequestSpec
from pipeline.idempotency.render_manifest import RenderAssemblyManifest
from pipeline.idempotency.script_runtime import execute_script_request
from pipeline.idempotency.script_request import ScriptRequestSpec
from pipeline.idempotency.subtitle_runtime import execute_subtitle_request
from pipeline.idempotency.subtitle_request import SubtitleRequestSpec
from pipeline.idempotency.visual_runtime import execute_visual_request
from pipeline.idempotency.visual_request import VisualRequestSpec, GenerationMode


class TestSector2MetadataThumbnailEngine(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.engine = MetadataThumbnailEngine(thumbs_dir=Path(self.tmp_dir.name))

    def tearDown(self):
        self.tmp_dir.cleanup()

    # --- 1. Emotional Power & Curiosity Gap Title Scoring ---
    def test_title_scoring_emotional_and_curiosity_english(self):
        """Validates that English titles with emotional words and curiosity triggers get high CTR scores."""
        high_ctr_title = "Why The Secret Shocking Truth About AI Was Exposed (Proven 100%)"
        res = score_title_emotional_curiosity(high_ctr_title, language="en")

        self.assertGreaterEqual(res["emotional_power_score"], 80.0)
        self.assertGreaterEqual(res["curiosity_gap_score"], 80.0)
        self.assertGreaterEqual(res["composite_ctr_score"], 80.0)
        self.assertIn("shocking", [w.lower() for w in res["matched_emotional_words"]])
        self.assertIn("exposed", [w.lower() for w in res["matched_emotional_words"]])
        self.assertIn("why", [c.lower() for c in res["matched_curiosity_hooks"]])
        self.assertTrue(res["has_punctuation_hook"])
        self.assertTrue(res["has_number_hook"])

    def test_title_scoring_bengali_viral_triggers(self):
        """Validates that Bengali titles with emotional words and curiosity hooks score in the top tier."""
        bn_title = "কেন সবাই এই গোপন সত্য নিয়ে কথা বলছে? অবিশ্বাস্য রহস্য ফাঁস (১০০% প্রমাণিত)"
        res = score_title_emotional_curiosity(bn_title, language="bn")

        self.assertGreaterEqual(res["emotional_power_score"], 80.0)
        self.assertGreaterEqual(res["curiosity_gap_score"], 80.0)
        self.assertGreaterEqual(res["composite_ctr_score"], 80.0)
        self.assertIn(res["tier"], ["A+ Viral Potential", "A High CTR"])
        self.assertTrue(any("গোপন" in w or "অবিশ্বাস্য" in w or "রহস্য" in w for w in res["matched_emotional_words"]))

    def test_title_scoring_low_score_for_dry_title(self):
        """Validates that bland, emotionless titles without curiosity hooks get lower scores and actionable recommendations."""
        dry_title = "A regular video"
        res = score_title_emotional_curiosity(dry_title, language="en")

        self.assertLess(res["composite_ctr_score"], 70.0)
        self.assertEqual(res["tier"], "C Standard")
        self.assertGreater(len(res["recommendations"]), 0)

    # --- 2. Multi-Variant Thumbnail Generation ---
    def test_multi_variant_thumbnail_generation_styles(self):
        """Validates that Minimalist, High Emotion Face, and Split Screen variants are generated as valid JPEGs."""
        variants = self.engine.generate_thumbnail_variants(
            topic_title="AI Takeover",
            niche="Technology & AI",
            video_format="long",
            language="en",
            base_hash="testhash12345",
        )
        self.assertEqual(len(variants), 3)

        style_ids = [v["style"] for v in variants]
        self.assertIn("minimalist", style_ids)
        self.assertIn("high_emotion_face", style_ids)
        self.assertIn("split_screen", style_ids)

        for v in variants:
            path = Path(v["path"])
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 1000)
            details = v["details"]
            self.assertTrue(details["valid"])
            self.assertEqual(details["aspect_ratio"], "16:9")
            self.assertEqual(details["width"], 1280)
            self.assertEqual(details["height"], 720)

    def test_multi_variant_thumbnails_vertical_shorts(self):
        """Validates vertical 9:16 dimensions for all 3 variants on Shorts format."""
        variants = self.engine.generate_thumbnail_variants(
            topic_title="Life Changing Habits",
            niche="Health & Vitality",
            video_format="short",
            language="bn",
            base_hash="shorthash987",
        )
        self.assertEqual(len(variants), 3)
        for v in variants:
            details = v["details"]
            self.assertTrue(details["valid"])
            self.assertEqual(details["aspect_ratio"], "9:16")
            self.assertEqual(details["width"], 1080)
            self.assertEqual(details["height"], 1920)

    # --- 3. Automated Video Chapters & Timestamps ---
    def test_automated_video_chapters_generation(self):
        """Validates automated chapters contain standard timestamps (00:00 Intro, 02:15 The Secret, etc.)."""
        chapters = generate_video_chapters("Space Explorers", total_duration_seconds=300, video_format="long", language="en")
        self.assertGreaterEqual(len(chapters), 4)

        timestamps = [c["timestamp"] for c in chapters]
        self.assertIn("00:00", timestamps)
        self.assertIn("02:15", timestamps)

        labels = [c["label"] for c in chapters]
        self.assertTrue(any("Intro" in l for l in labels))
        self.assertTrue(any("Secret" in l for l in labels))

    def test_package_generation_integrates_chapters_and_scores(self):
        """Validates that generate_package integrates title scores, chapters, and all 3 thumbnail variants."""
        pkg = self.engine.generate_package(
            topic_title="The Lost City",
            niche="Mystery & Archaeology",
            video_format="long",
            language="en",
        )
        self.assertTrue(pkg.passed_qa)
        self.assertIn("00:00", pkg.description)
        self.assertIn("02:15", pkg.description)
        self.assertGreaterEqual(len(pkg.video_chapters), 4)
        self.assertEqual(len(pkg.thumbnail_variants), 3)

        # SEO breakdown
        self.assertIn("ctr_curiosity_score", pkg.seo_breakdown)
        self.assertIn("ctr_emotional_score", pkg.seo_breakdown)
        self.assertIn("composite_ctr_score", pkg.seo_breakdown)
        self.assertIn("title_scoring", pkg.seo_breakdown)


class TestSector3ProductionIntegrityAndMockElimination(unittest.TestCase):
    def setUp(self):
        self.orig_prod = os.environ.get("AUTOMOVIE_PRODUCTION")
        self.orig_live_pub = os.environ.get("AUTOMOVIE_LIVE_PUBLISH")
        self.orig_env = os.environ.get("AUTOMOVIE_ENV")
        self.orig_cust_prod = os.environ.get("AUTOMOVIE_CUSTOMER_PROD")

    def tearDown(self):
        for k, v in [
            ("AUTOMOVIE_PRODUCTION", self.orig_prod),
            ("AUTOMOVIE_LIVE_PUBLISH", self.orig_live_pub),
            ("AUTOMOVIE_ENV", self.orig_env),
            ("AUTOMOVIE_CUSTOMER_PROD", self.orig_cust_prod),
        ]:
            if v is not None:
                os.environ[k] = v
            elif k in os.environ:
                del os.environ[k]

    # --- 1. MockPublishProvider strictly prevented in live production ---
    def test_mock_publish_provider_blocked_in_live_production(self):
        """In live production mode, MockPublishProvider raises RuntimeError upon instantiation."""
        os.environ["AUTOMOVIE_PRODUCTION"] = "1"
        with self.assertRaises(RuntimeError) as ctx:
            MockPublishProvider()
        self.assertIn("PRODUCTION_INTEGRITY_VIOLATION", str(ctx.exception))

    def test_get_publish_provider_mock_blocked_in_live_production(self):
        """In live production mode, get_publish_provider strictly rejects mock provider."""
        os.environ["AUTOMOVIE_PRODUCTION"] = "1"
        with self.assertRaises(RuntimeError) as ctx:
            get_publish_provider("mock")
        self.assertIn("PRODUCTION_INTEGRITY_VIOLATION", str(ctx.exception))

    def test_mock_publish_provider_upload_blocks_live_production_payload(self):
        """MockPublishProvider.upload strictly raises if package or channel has live_production flag."""
        # When not in global prod env, explicit upload flag must still trigger guard
        prov = MockPublishProvider(enforce_production_guard=False)
        with self.assertRaises(RuntimeError) as ctx:
            prov.upload(package={"live_production": True}, channel={})
        self.assertIn("PRODUCTION_INTEGRITY_VIOLATION", str(ctx.exception))

    # --- 2. pipeline/idempotency/* prevents use_mock=True in customer production ---
    def test_idempotency_audio_runtime_rejects_mock_in_production(self):
        """execute_audio_request strictly raises if use_mock=True in customer production environment."""
        os.environ["AUTOMOVIE_CUSTOMER_PROD"] = "1"
        spec = AudioRequestSpec(
            job_id="job_prod_01",
            scene_id=1,
            dialogue_id="dlg_01",
            audio_plan_id="plan_01",
            dialogue_text="Production test text",
            language="en",
            provider="elevenlabs",
            model="eleven_multilingual_v2",
        )
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(RuntimeError) as ctx:
                execute_audio_request(Path(td), spec, Path(td) / "out.wav", use_mock=True)
            self.assertIn("PRODUCTION_INTEGRITY_VIOLATION", str(ctx.exception))

    def test_idempotency_render_runtime_rejects_mock_in_production(self):
        """execute_render_request strictly raises if use_mock=True in customer production environment."""
        os.environ["AUTOMOVIE_PRODUCTION"] = "1"
        spec = RenderRequestSpec(
            job_id="job_prod_02",
            manifest=RenderAssemblyManifest(job_id="job_prod_02"),
        )
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(RuntimeError) as ctx:
                execute_render_request(Path(td), spec, Path(td) / "out.mp4", use_mock=True)
            self.assertIn("PRODUCTION_INTEGRITY_VIOLATION", str(ctx.exception))

    def test_idempotency_script_runtime_rejects_mock_in_production(self):
        """execute_script_request strictly raises if use_mock=True in customer production environment."""
        os.environ["AUTOMOVIE_CUSTOMER_PROD"] = "1"
        spec = ScriptRequestSpec(
            job_id="job_prod_03",
            topic="Production Security",
            topic_identity="id_03",
            niche="Technology",
            niche_id=1,
            video_type="short",
            max_seconds=60,
            language="en",
            provider="llm_router",
            model="purpose-script",
        )
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(RuntimeError) as ctx:
                execute_script_request(Path(td), spec, Path(td) / "out.json", use_mock=True)
            self.assertIn("PRODUCTION_INTEGRITY_VIOLATION", str(ctx.exception))

    def test_idempotency_subtitle_runtime_rejects_mock_in_production(self):
        """execute_subtitle_request strictly raises if use_mock=True in customer production environment."""
        os.environ["AUTOMOVIE_PRODUCTION"] = "1"
        spec = SubtitleRequestSpec(
            job_id="job_prod_04",
            scene_id="1",
            dialogue_id="dlg_04",
            segment_id="seg_04",
            language="en",
            localized_text="Subtitles text",
            audio_fingerprint="fp_04",
            audio_duration_sec=3.5,
        )
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(RuntimeError) as ctx:
                execute_subtitle_request(Path(td), spec, Path(td) / "out.srt", use_mock=True)
            self.assertIn("PRODUCTION_INTEGRITY_VIOLATION", str(ctx.exception))

    def test_idempotency_visual_runtime_rejects_mock_in_production(self):
        """execute_visual_request strictly raises if use_mock=True in customer production environment."""
        os.environ["AUTOMOVIE_CUSTOMER_PROD"] = "1"
        spec = VisualRequestSpec(
            job_id="job_prod_05",
            scene_id=1,
            visual_plan_id="vplan_01",
            provider="mock",
            model="mock",
            generation_mode=GenerationMode.IMAGE_GENERATION,
            prompt="High quality scene visual",
        )
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(RuntimeError) as ctx:
                execute_visual_request(Path(td), spec, Path(td) / "out.jpg", use_mock=True)
            self.assertIn("PRODUCTION_INTEGRITY_VIOLATION", str(ctx.exception))

    # --- 3. /api/mobile/captcha/simulate real telemetry integration ---
    def test_captcha_simulate_integrates_real_telemetry(self):
        """Verifies /api/mobile/captcha/simulate attaches real telemetry metrics."""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.mobile_bridge import bridge

        client = TestClient(app)
        os.environ["AMP_ALLOW_CAPTCHA_SIMULATION"] = "1"

        with patch("app.config.is_production_runtime", return_value=False):
            resp = client.post("/api/mobile/captcha/simulate", json={
                "type": "puzzle_slider",
                "captcha_id": "cap_telemetry_test_123",
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["ok"])
            self.assertTrue(data.get("simulated"))
            self.assertTrue(data.get("telemetry_synced"))
            self.assertIn("telemetry", data)
            self.assertIn("system_state", data["telemetry"])
            self.assertIn("videos_generated_today", data["telemetry"])


if __name__ == "__main__":
    unittest.main()
