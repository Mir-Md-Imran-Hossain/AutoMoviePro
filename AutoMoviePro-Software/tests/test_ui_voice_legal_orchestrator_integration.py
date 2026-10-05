import os
import sys
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from app.voice.voice_commentary import FuturisticVoiceEngine
from app.legal.consent_manager import ConsentManager, CURRENT_LEGAL_VERSION
from app.customer_generation_orchestrator import (
    render_real_media_with_ffmpeg,
    filter_mock_or_invalid_media_artifacts,
    is_mock_or_invalid_media_artifact,
    run_mock_execution,
)
from app.customer_job import ensure_job_columns, create_generation_job
import app.db as store


class TestUIVoiceLegalOrchestrator(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = TemporaryDirectory()
        self.work_dir = Path(self.tmp_dir.name)
        ensure_job_columns()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_voice_commentary_four_rendering_stages_and_mute_volume(self):
        engine = FuturisticVoiceEngine()
        
        # 1. Update settings: volume and mute
        engine.update_settings(is_muted=False, volume=0.75)
        prefs = engine.get_preferences()
        self.assertFalse(prefs["is_muted"])
        self.assertEqual(prefs["volume"], 0.75)

        # 2. Four core rendering stages
        stages = [
            ("topic_research", "টপিক রিসার্চ"),
            ("script_localization", "স্ক্রিপ্ট লোকালাইজেশন"),
            ("audio_generation", "অডিও জেনারেশন"),
            ("scene_rendering", "সিন রেন্ডারিং"),
        ]

        for stage_key, expected_bn in stages:
            res = engine.get_pipeline_commentary(stage_key, language="bn")
            self.assertTrue(res["speech_active"], f"Stage {stage_key} should be active when unmuted")
            self.assertEqual(res["volume"], 0.75)
            self.assertIn(expected_bn, res["stage_title"])
            self.assertTrue(len(res["text"]) > 0)
            self.assertTrue(res["display_text"].startswith(res["text"]))
            self.assertTrue(res["live_screen_text"].startswith("[JARVIS]:"))

        # 3. Mute state should deactivate speech while preserving live screen text
        engine.set_mute_state(True)
        res_muted = engine.get_pipeline_commentary("topic_research", language="bn")
        self.assertFalse(res_muted["speech_active"])
        self.assertTrue(res_muted["is_muted"])
        self.assertIn("টপিক রিসার্চ", res_muted["stage_title"])
        self.assertTrue(res_muted["live_screen_text"].startswith("[JARVIS]:"))

        # Restore
        engine.set_mute_state(False)

    def test_consent_manager_mandatory_gating_and_terms(self):
        cm = ConsentManager()
        terms = cm.get_terms("bn")
        self.assertEqual(terms["version"], CURRENT_LEGAL_VERSION)
        self.assertIn("অটোমুভি প্রো", terms["title"])
        self.assertTrue(len(terms["sections"]) >= 4)

        test_user = f"user_gate_test_{os.getpid()}"
        hw_id = "HW-TEST-GATE-123"

        # Initially unconsented
        self.assertFalse(cm.has_user_consented(test_user, hw_id))
        self.assertFalse(cm.has_user_consented("", hw_id))

        # Record consent
        rec = cm.record_consent(test_user, hw_id)
        self.assertTrue(rec["ok"])

        # Now consented
        self.assertTrue(cm.has_user_consented(test_user, hw_id))
        # Wrong hardware ID must be blocked
        self.assertFalse(cm.has_user_consented(test_user, "DIFFERENT-HWID"))

    def test_ffmpeg_real_media_merging_and_mock_filtering(self):
        # 1. Filter out mock and invalid files
        mock_file = self.work_dir / "bad_mock.mp4"
        mock_file.write_bytes(b"ftypisommock")
        valid_file = self.work_dir / "valid_image.png"
        valid_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        cleaned = filter_mock_or_invalid_media_artifacts([mock_file, valid_file])
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0], valid_file)

        # 2. Render real media with FFmpeg
        out_mp4 = self.work_dir / "test_merged.mp4"
        merged = render_real_media_with_ffmpeg(
            self.work_dir,
            output_path=out_mp4,
            duration_sec=1.5,
        )
        self.assertTrue(merged.is_file())
        self.assertGreater(merged.stat().st_size, 500)

        # 3. Output MP4 must NOT be mock or invalid
        is_mock, reason = is_mock_or_invalid_media_artifact(merged)
        self.assertFalse(is_mock, f"Output MP4 must be valid, got reason: {reason}")
        self.assertEqual(reason, "ok")

    def test_run_mock_execution_produces_real_media_and_filters_mock_bytes(self):
        job = create_generation_job(
            channel_id=1,
            video_type="short",
            requested_by="test_admin",
            title_hint="Real MP4 Generation Test",
        )
        job_id = int(job["id"])

        plan = {
            "channel_id": 1,
            "dialogue_segments": [
                {"dialogue_id": "dlg-real-1", "speaker": "narrator", "text": "Real test audio"}
            ],
            "units": [
                {"beat_id": "beat-real-1", "visual_mode": "stock_ambient"}
            ],
        }
        snapshot = {
            "production_plan_id": f"pp-real-{job_id}",
            "units": [{"beat_id": "beat-real-1", "visual_mode": "stock_ambient"}],
        }

        from unittest.mock import patch
        with patch("app.customer_generation_orchestrator.map_production_plan_to_payloads") as mock_map, \
             patch("app.customer_generation_orchestrator.audit_information_loss") as mock_audit, \
             patch("app.customer_generation_orchestrator.materialize_plan_visual_beats") as mock_mat:

            mock_map.return_value = {
                "ok": True,
                "payloads": [
                    {
                        "actual_mode": "stock_ambient",
                        "dialogue_id": "dlg-real-1",
                        "beat_id": "beat-real-1",
                        "semantic_projection": {},
                    }
                ],
            }
            mock_audit.return_value = {"ok": True}
            mock_mat.return_value = {
                "ok": True,
                "units": [{"beat_id": "beat-real-1", "visual_mode": "stock_ambient"}],
            }

            res = run_mock_execution(
                login_id="test_admin",
                job_id=job_id,
                plan=plan,
                snapshot=snapshot,
                fingerprint="fp_real_test",
                work_dir=self.work_dir,
            )

        self.assertTrue(res.get("ok"))
        out_path = Path(res["record"]["render"]["output"])
        self.assertTrue(out_path.is_file())
        
        # Verify that the generated video is a genuine valid MP4 and NOT dummy mock bytes
        is_mock, reason = is_mock_or_invalid_media_artifact(out_path)
        self.assertFalse(is_mock, f"Video generated must not be mock! Reason: {reason}")
        self.assertEqual(reason, "ok")


if __name__ == "__main__":
    unittest.main()
