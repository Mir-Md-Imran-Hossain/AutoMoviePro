"""C01-B — Customer Production Workspace + generation mutual exclusion (paid APIs = 0)."""
from __future__ import annotations

import inspect
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import generation_guard as guard
from app.customer_job import (
    CUSTOMER_VIEW_FIELDS,
    is_newer_projection,
    is_terminal_state,
    mark_failed,
    mark_from_pipeline_result,
    partition_jobs,
    reconcile_interrupted_jobs,
    to_customer_view,
    create_generation_job,
    ensure_job_columns,
    get_job,
    update_customer_progress,
)
from app.customer_foundation import build_foundation_snapshot


class C01BWorkspaceProjectionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "c01b.db"
        from app import db as store

        self._orig_db = store.DB_PATH
        store.DB_PATH = self.db_path
        store.init_db()
        ensure_job_columns()
        self.channel_id = store.upsert_channel(
            {
                "youtube_name": "C01B",
                "niche": "gadgets",
                "niche_id": 1,
                "short_upload_time": "12:00",
                "long_upload_time": "18:00",
            }
        )
        guard.reset_for_tests()

    def tearDown(self):
        from app import db as store

        store.DB_PATH = self._orig_db
        guard.force_release()
        guard.reset_for_tests()

    def test_01_workspace_endpoint_exists(self):
        from app import main as main_mod

        self.assertTrue(callable(main_mod.workspace))
        self.assertIn("/api/workspace", inspect.getsource(main_mod.workspace) or "workspace")

    def test_02_03_04_05_readiness_planes(self):
        snap = build_foundation_snapshot(
            media_cap={"FFMPEG_AVAILABLE": True, "FFPROBE_AVAILABLE": True},
            operational={"status": "READY", "production_ready": True, "issues": []},
            api_readiness={"active": True},
        )
        self.assertEqual(snap["application"], "READY")
        self.assertEqual(snap["media"], "AVAILABLE")
        self.assertEqual(snap["production"], "READY")
        self.assertIn("generate_allowed", snap)

    def test_06_07_08_job_projection_and_stage(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        update_customer_progress(
            int(row["id"]), customer_state="GENERATING", upload_status="generating"
        )
        view = to_customer_view(get_job(int(row["id"])))
        self.assertEqual(view["state"], "GENERATING")
        self.assertIsNone(view["progress_percent"])
        self.assertIn("revision", view)
        self.assertIn("state_ordinal", view)
        for k in view:
            self.assertIn(k, CUSTOMER_VIEW_FIELDS)

    def test_09_no_false_completion(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        mark_from_pipeline_result(int(row["id"]), {"upload_status": "generated", "local_path": "/x.mp4"})
        view = to_customer_view(get_job(int(row["id"])))
        self.assertNotEqual(view["state"], "READY_FOR_REVIEW")
        self.assertFalse(view["publishable"])

    def test_10_11_generated_vs_verified(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        from app import db as store

        store.update_job(int(row["id"]), local_path="/tmp/out.mp4", upload_status="generating")
        view = to_customer_view(get_job(int(row["id"])))
        self.assertTrue(view["result_planes"]["file_exists"])
        self.assertFalse(view["result_planes"]["technically_verified"])
        self.assertFalse(view["result_planes"]["quality_verified"])

        mark_from_pipeline_result(
            int(row["id"]),
            {"upload_status": "ready_to_upload", "title": "T", "local_path": "/tmp/out.mp4"},
        )
        view2 = to_customer_view(get_job(int(row["id"])))
        self.assertEqual(view2["state"], "READY_FOR_REVIEW")
        self.assertTrue(view2["result_planes"]["ready_for_review"])
        self.assertTrue(view2["result_planes"]["technically_verified"])

    def test_12_13_readiness_blocks(self):
        snap_u = build_foundation_snapshot(
            media_cap={},
            operational={"status": "READY", "production_ready": True, "issues": []},
            api_readiness={"active": True},
        )
        self.assertFalse(snap_u["generate_allowed"])
        snap_b = build_foundation_snapshot(
            media_cap={"FFMPEG_AVAILABLE": True, "FFPROBE_AVAILABLE": True},
            operational={"status": "BLOCKED", "production_ready": False, "issues": ["x"]},
            api_readiness={"active": True},
        )
        self.assertFalse(snap_b["generate_allowed"])

    def test_14_15_failed_and_recovery_projection(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        mark_failed(int(row["id"]), "publishability_blocked:q")
        view = to_customer_view(get_job(int(row["id"])))
        self.assertEqual(view["state"], "FAILED")
        self.assertTrue(view["recoverable"])
        self.assertFalse(view["retry_supported"])
        self.assertIn("Generate", view["next_action"] or "")

    def test_16_restart_projection(self):
        row = create_generation_job(channel_id=self.channel_id, video_type="short")
        update_customer_progress(int(row["id"]), customer_state="GENERATING", upload_status="generating")
        reconcile_interrupted_jobs(live_active=False)
        view = to_customer_view(get_job(int(row["id"])))
        self.assertEqual(view["state"], "INTERRUPTED")
        self.assertTrue(view["terminal"])

    def test_04_05_active_recent_partition(self):
        a = create_generation_job(channel_id=self.channel_id, video_type="short")
        b = create_generation_job(channel_id=self.channel_id, video_type="long")
        mark_from_pipeline_result(
            int(b["id"]),
            {"upload_status": "ready_to_upload", "title": "ok", "local_path": "/a.mp4"},
        )
        jobs = [to_customer_view(get_job(int(a["id"]))), to_customer_view(get_job(int(b["id"])))]
        parts = partition_jobs(jobs)
        self.assertTrue(any(j["job_id"] == int(a["id"]) for j in parts["active_jobs"]))
        self.assertTrue(any(j["job_id"] == int(b["id"]) for j in parts["recent_jobs"]))


class C01BPollingSafetyTests(unittest.TestCase):
    def test_17_stale_response_cannot_overwrite(self):
        newer = {
            "job_id": 1,
            "updated_at": "2026-09-05T12:00:10",
            "state": "READY_FOR_REVIEW",
            "state_ordinal": 90,
        }
        older = {
            "job_id": 1,
            "updated_at": "2026-09-05T12:00:05",
            "state": "GENERATING",
            "state_ordinal": 30,
        }
        self.assertTrue(is_newer_projection(newer, None))
        self.assertTrue(is_newer_projection(newer, older))
        self.assertFalse(is_newer_projection(older, newer))

    def test_18_terminal_states(self):
        for s in ("READY_FOR_REVIEW", "FAILED", "INTERRUPTED", "CANCELLED", "COMPLETED"):
            self.assertTrue(is_terminal_state(s))
        self.assertFalse(is_terminal_state("GENERATING"))


class C01BMutualExclusionTests(unittest.TestCase):
    def setUp(self):
        guard.reset_for_tests()

    def tearDown(self):
        guard.force_release()
        guard.reset_for_tests()

    def test_19_customer_blocked_while_idle_holds(self):
        self.assertTrue(guard.try_acquire("idle_pregen"))
        self.assertFalse(guard.try_acquire("customer"))
        guard.release("idle_pregen")
        self.assertTrue(guard.try_acquire("customer"))
        guard.release("customer")

    def test_20_idle_blocked_while_customer_holds(self):
        self.assertTrue(guard.try_acquire("customer"))
        self.assertFalse(guard.try_acquire("idle_pregen"))
        guard.release("customer")

    def test_21_simultaneous_contention_one_wins(self):
        results = []
        barrier = threading.Barrier(2)
        lock = threading.Lock()

        def worker(name):
            barrier.wait()
            ok = guard.try_acquire(name)
            with lock:
                results.append((name, ok))
            if ok:
                time.sleep(0.05)
                guard.release(name)

        t1 = threading.Thread(target=worker, args=("customer",))
        t2 = threading.Thread(target=worker, args=("idle_pregen",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        wins = sum(1 for _, ok in results if ok)
        self.assertEqual(wins, 1)
        self.assertEqual(guard.metrics_snapshot()["max_observed_concurrent"], 1)
        self.assertEqual(guard.metrics_snapshot()["inflight"], 0)

    def test_22_release_after_idle_failure(self):
        self.assertTrue(guard.try_acquire("idle_pregen"))
        try:
            raise RuntimeError("idle boom")
        except RuntimeError:
            guard.release("idle_pregen")
        self.assertFalse(guard.is_busy())
        self.assertTrue(guard.try_acquire("customer"))
        guard.release("customer")

    def test_23_release_after_customer_failure(self):
        self.assertTrue(guard.try_acquire("customer"))
        guard.release("customer")
        self.assertTrue(guard.try_acquire("idle_pregen"))
        guard.release("idle_pregen")

    def test_24_release_on_exception_path(self):
        self.assertTrue(guard.try_acquire("idle_pregen"))

        def boom():
            try:
                raise ValueError("x")
            finally:
                guard.release("idle_pregen")

        with self.assertRaises(ValueError):
            boom()
        self.assertEqual(guard.metrics_snapshot()["inflight"], 0)
        self.assertTrue(guard.try_acquire("customer"))
        guard.release("customer")

    def test_25_repeated_contention_no_overlap(self):
        holds = []
        lock = threading.Lock()

        def hammer(name, n=40):
            for _ in range(n):
                if guard.try_acquire(name):
                    with lock:
                        holds.append(1)
                        # critical section — max concurrent must stay 1
                        self.assertEqual(guard.metrics_snapshot()["inflight"], 1)
                    time.sleep(0.001)
                    guard.release(name)
                else:
                    time.sleep(0.0005)

        threads = [
            threading.Thread(target=hammer, args=("customer",)),
            threading.Thread(target=hammer, args=("idle_pregen",)),
            threading.Thread(target=hammer, args=("timed_fallback",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        m = guard.metrics_snapshot()
        self.assertEqual(m["max_observed_concurrent"], 1)
        self.assertGreater(m["enters"], 0)
        self.assertEqual(m["inflight"], 0)

    def test_scheduler_uses_guard(self):
        from app.scheduler_service import SchedulerService

        src = inspect.getsource(SchedulerService._pregenerate_one)
        self.assertIn("generation_try_acquire", src)
        self.assertIn("generation_release", src)
        src2 = inspect.getsource(__import__("app.main", fromlist=["generate"]).generate)
        self.assertIn("generation_try_acquire", src2)
        self.assertIn("generation_owner", src2)

    def test_no_secrets_in_projection(self):
        row = {
            "id": 9,
            "video_type": "short",
            "upload_status": "failed",
            "customer_state": "FAILED",
            "error": "api_key=sk-abcdefghijklmnopqrst failure",
            "created_at": "t",
            "updated_at": "t",
            "local_path": "",
            "recoverable": 1,
        }
        view = to_customer_view(row)
        blob = str(view)
        self.assertNotIn("sk-abcdefghijklmnopqrst", blob)
        self.assertNotIn("password", blob.lower() + "x")


class C01BGeneratePathTests(unittest.TestCase):
    def setUp(self):
        guard.reset_for_tests()

    def tearDown(self):
        guard.force_release()
        guard.reset_for_tests()

    def test_generate_uses_existing_job_path_and_guard(self):
        from app.main import generate

        fake_channel = {"id": 7, "youtube_name": "x", "niche": "n"}
        created = {
            "id": 42,
            "upload_status": "queued",
            "customer_state": "QUEUED",
            "trace_id": "abc",
            "video_type": "short",
            "title": "t",
            "created_at": "t",
            "channel_id": 7,
        }
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
            "pipeline.live_activity.snapshot", return_value={"active": False}
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
        ) as rib:
            out = generate({"channel_id": 7, "video_type": "short"})
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("job_id"), 42)
        self.assertEqual(rib.call_args.kwargs.get("generation_owner"), "customer")
        self.assertEqual(rib.call_args.kwargs.get("db_job_id"), 42)
        # release happens in background wrap; acquire still held until wrap — release for cleanliness
        guard.force_release()

    def test_generate_rejects_when_guard_held(self):
        from app.main import generate

        guard.try_acquire("idle_pregen")
        fake_channel = {"id": 7, "youtube_name": "x", "niche": "n"}
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
            return_value={"FFMPEG_AVAILABLE": True, "FFPROBE_AVAILABLE": True},
        ), patch(
            "app.config.validate_production_operational",
            return_value={"status": "READY", "production_ready": True, "issues": []},
        ), patch(
            "pipeline.live_activity.snapshot", return_value={"active": False}
        ):
            out = generate({"channel_id": 7, "video_type": "short"})
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "generation_busy")


if __name__ == "__main__":
    unittest.main()
