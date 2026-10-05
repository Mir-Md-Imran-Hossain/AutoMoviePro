import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

from app.customer_generation_orchestrator import (
    is_mock_or_invalid_media_artifact,
    run_mock_execution,
    start_customer_generation,
)
from app.customer_job import ensure_job_columns, create_generation_job, get_job
import app.db as store


class TestCustomerOrchestratorMockBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = TemporaryDirectory()
        self.work_dir = Path(self.tmp_dir.name)
        ensure_job_columns()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_mock_byte_signatures_detected(self):
        # 1. WAV mock bytes
        wav_mock = self.work_dir / "audio_mock.wav"
        wav_mock.write_bytes(b"RIFF....WAVEmock")
        is_mock, reason = is_mock_or_invalid_media_artifact(wav_mock)
        self.assertTrue(is_mock)
        self.assertIn("mock_marker_detected", reason)

        # 2. PNG mock bytes
        png_mock = self.work_dir / "visual_mock.png"
        png_mock.write_bytes(b"\x89PNGmock")
        is_mock, reason = is_mock_or_invalid_media_artifact(png_mock)
        self.assertTrue(is_mock)
        self.assertIn("mock_marker_detected", reason)

        # 3. Video mock bytes
        mp4_mock = self.work_dir / "video_mock.mp4"
        mp4_mock.write_bytes(b"ftypisommock")
        is_mock, reason = is_mock_or_invalid_media_artifact(mp4_mock)
        self.assertTrue(is_mock)
        self.assertIn("mock_marker_detected", reason)

        # 4. Empty file
        empty_file = self.work_dir / "empty.mp4"
        empty_file.write_bytes(b"")
        is_mock, reason = is_mock_or_invalid_media_artifact(empty_file)
        self.assertTrue(is_mock)
        self.assertEqual(reason, "media_file_empty")

        # 5. Non-existent file
        missing_file = self.work_dir / "does_not_exist.mp4"
        is_mock, reason = is_mock_or_invalid_media_artifact(missing_file)
        self.assertTrue(is_mock)
        self.assertEqual(reason, "media_file_not_found")

        # 6. Truncated mp4
        truncated_mp4 = self.work_dir / "truncated.mp4"
        truncated_mp4.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 30)
        is_mock, reason = is_mock_or_invalid_media_artifact(truncated_mp4)
        self.assertTrue(is_mock)
        self.assertIn("truncated", reason)

    def test_valid_media_signatures_pass(self):
        # 1. Valid PNG
        valid_png = self.work_dir / "valid.png"
        valid_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        is_mock, reason = is_mock_or_invalid_media_artifact(valid_png)
        self.assertFalse(is_mock)
        self.assertEqual(reason, "ok")

        # 2. Valid MP4 header
        valid_mp4 = self.work_dir / "valid.mp4"
        valid_mp4.write_bytes(b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41" + b"\x00" * 150)
        is_mock, reason = is_mock_or_invalid_media_artifact(valid_mp4)
        self.assertFalse(is_mock)
        self.assertEqual(reason, "ok")

        # 3. Valid WAV
        valid_wav = self.work_dir / "valid.wav"
        valid_wav.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x02\x00" + b"\x00" * 50)
        is_mock, reason = is_mock_or_invalid_media_artifact(valid_wav)
        self.assertFalse(is_mock)
        self.assertEqual(reason, "ok")

    def test_run_mock_execution_attaches_explicit_mock_metadata(self):
        job = create_generation_job(
            channel_id=1,
            video_type="short",
            requested_by="test_user",
            title_hint="Mock Execution Test",
        )
        job_id = int(job["id"])

        plan = {
            "channel_id": 1,
            "dialogue_segments": [
                {"dialogue_id": "dlg-1", "speaker": "narrator", "text": "Hello world"}
            ],
            "units": [
                {"beat_id": "beat-1", "visual_mode": "stock_ambient"}
            ],
        }
        snapshot = {
            "production_plan_id": f"pp-{job_id}",
            "units": [{"beat_id": "beat-1", "visual_mode": "stock_ambient"}],
        }

        with patch("app.customer_generation_orchestrator.map_production_plan_to_payloads") as mock_map, \
             patch("app.customer_generation_orchestrator.audit_information_loss") as mock_audit, \
             patch("app.customer_generation_orchestrator.materialize_plan_visual_beats") as mock_mat:

            mock_map.return_value = {
                "ok": True,
                "payloads": [
                    {
                        "actual_mode": "stock_ambient",
                        "dialogue_id": "dlg-1",
                        "beat_id": "beat-1",
                        "semantic_projection": {},
                    }
                ],
            }
            mock_audit.return_value = {"ok": True}
            mock_mat.return_value = {
                "ok": True,
                "units": [{"beat_id": "beat-1", "visual_mode": "stock_ambient"}],
            }

            res = run_mock_execution(
                login_id="test_user",
                job_id=job_id,
                plan=plan,
                snapshot=snapshot,
                fingerprint="fp123",
                work_dir=self.work_dir,
            )

        self.assertTrue(res.get("ok"), f"Execution failed: {res}")
        self.assertTrue(res.get("mock"))
        self.assertTrue(res.get("is_mock"))
        self.assertTrue(res.get("mock_is_not_real_media"))
        self.assertEqual(res.get("execution_mode"), "MOCK")

        record = res.get("record") or {}
        # Check audio artifacts metadata
        audio_arts = record.get("audio_artifacts") or []
        self.assertTrue(len(audio_arts) > 0)
        self.assertTrue(audio_arts[0].get("mock"))
        self.assertTrue(audio_arts[0].get("is_mock"))
        self.assertTrue(audio_arts[0].get("mock_is_not_real_media"))
        self.assertEqual(audio_arts[0].get("media_type"), "MOCK_AUDIO_FIXTURE")

        # Check visual lineage metadata
        lineage = record.get("lineage") or []
        self.assertTrue(len(lineage) > 0)
        self.assertTrue(lineage[0].get("mock"))
        self.assertTrue(lineage[0].get("is_mock"))
        self.assertTrue(lineage[0].get("mock_is_not_real_media"))
        self.assertEqual(lineage[0].get("media_type"), "MOCK_IMAGE_FIXTURE")

        # Check render metadata
        render = record.get("render") or {}
        self.assertTrue(render.get("mock"))
        self.assertTrue(render.get("is_mock"))
        self.assertTrue(render.get("mock_is_not_real_media"))
        self.assertEqual(render.get("media_type"), "MOCK_VIDEO_CONTAINER")

        # Check stored DB quality summary
        db_job = get_job(job_id)
        qs = json.loads(db_job.get("quality_summary") or "{}")
        self.assertTrue(qs.get("mock"))
        self.assertTrue(qs.get("is_mock"))
        self.assertTrue(qs.get("mock_is_not_real_media"))
        self.assertEqual(qs.get("execution_mode"), "MOCK")

    def test_live_path_rejects_mock_or_invalid_artifact(self):
        job = create_generation_job(
            channel_id=1,
            video_type="short",
            requested_by="test_user",
            title_hint="Live Path Test",
        )
        job_id = int(job["id"])

        # Setup mock video that returns mock byte artifact
        mock_output = self.work_dir / "final.mp4"
        mock_output.write_bytes(b"ftypisommock")

        channel = {
            "id": 1,
            "niche": "technology",
            "youtube_name": "TechChannel",
            "niche_id": 1,
            "lang_code": "en",
            "owner_login_id": "test_user",
        }

        # Mock the pipeline functions to exercise the live execution branch
        with patch("pipeline.video_pipeline.generate_video") as mock_generate_video, \
             patch("app.customer_generation_orchestrator.load_production_plan") as mock_lpp, \
             patch("app.customer_generation_orchestrator.evaluate_generation_readiness") as mock_egr, \
             patch("app.customer_plan_adapter.build_director_plan_from_production_plan") as mock_bdp, \
             patch("app.customer_generation_orchestrator.map_production_plan_to_payloads") as mock_mpp:

            mock_generate_video.return_value = {
                "local_path": str(mock_output),
                "upload_status": "ready_to_upload",
            }
            mock_lpp.return_value = {
                "plan_id": f"pp-{job_id}",
                "owner_login_id": "test_user",
                "channel_id": 1,
                "status": "READY_FOR_GENERATION",
                "fingerprint": "rev-1",
                "script_revision": "rev-1",
                "topic": "Real Smartphone Review",
                "video_type": "short",
                "language": "en",
                "dialogue_segments": [{"dialogue_id": "dlg-1"}],
                "visual_beats": [{"beat_id": "beat-1", "visual_mode": "stock_ambient"}],
                "units": [{"beat_id": "beat-1", "visual_mode": "stock_ambient"}],
            }
            mock_egr.return_value = {"ready": True, "verdict": "READY", "readiness": {"ok": True}}
            mock_bdp.return_value = {"topic": "Real Smartphone Review"}
            mock_mpp.return_value = {"ok": True, "payloads": []}

            res = start_customer_generation(
                login_id="test_user",
                channel=channel,
                use_mock=False,
                deterministic_fixtures=False,
                force_rebuild=True,
                work_dir=self.work_dir,
            )

            # Live generation MUST reject the mock artifact!
            self.assertFalse(res.get("ok"))
            self.assertEqual(res.get("status"), "FAILED")
            self.assertIn("live_generation_rejected_invalid_or_mock_media", str(res.get("error")))

    def test_customer_publish_rejects_mock_media_for_live_provider(self):
        from app.customer_publish import validate_publish_gates

        job = create_generation_job(
            channel_id=1,
            video_type="short",
            requested_by="test_user",
            title_hint="Publish Mock Media Test",
        )
        job_id = int(job["id"])

        # Create mock video file
        mock_video = self.work_dir / "mock_publish.mp4"
        mock_video.write_bytes(b"ftypisommock")

        store.update_job(
            job_id,
            upload_status="ready_to_upload",
            customer_state="READY_FOR_REVIEW",
            local_path=str(mock_video),
            quality_summary=json.dumps({"publishable": True, "verified": True}),
        )

        channel_dict = {
            "id": 1,
            "owner_login_id": "test_user",
            "youtube_name": "TestChan",
            "lang_code": "en",
        }

        with patch("app.db.get_channel", return_value=channel_dict), \
             patch("app.customer_publish.job_owned_by_channels", return_value=True):

            # 1. Publish to live provider (youtube) with mock media artifact -> MUST be blocked
            res_live = validate_publish_gates(
                login_id="test_user",
                job_id=job_id,
                channel_ids=[1],
                channel_id=1,
                provider="youtube",
                require_production_access=False,
            )
            self.assertFalse(res_live.get("admitted"))
            blockers = res_live.get("blockers") or []
            self.assertTrue(any("mock_media_rejected_for_live_publish" in b for b in blockers))

            # 2. Publish to mock provider -> allowed for test fixtures
            res_mock = validate_publish_gates(
                login_id="test_user",
                job_id=job_id,
                channel_ids=[1],
                channel_id=1,
                provider="mock",
                require_production_access=False,
            )
            # Should not have mock_media_rejected_for_live_publish blocker
            mock_blockers = res_mock.get("blockers") or []
            self.assertFalse(any("mock_media_rejected_for_live_publish" in b for b in mock_blockers))


if __name__ == "__main__":
    unittest.main()
