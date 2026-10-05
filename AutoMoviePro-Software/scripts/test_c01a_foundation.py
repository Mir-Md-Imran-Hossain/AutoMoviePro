"""C01-A — Customer application foundation + truthful job UX (paid APIs = 0)."""
from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.customer_foundation import (
    MEDIA_AVAILABLE,
    MEDIA_UNAVAILABLE,
    MEDIA_UNKNOWN,
    PRODUCTION_BLOCKED,
    PRODUCTION_READY,
    build_foundation_snapshot,
    media_status_from_capability,
)
from app.customer_job import (
    classify_error,
    create_generation_job,
    ensure_job_columns,
    get_job,
    mark_failed,
    mark_from_pipeline_result,
    reconcile_interrupted_jobs,
    sanitize_customer_error,
    to_customer_view,
    update_customer_progress,
)


class C01AFoundationTests(unittest.TestCase):
    def test_01_application_starts_modules_import(self):
        from app import main as main_mod
        from app.customer_foundation import build_foundation_snapshot as bfs
        from app.customer_job import create_generation_job as cgj

        self.assertTrue(callable(main_mod.status))
        self.assertTrue(callable(main_mod.foundation))
        self.assertTrue(callable(main_mod.generate))
        self.assertTrue(callable(bfs))
        self.assertTrue(callable(cgj))

    def test_02_truthful_readiness_planes_separated(self):
        snap = build_foundation_snapshot(
            app_started=True,
            media_cap={"FFMPEG_AVAILABLE": True, "FFPROBE_AVAILABLE": True},
            operational={"status": "READY", "production_ready": True, "issues": []},
            api_readiness={"active": True},
        )
        self.assertEqual(snap["media"], MEDIA_AVAILABLE)
        self.assertEqual(snap["production"], PRODUCTION_READY)
        self.assertTrue(snap["generate_allowed"])
        self.assertIn("publishability", snap["note"])

    def test_03_media_unavailable(self):
        self.assertEqual(
            media_status_from_capability({"FFMPEG_AVAILABLE": False, "FFPROBE_AVAILABLE": False}),
            MEDIA_UNAVAILABLE,
        )
        snap = build_foundation_snapshot(
            media_cap={"FFMPEG_AVAILABLE": False, "FFPROBE_AVAILABLE": True},
            operational={"status": "BLOCKED", "production_ready": False, "issues": ["ffmpeg_unavailable"]},
            api_readiness={"active": True},
        )
        self.assertEqual(snap["media"], MEDIA_UNAVAILABLE)
        self.assertFalse(snap["generate_allowed"])
        self.assertIn("media_tools_unavailable", snap["generate_block_reasons"])

    def test_03b_media_unknown_fail_closed(self):
        self.assertEqual(media_status_from_capability({}), MEDIA_UNKNOWN)
        snap = build_foundation_snapshot(
            media_cap={},
            operational={"status": "READY", "production_ready": True, "issues": []},
            api_readiness={"active": True},
        )
        self.assertFalse(snap["generate_allowed"])
        self.assertIn("media_tools_unknown", snap["generate_block_reasons"])

    def test_04_production_prerequisite_blocks_generate_flag(self):
        snap = build_foundation_snapshot(
            media_cap={"FFMPEG_AVAILABLE": True, "FFPROBE_AVAILABLE": True},
            operational={"status": "BLOCKED", "production_ready": False, "issues": ["data_dir_missing"]},
            api_readiness={"active": True},
        )
        self.assertEqual(snap["production"], PRODUCTION_BLOCKED)
        self.assertFalse(snap["generate_allowed"])


class C01AJobContractTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "c01a.db"
        from app import db as store

        self._orig_db = store.DB_PATH
        store.DB_PATH = self.db_path
        store.init_db()
        ensure_job_columns()
        self.channel_id = store.upsert_channel(
            {
                "youtube_name": "C01A Test",
                "facebook_name": "",
                "niche": "gadgets",
                "niche_id": 1,
                "short_upload_time": "12:00",
                "long_upload_time": "18:00",
            }
        )

    def tearDown(self):
        from app import db as store

        store.DB_PATH = self._orig_db

    def test_05_generate_persists_one_job(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short", requested_by="tester")
        self.assertIsNotNone(row["id"])
        self.assertEqual(row["upload_status"], "queued")
        loaded = get_job(int(row["id"]))
        self.assertEqual(loaded["customer_state"], "QUEUED")
        self.assertTrue(loaded["trace_id"])

    def test_06_job_queued_through_persistence_authority(self):
        from app import db as store

        row = create_generation_job(channel_id=self.channel_id, video_type="long")
        jobs = store.list_jobs(10)
        self.assertTrue(any(int(j["id"]) == int(row["id"]) for j in jobs))
        self.assertEqual(jobs[0]["upload_status"], "queued")

    def test_07_job_state_tracks_progress_updates(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        jid = int(row["id"])
        update_customer_progress(jid, customer_state="GENERATING", stage="GENERATING", upload_status="generating")
        view = to_customer_view(get_job(jid))
        self.assertEqual(view["state"], "GENERATING")
        self.assertIsNone(view["progress_percent"])

    def test_08_no_fabricated_progress_percent(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        view = to_customer_view(get_job(int(row["id"])))
        self.assertIsNone(view["progress_percent"])
        self.assertIn("Queued", view["stage_label"])

    def test_09_generation_failure_failed(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        mark_failed(int(row["id"]), "provider timeout Agnes", recoverable=True)
        view = to_customer_view(get_job(int(row["id"])))
        self.assertEqual(view["state"], "FAILED")
        self.assertEqual(view["error_class"], "provider_failure")
        self.assertTrue(view["recoverable"])

    def test_10_quality_rejection_not_ready(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        mark_failed(int(row["id"]), "publishability_blocked:quality_failed")
        view = to_customer_view(get_job(int(row["id"])))
        self.assertEqual(view["state"], "FAILED")
        self.assertEqual(view["error_class"], "quality_rejection")
        self.assertFalse(view["result_planes"]["ready_for_review"])
        self.assertFalse(view["publishable"])

    def test_11_rendering_failure_not_ready(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        mark_failed(int(row["id"]), "ffmpeg render failed")
        view = to_customer_view(get_job(int(row["id"])))
        self.assertEqual(view["error_class"], "rendering_failure")
        self.assertNotEqual(view["state"], "READY_FOR_REVIEW")

    def test_12_successful_pipeline_ready_for_review(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        jid = int(row["id"])
        mark_from_pipeline_result(
            jid,
            {
                "upload_status": "ready_to_upload",
                "title": "Demo title",
                "local_path": "/tmp/out.mp4",
            },
        )
        view = to_customer_view(get_job(jid))
        self.assertEqual(view["state"], "READY_FOR_REVIEW")
        self.assertTrue(view["publishable"])
        self.assertTrue(view["result_planes"]["ready_for_review"])
        self.assertFalse(view["result_planes"]["approved"])
        self.assertFalse(view["result_planes"]["published"])

    def test_12b_generated_without_ready_is_not_ready(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        mark_from_pipeline_result(int(row["id"]), {"upload_status": "generated", "title": "X"})
        view = to_customer_view(get_job(int(row["id"])))
        self.assertEqual(view["state"], "FAILED")
        self.assertFalse(view["publishable"])

    def test_14_restart_reconciles_inflight(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        update_customer_progress(
            int(row["id"]),
            customer_state="GENERATING",
            upload_status="generating",
        )
        n = reconcile_interrupted_jobs(live_active=False)
        self.assertGreaterEqual(n, 1)
        view = to_customer_view(get_job(int(row["id"])))
        self.assertEqual(view["state"], "INTERRUPTED")
        self.assertIn("interrupted", (view["error_summary"] or "").lower())

    def test_15_unknown_state_not_success(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        from app import db as store

        store.update_job(int(row["id"]), customer_state="", upload_status="weird_unknown")
        view = to_customer_view(get_job(int(row["id"])))
        self.assertEqual(view["state"], "FAILED")

    def test_16_exception_path_no_false_success(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        mark_failed(int(row["id"]), RuntimeError("boom"))
        view = to_customer_view(get_job(int(row["id"])))
        self.assertNotEqual(view["state"], "READY_FOR_REVIEW")
        self.assertNotEqual(view["state"], "COMPLETED")

    def test_17_secrets_redacted(self):
        msg = sanitize_customer_error("api_key=sk-abcdefghijklmnopqrstuvwxyz failure")
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", msg)
        self.assertIn("[redacted]", msg)
        self.assertEqual(classify_error("publishability_blocked:x"), "quality_rejection")


class C01AWiringTests(unittest.TestCase):
    def test_13_duplicate_generate_uses_already_running(self):
        src = inspect.getsource(__import__("app.main", fromlist=["generate"]).generate)
        self.assertIn("already_running", src)
        self.assertIn("existing_job_id", src)
        self.assertIn("create_generation_job", src)
        # C02: generate gates via can_customer_produce (composes C01 generate_allowed)
        self.assertIn("can_customer_produce", src)
        self.assertIn("generate_block_reasons", src)

    def test_18_gates_untouched_publishability_import(self):
        import pipeline.quality.publishability as pub
        import pipeline.video_pipeline as vp

        self.assertTrue(callable(pub.evaluate_publishability))
        self.assertIn("existing_job_id", inspect.signature(vp.generate_video).parameters)
        # Sole ready writer still in generate_video
        src = inspect.getsource(vp.generate_video)
        self.assertIn('upload_status = "ready_to_upload"', src)

    def test_19_live_activity_db_job_id(self):
        from pipeline import live_activity as la

        self.assertIn("db_job_id", inspect.signature(la.start_job).parameters)
        self.assertIn("db_job_id", inspect.signature(la.run_in_background).parameters)

    def test_status_still_media_ready_null(self):
        from app.main import status

        with patch("pipeline.compose.probe_media_tool_capability", return_value={
            "FFMPEG_AVAILABLE": True,
            "FFPROBE_AVAILABLE": True,
        }):
            out = status()
        self.assertTrue(out.get("ok"))
        self.assertIsNone(out.get("media_ready"))
        self.assertIn("foundation", out)


class C01AGenerateEndpointTests(unittest.TestCase):
    def test_04_generate_blocked_when_media_down(self):
        from app.main import generate

        fake_channel = {"id": 1, "youtube_name": "x", "niche": "n"}
        entitled = {
            "auth_state": "AUTHENTICATED",
            "account_state": "ACTIVE",
            "entitlement_state": "ACTIVE",
            "production_access": True,
            "logged_in": True,
        }
        with patch("app.main._require_session", return_value={"customer": {"login_id": "t"}}), patch(
            "app.customer_auth.evaluate_session", return_value=entitled
        ), patch(
            "app.customer_config.require_owned_channel", return_value=(fake_channel, None)
        ), patch(
            "app.main.store.get_channel", return_value=fake_channel
        ), patch(
            "pipeline.channel_api_slots.evaluate_readiness",
            return_value={"active": True, "message": "ok"},
        ), patch(
            "pipeline.compose.probe_media_tool_capability",
            return_value={"FFMPEG_AVAILABLE": False, "FFPROBE_AVAILABLE": False},
        ), patch(
            "app.config.validate_production_operational",
            return_value={"status": "BLOCKED", "production_ready": False, "issues": ["ffmpeg_unavailable"]},
        ):
            out = generate({"channel_id": 1, "video_type": "short"})
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "production_prerequisites_blocked")

    def test_05_generate_creates_job_and_starts(self):
        from app.main import generate

        fake_channel = {"id": 7, "youtube_name": "x", "niche": "n"}
        created = {"id": 42, "upload_status": "queued", "customer_state": "QUEUED", "trace_id": "abc", "video_type": "short", "title": "t", "created_at": "t", "channel_id": 7}
        entitled = {
            "auth_state": "AUTHENTICATED",
            "account_state": "ACTIVE",
            "entitlement_state": "ACTIVE",
            "production_access": True,
            "logged_in": True,
        }

        with patch("app.main._require_session", return_value={"customer": {"login_id": "t"}}), patch(
            "app.customer_auth.evaluate_session", return_value=entitled
        ), patch(
            "app.customer_config.require_owned_channel", return_value=(fake_channel, None)
        ), patch(
            "app.main.store.get_channel", return_value=fake_channel
        ), patch(
            "app.main.store.get_session", return_value={"customer": {"login_id": "t"}}
        ), patch(
            "pipeline.channel_api_slots.evaluate_readiness",
            return_value={"active": True, "message": "ok"},
        ), patch(
            "pipeline.compose.probe_media_tool_capability",
            return_value={"FFMPEG_AVAILABLE": True, "FFPROBE_AVAILABLE": True},
        ), patch(
            "app.config.validate_production_operational",
            return_value={"status": "READY", "production_ready": True, "issues": []},
        ), patch(
            "pipeline.live_activity.snapshot",
            return_value={"active": False},
        ), patch(
            "app.customer_job.create_generation_job", return_value=created
        ), patch(
            "app.customer_job.get_job", return_value=created
        ), patch(
            "app.customer_job.set_live_correlation"
        ), patch(
            "app.customer_job.update_customer_progress"
        ), patch(
            "pipeline.live_activity.run_in_background", return_value="livehex"
        ) as rib, patch(
            "app.customer_job.ensure_job_columns"
        ), patch(
            "app.customer_job.to_customer_view", return_value={"job_id": 42, "state": "QUEUED", "trace_id": "abc"}
        ):
            out = generate({"channel_id": 7, "video_type": "short"})
        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("started"))
        self.assertEqual(out.get("job_id"), 42)
        self.assertEqual(out.get("live_correlation_id"), "livehex")
        self.assertNotIn("result", out)  # no false synchronous result.title
        self.assertIn("not complete", (out.get("message") or "").lower())
        rib.assert_called_once()
        self.assertEqual(rib.call_args.kwargs.get("db_job_id"), 42)
        from app.generation_guard import force_release

        force_release()


if __name__ == "__main__":
    unittest.main()
