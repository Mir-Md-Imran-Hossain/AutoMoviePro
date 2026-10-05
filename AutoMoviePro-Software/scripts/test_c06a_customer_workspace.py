"""C06-A — Customer Production Workspace Foundation (paid APIs = 0).

Deterministic projection + ownership + stage derivation tests.
Does not call paid providers.
"""
from __future__ import annotations

import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class C06AContractTests(unittest.TestCase):
    def test_01_module_exists(self):
        from app import customer_workspace as cw

        self.assertTrue(hasattr(cw, "build_workspace_projection"))
        self.assertTrue(hasattr(cw, "derive_workflow_stages"))

    def test_02_workflow_stages_order(self):
        from app.customer_workspace import WORKFLOW_STAGES

        self.assertEqual(
            list(WORKFLOW_STAGES),
            ["TOPIC", "RESEARCH", "SCRIPT", "PLAN", "GENERATE", "QUALITY", "PREVIEW", "APPROVAL"],
        )

    def test_03_stage_statuses(self):
        from app.customer_workspace import STAGE_STATUSES

        for s in ("NOT_STARTED", "READY", "RUNNING", "BLOCKED", "FAILED", "COMPLETED"):
            self.assertIn(s, STAGE_STATUSES)

    def test_04_no_duplicate_engines_in_module(self):
        from app import customer_workspace as cw

        src = Path(cw.__file__).read_text(encoding="utf-8")
        self.assertEqual(cw.detect_duplicate_engines_in_source(src), [])

    def test_05_does_not_import_generate_video(self):
        src = (ROOT / "app" / "customer_workspace.py").read_text(encoding="utf-8")
        self.assertNotIn("from pipeline.video_pipeline", src)
        self.assertNotIn("import video_pipeline", src)
        self.assertNotIn("from pipeline.quality.publishability", src)


class C06AOwnershipIsolationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "c06a.db"
        from app import db as store
        from app.customer_job import ensure_job_columns, create_generation_job
        from app.customer_config import ensure_channel_owner_column

        self._orig = store.DB_PATH
        store.DB_PATH = self.db_path
        store.init_db()
        ensure_job_columns()
        ensure_channel_owner_column()
        self.store = store
        self.create_generation_job = create_generation_job
        self.ch_a = store.upsert_channel(
            {
                "youtube_name": "A",
                "niche": "tech",
                "niche_id": 1,
                "short_upload_time": "12:00",
                "long_upload_time": "18:00",
                "owner_login_id": "customer_a",
            }
        )
        self.ch_b = store.upsert_channel(
            {
                "youtube_name": "B",
                "niche": "news",
                "niche_id": 2,
                "short_upload_time": "12:00",
                "long_upload_time": "18:00",
                "owner_login_id": "customer_b",
            }
        )

    def tearDown(self):
        self.store.DB_PATH = self._orig

    def test_06_workspace_ownership_project_header(self):
        from app.customer_workspace import build_project_header
        from app.customer_job import to_customer_view, get_job

        row = self.create_generation_job(channel_id=self.ch_a, video_type="short")
        job = to_customer_view(get_job(int(row["id"])))
        hdr = build_project_header(
            channel=self.store.get_channel(self.ch_a),
            job=job,
            login_id="customer_a",
        )
        self.assertEqual(hdr["owner_login_id"], "customer_a")
        self.assertIn("project_id", hdr)

    def test_07_forged_customer_job_filter(self):
        from app.customer_job import list_customer_jobs, create_generation_job

        ja = create_generation_job(channel_id=self.ch_a, video_type="short")
        jb = create_generation_job(channel_id=self.ch_b, video_type="short")
        only_a = list_customer_jobs(50, channel_ids=[self.ch_a])
        ids = {j["job_id"] for j in only_a}
        self.assertIn(int(ja["id"]), ids)
        self.assertNotIn(int(jb["id"]), ids)

    def test_08_job_owned_by_channels(self):
        from app.customer_job import job_owned_by_channels, create_generation_job, get_job

        row = create_generation_job(channel_id=self.ch_a, video_type="short")
        self.assertTrue(job_owned_by_channels(get_job(int(row["id"])), [self.ch_a]))
        self.assertFalse(job_owned_by_channels(get_job(int(row["id"])), [self.ch_b]))
        self.assertFalse(job_owned_by_channels(None, [self.ch_a]))

    def test_09_project_job_isolation(self):
        from app.customer_job import list_customer_jobs, create_generation_job

        create_generation_job(channel_id=self.ch_b, video_type="long")
        self.assertEqual(list_customer_jobs(10, channel_ids=[self.ch_a]), [])

    def test_10_empty_owned_channels_isolates_all(self):
        from app.customer_job import list_customer_jobs, create_generation_job

        create_generation_job(channel_id=self.ch_a, video_type="short")
        self.assertEqual(list_customer_jobs(10, channel_ids=[]), [])


class C06AStageDerivationTests(unittest.TestCase):
    def _job(self, **kw):
        base = {
            "job_id": 1,
            "state": "QUEUED",
            "created_at": "2026-09-06T10:00:00",
            "updated_at": "2026-09-06T10:00:01",
            "started_at": "2026-09-06T10:00:00",
            "publishable": False,
            "artifact_available": False,
            "request_type": "short",
            "title": "T",
            "channel_id": 1,
        }
        base.update(kw)
        return base

    def test_11_stage_derivation_no_job_ready(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job=None,
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        by = {s["stage"]: s for s in stages}
        self.assertEqual(by["TOPIC"]["status"], "READY")
        self.assertEqual(by["GENERATE"]["status"], "NOT_STARTED")

    def test_12_stage_blocked_when_config_missing(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job=None,
            foundation={"generate_allowed": False, "generate_block_reasons": ["api_readiness_inactive"]},
            access={"production_allowed": False, "block_reason": "config_missing"},
        )
        by = {s["stage"]: s for s in stages}
        self.assertEqual(by["TOPIC"]["status"], "BLOCKED")
        self.assertTrue(by["TOPIC"]["action_required"])

    def test_13_running_truthfulness_generating(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job=self._job(state="GENERATING"),
            live={"active": True, "db_job_id": "1", "phase": "visual", "scene": 4, "scene_total": 12},
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        by = {s["stage"]: s for s in stages}
        self.assertEqual(by["GENERATE"]["status"], "RUNNING")
        self.assertEqual(by["TOPIC"]["status"], "COMPLETED")
        self.assertIn("4", by["GENERATE"]["progress"]["label"])

    def test_14_no_fake_percent(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job=self._job(state="GENERATING"),
            live={"active": True, "db_job_id": "1", "phase": "tts"},
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        by = {s["stage"]: s for s in stages}
        self.assertIsNone(by["GENERATE"].get("progress"))

    def test_15_blocked_truthfulness(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job=None,
            foundation={"generate_allowed": False},
            access={"production_allowed": False, "block_reason": "login_required"},
        )
        self.assertEqual(stages[0]["status"], "BLOCKED")
        self.assertEqual(stages[0]["blocked_reason"], "login_required")

    def test_16_script_phase_maps(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job=self._job(state="GENERATING"),
            live={"active": True, "db_job_id": "1", "phase": "humanize"},
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        by = {s["stage"]: s for s in stages}
        self.assertEqual(by["SCRIPT"]["status"], "RUNNING")

    def test_17_plan_phase_maps(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job=self._job(state="GENERATING"),
            live={"active": True, "db_job_id": "1", "phase": "scenes"},
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        by = {s["stage"]: s for s in stages}
        self.assertEqual(by["PLAN"]["status"], "RUNNING")

    def test_18_research_phase_maps(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job=self._job(state="GENERATING"),
            live={"active": True, "db_job_id": "1", "phase": "director"},
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        by = {s["stage"]: s for s in stages}
        self.assertEqual(by["RESEARCH"]["status"], "RUNNING")

    def test_19_quality_validating(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job=self._job(state="VALIDATING"),
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        by = {s["stage"]: s for s in stages}
        self.assertEqual(by["QUALITY"]["status"], "RUNNING")

    def test_20_ready_for_review_completes_through_quality(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job=self._job(state="READY_FOR_REVIEW", publishable=True, artifact_available=True),
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        by = {s["stage"]: s for s in stages}
        self.assertEqual(by["QUALITY"]["status"], "COMPLETED")
        self.assertEqual(by["APPROVAL"]["status"], "READY")

    def test_21_failed_stage(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job=self._job(state="FAILED", error_summary="boom", error_class="generation_failure"),
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        by = {s["stage"]: s for s in stages}
        self.assertEqual(by["GENERATE"]["status"], "FAILED")

    def test_22_multi_stage_list_length(self):
        from app.customer_workspace import derive_workflow_stages, WORKFLOW_STAGES

        stages = derive_workflow_stages(
            job=self._job(state="QUEUED"),
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        self.assertEqual(len(stages), len(WORKFLOW_STAGES))


class C06AUnknownSemanticsTests(unittest.TestCase):
    def test_23_unknown_never_pass_normalize(self):
        from app.customer_workspace import _normalize_verdict

        self.assertEqual(_normalize_verdict("UNKNOWN"), "UNKNOWN")
        self.assertEqual(_normalize_verdict("OBSERVED_UNKNOWN"), "UNKNOWN")
        self.assertNotEqual(_normalize_verdict("UNKNOWN"), "PASS")

    def test_24_file_exists_without_publishable_is_unknown(self):
        from app.customer_workspace import project_quality_panel

        panel = project_quality_panel(
            {
                "state": "FAILED",
                "publishable": False,
                "result_planes": {"file_exists": True, "technically_verified": False},
                "verification": {"note": "x"},
                "quality": {},
            }
        )
        dims = {d["name"]: d["status"] for d in panel["dimensions"]}
        self.assertEqual(dims["Technical"], "UNKNOWN")
        self.assertNotEqual(dims["Technical"], "PASS")

    def test_25_quality_panel_unknown_flag(self):
        from app.customer_workspace import project_quality_panel

        panel = project_quality_panel(None)
        self.assertTrue(panel["unknown_is_not_pass"])

    def test_26_multimodal_not_inferred_pass(self):
        from app.customer_workspace import project_quality_panel

        panel = project_quality_panel(
            {"state": "READY_FOR_REVIEW", "publishable": True, "result_planes": {"technically_verified": True}},
            sidecar={"multimodal": "PASS", "multimodal_source": "METADATA"},
        )
        dims = {d["name"]: d["status"] for d in panel["dimensions"]}
        self.assertEqual(dims["Multimodal"], "UNKNOWN")

    def test_27_publishability_projection_pass(self):
        from app.customer_workspace import project_quality_panel

        panel = project_quality_panel(
            {
                "state": "READY_FOR_REVIEW",
                "publishable": True,
                "result_planes": {"technically_verified": True},
                "verification": {},
            }
        )
        self.assertEqual(panel["publishability"], "PASS")

    def test_28_publishability_not_run_inflight(self):
        from app.customer_workspace import project_quality_panel

        panel = project_quality_panel({"state": "GENERATING", "publishable": False, "result_planes": {}})
        self.assertEqual(panel["publishability"], "NOT_RUN")


class C06APreviewApprovalTests(unittest.TestCase):
    def test_29_missing_preview(self):
        from app.customer_workspace import project_preview

        p = project_preview(None)
        self.assertFalse(p["available"])
        self.assertIn("PREVIEW NOT AVAILABLE", p["message"])

    def test_30_preview_path_missing_file(self):
        from app.customer_workspace import project_preview

        p = project_preview({"artifact_path": "/no/such/file.mp4", "artifact_available": True})
        self.assertFalse(p["available"])

    def test_31_preview_available_when_file_exists(self):
        from app.customer_workspace import project_preview

        with TemporaryDirectory() as td:
            fp = Path(td) / "out.mp4"
            fp.write_bytes(b"x")
            p = project_preview({"artifact_path": str(fp), "artifact_available": True})
            self.assertTrue(p["available"])

    def test_32_approval_not_ready(self):
        from app.customer_workspace import project_approval

        a = project_approval({"state": "GENERATING"})
        self.assertEqual(a["state"], "NOT_READY")
        self.assertFalse(a["publishes"])

    def test_33_approval_ready_for_review(self):
        from app.customer_workspace import project_approval

        a = project_approval({"state": "READY_FOR_REVIEW", "publishable": True})
        self.assertEqual(a["state"], "PENDING")
        self.assertEqual(a["approval_status"], "PENDING")
        self.assertFalse(a["publishes"])

    def test_34_approval_approved_not_publish(self):
        from app.customer_workspace import project_approval

        a = project_approval(
            {"state": "READY_FOR_REVIEW", "publishable": True, "approval": {"state": "APPROVED"}}
        )
        self.assertEqual(a["state"], "APPROVED")
        self.assertFalse(a["publishes"])


class C06AActionModelTests(unittest.TestCase):
    def test_35_customer_action_config(self):
        from app.customer_workspace import derive_action_model, derive_workflow_stages

        stages = derive_workflow_stages(
            job=None,
            foundation={"generate_allowed": False},
            access={"production_allowed": False, "block_reason": "x", "message": "fix config"},
        )
        act = derive_action_model(
            stages=stages,
            job=None,
            access={"production_allowed": False, "message": "fix config", "block_reason": "x"},
        )
        self.assertEqual(act["kind"], "CUSTOMER_ACTION_REQUIRED")

    def test_36_system_running(self):
        from app.customer_workspace import derive_action_model, derive_workflow_stages

        job = {"job_id": 1, "state": "GENERATING", "created_at": "t", "updated_at": "t"}
        stages = derive_workflow_stages(
            job=job,
            live={"active": True, "db_job_id": "1", "phase": "visual"},
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        act = derive_action_model(stages=stages, job=job, access={"production_allowed": True})
        self.assertEqual(act["kind"], "SYSTEM_RUNNING")

    def test_37_system_failed(self):
        from app.customer_workspace import derive_action_model, derive_workflow_stages

        job = {
            "job_id": 1,
            "state": "FAILED",
            "error_summary": "q",
            "error_class": "quality_rejection",
            "next_action": "retry",
            "created_at": "t",
            "updated_at": "t",
        }
        stages = derive_workflow_stages(
            job=job,
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        act = derive_action_model(stages=stages, job=job, access={"production_allowed": True})
        self.assertEqual(act["kind"], "SYSTEM_FAILED")

    def test_38_approval_customer_action(self):
        from app.customer_workspace import derive_action_model, derive_workflow_stages

        job = {
            "job_id": 1,
            "state": "READY_FOR_REVIEW",
            "publishable": True,
            "artifact_available": True,
            "created_at": "t",
            "updated_at": "t",
        }
        stages = derive_workflow_stages(
            job=job,
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        act = derive_action_model(stages=stages, job=job, access={"production_allowed": True})
        self.assertEqual(act["kind"], "CUSTOMER_ACTION_REQUIRED")
        self.assertEqual(act["stage"], "APPROVAL")


class C06AApprovalPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        from app import db as store
        from app.customer_job import ensure_job_columns, create_generation_job, mark_from_pipeline_result

        self.store = store
        self._orig = store.DB_PATH
        store.DB_PATH = Path(self._tmp.name) / "a.db"
        store.init_db()
        ensure_job_columns()
        self.ch = store.upsert_channel(
            {
                "youtube_name": "X",
                "niche": "x",
                "niche_id": 1,
                "short_upload_time": "12:00",
                "long_upload_time": "18:00",
            }
        )
        self.row = create_generation_job(channel_id=self.ch, video_type="short")
        with TemporaryDirectory() as td:
            # use persistent path under self._tmp
            pass
        self.art = Path(self._tmp.name) / "final.mp4"
        self.art.write_bytes(b"mp4")
        mark_from_pipeline_result(
            int(self.row["id"]),
            {"upload_status": "ready_to_upload", "title": "OK", "local_path": str(self.art)},
        )

    def tearDown(self):
        self.store.DB_PATH = self._orig

    def test_39_set_approval_approved(self):
        from app.customer_job import set_customer_approval, get_job

        res = set_customer_approval(int(self.row["id"]), "approved")
        self.assertTrue(res["ok"])
        self.assertFalse(res["publishes"])
        row = get_job(int(self.row["id"]))
        self.assertEqual(row["customer_approval"], "APPROVED")
        self.assertEqual(row["upload_status"], "ready_to_upload")  # not uploaded

    def test_40_set_approval_rejected(self):
        from app.customer_job import set_customer_approval

        res = set_customer_approval(int(self.row["id"]), "rejected")
        self.assertTrue(res["ok"])
        self.assertEqual(res["approval_state"], "REJECTED")

    def test_41_approval_blocked_when_not_ready(self):
        from app.customer_job import create_generation_job, set_customer_approval

        row = create_generation_job(channel_id=self.ch, video_type="short")
        res = set_customer_approval(int(row["id"]), "approved")
        self.assertFalse(res["ok"])
        self.assertEqual(res["error_code"], "approval_not_ready")

    def test_42_invalid_decision(self):
        from app.customer_job import set_customer_approval

        res = set_customer_approval(int(self.row["id"]), "publish")
        self.assertFalse(res["ok"])


class C06APollingStaleTests(unittest.TestCase):
    def test_43_stale_polling_guard(self):
        from app.customer_job import is_newer_projection

        newer = {"updated_at": "2026-09-06T12:00:10", "state": "READY_FOR_REVIEW", "state_ordinal": 90}
        older = {"updated_at": "2026-09-06T12:00:05", "state": "GENERATING", "state_ordinal": 30}
        self.assertFalse(is_newer_projection(older, newer))
        self.assertTrue(is_newer_projection(newer, older))

    def test_44_terminal_polling(self):
        from app.customer_job import is_terminal_state

        self.assertTrue(is_terminal_state("READY_FOR_REVIEW"))
        self.assertTrue(is_terminal_state("FAILED"))
        self.assertFalse(is_terminal_state("GENERATING"))

    def test_45_restart_interrupted(self):
        from app import db as store
        from app.customer_job import (
            create_generation_job,
            ensure_job_columns,
            reconcile_interrupted_jobs,
            to_customer_view,
            get_job,
            update_customer_progress,
        )

        with TemporaryDirectory() as td:
            orig = store.DB_PATH
            store.DB_PATH = Path(td) / "r.db"
            try:
                store.init_db()
                ensure_job_columns()
                ch = store.upsert_channel(
                    {
                        "youtube_name": "R",
                        "niche": "r",
                        "niche_id": 1,
                        "short_upload_time": "12:00",
                        "long_upload_time": "18:00",
                    }
                )
                row = create_generation_job(channel_id=ch, video_type="short")
                update_customer_progress(int(row["id"]), customer_state="GENERATING", upload_status="generating")
                reconcile_interrupted_jobs(live_active=False)
                view = to_customer_view(get_job(int(row["id"])))
                self.assertEqual(view["state"], "INTERRUPTED")
                self.assertTrue(view["terminal"])
            finally:
                store.DB_PATH = orig


class C06AErrorSanitizationTests(unittest.TestCase):
    def test_46_error_sanitization_api_key(self):
        from app.customer_job import sanitize_customer_error

        s = sanitize_customer_error("failed api_key=sk-secret1234567890 and token=abc")
        self.assertNotIn("sk-secret", s)
        self.assertIn("[redacted]", s)

    def test_47_error_sanitization_in_quality_note(self):
        from app.customer_workspace import project_quality_panel

        panel = project_quality_panel(
            {
                "state": "FAILED",
                "publishable": False,
                "result_planes": {},
                "quality": {"note": "provider secret=supersecretvalue"},
            }
        )
        self.assertNotIn("supersecretvalue", str(panel.get("note") or ""))


class C06AIntegrationAuthorityTests(unittest.TestCase):
    def test_48_c01_job_integration(self):
        from app.customer_job import CUSTOMER_STATES, to_customer_view

        self.assertIn("READY_FOR_REVIEW", CUSTOMER_STATES)
        self.assertTrue(callable(to_customer_view))

    def test_49_c02_auth_symbols(self):
        from app.customer_auth import can_customer_produce, evaluate_session

        self.assertTrue(callable(can_customer_produce))
        self.assertTrue(callable(evaluate_session))

    def test_50_c03_onboarding_symbols(self):
        from app.customer_onboarding import build_dashboard, assert_customer_scope

        self.assertTrue(callable(build_dashboard))
        self.assertTrue(callable(assert_customer_scope))

    def test_51_c04_config_symbols(self):
        from app.customer_config import require_owned_channel, list_owned_channels

        self.assertTrue(callable(require_owned_channel))
        self.assertTrue(callable(list_owned_channels))

    def test_52_workspace_endpoint_extended(self):
        from app import main as main_mod

        src = inspect.getsource(main_mod.workspace)
        self.assertIn("build_workspace_projection", src)
        self.assertIn("workflow", src)
        self.assertIn("quality_panel", src)

    def test_53_approval_endpoint_exists(self):
        from app import main as main_mod

        self.assertTrue(callable(main_mod.workspace_approval))
        src = inspect.getsource(main_mod.workspace_approval)
        self.assertTrue(
            "set_customer_approval" in src or "record_customer_approval" in src
        )
        self.assertTrue("publish" in src.lower())

    def test_54_generate_still_uses_guard(self):
        from app import main as main_mod

        src = inspect.getsource(main_mod.generate)
        self.assertIn("generation_try_acquire", src)
        self.assertIn("require_owned_channel", src)
        self.assertIn("can_customer_produce", src)

    def test_55_jobs_endpoint_scoped(self):
        from app import main as main_mod

        src = inspect.getsource(main_mod.jobs)
        self.assertIn("channel_ids", src)
        src2 = inspect.getsource(main_mod.job_detail)
        self.assertIn("job_access_denied", src2)


class C05VisibilityTests(unittest.TestCase):
    def test_56_c05_summary_unavailable(self):
        from app.customer_workspace import load_c05_summary_from_artifact

        s = load_c05_summary_from_artifact(None)
        self.assertFalse(s["c05_visible"])
        self.assertEqual(s["source"], "unavailable")

    def test_57_c05_summary_from_sidecars(self):
        from app.customer_workspace import load_c05_summary_from_artifact

        with TemporaryDirectory() as td:
            art = Path(td) / "final.mp4"
            art.write_bytes(b"x")
            beat = {
                "units": [
                    {"dialogue_id": "d1", "beat_id": "b1"},
                    {"dialogue_id": "d1", "beat_id": "b2"},
                    {"dialogue_id": "d2", "beat_id": "b3"},
                ]
            }
            (Path(td) / "scene_01_beat_materialization.json").write_text(
                json.dumps(beat), encoding="utf-8"
            )
            s = load_c05_summary_from_artifact(
                {"artifact_path": str(art), "publishable": True, "state": "READY_FOR_REVIEW", "artifact_available": True}
            )
            self.assertTrue(s["c05_visible"])
            self.assertEqual(s["visual_beats"], 3)
            self.assertEqual(s["dialogue_beats"], 2)

    def test_58_c05_not_reinterpreted_in_module(self):
        src = (ROOT / "app" / "customer_workspace.py").read_text(encoding="utf-8")
        self.assertNotIn("DirectedVisualBeat", src)
        self.assertNotIn("materialize_visual_beats", src)


class C06AFullProjectionSmokeTests(unittest.TestCase):
    def test_59_full_projection_keys(self):
        from app.customer_workspace import build_workspace_projection

        proj = build_workspace_projection(
            login_id="cust1",
            channel={"id": 1, "youtube_name": "Ch", "languages_json": '["en","bn"]'},
            job=None,
            live={},
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        for k in (
            "project",
            "workflow",
            "production_summary",
            "quality_panel",
            "preview",
            "approval",
            "action",
        ):
            self.assertIn(k, proj)

    def test_60_smoke_login_to_approval_states(self):
        """Deterministic local smoke: stage map across lifecycle without providers."""
        from app.customer_workspace import derive_workflow_stages, project_approval, project_preview

        foundation = {"generate_allowed": True}
        access = {"production_allowed": True}
        # topic
        s0 = {x["stage"]: x["status"] for x in derive_workflow_stages(job=None, foundation=foundation, access=access)}
        self.assertEqual(s0["TOPIC"], "READY")
        job = {
            "job_id": 9,
            "state": "GENERATING",
            "created_at": "t",
            "updated_at": "t",
            "publishable": False,
            "artifact_available": False,
        }
        live = {"active": True, "db_job_id": "9", "phase": "humanize"}
        s1 = {x["stage"]: x["status"] for x in derive_workflow_stages(job=job, live=live, foundation=foundation, access=access)}
        self.assertEqual(s1["SCRIPT"], "RUNNING")
        live["phase"] = "scenes"
        s2 = {x["stage"]: x["status"] for x in derive_workflow_stages(job=job, live=live, foundation=foundation, access=access)}
        self.assertEqual(s2["PLAN"], "RUNNING")
        live["phase"] = "visual"
        s3 = {x["stage"]: x["status"] for x in derive_workflow_stages(job=job, live=live, foundation=foundation, access=access)}
        self.assertEqual(s3["GENERATE"], "RUNNING")
        job["state"] = "VALIDATING"
        s4 = {x["stage"]: x["status"] for x in derive_workflow_stages(job=job, foundation=foundation, access=access)}
        self.assertEqual(s4["QUALITY"], "RUNNING")
        job.update({"state": "READY_FOR_REVIEW", "publishable": True, "artifact_available": False})
        s5 = {x["stage"]: x["status"] for x in derive_workflow_stages(job=job, foundation=foundation, access=access)}
        self.assertEqual(s5["APPROVAL"], "READY")
        self.assertEqual(project_preview(job)["message"], "PREVIEW NOT AVAILABLE YET")
        self.assertEqual(project_approval(job)["state"], "PENDING")


class C06ARepeatedGenerateSafetyTests(unittest.TestCase):
    def test_61_generation_guard_mutual_exclusion(self):
        from app import generation_guard as guard

        guard.reset_for_tests()
        try:
            self.assertTrue(guard.try_acquire("customer"))
            self.assertFalse(guard.try_acquire("customer"))
            guard.release("customer")
            self.assertTrue(guard.try_acquire("customer"))
        finally:
            guard.force_release()
            guard.reset_for_tests()

    def test_62_generate_authorization_imports(self):
        from app.customer_auth import can_customer_produce
        from app.customer_foundation import build_foundation_snapshot

        snap = build_foundation_snapshot(
            media_cap={},
            operational={"status": "READY", "production_ready": True, "issues": []},
            api_readiness={"active": True},
        )
        self.assertFalse(snap["generate_allowed"])


class C06AArchitectureGuardTests(unittest.TestCase):
    def test_63_no_second_job_engine_file(self):
        bad = list((ROOT / "app").glob("*job_engine*")) + list((ROOT / "app").glob("*scheduler_engine*"))
        self.assertEqual(bad, [])

    def test_64_customer_workspace_does_not_write_upload_status_uploaded(self):
        src = (ROOT / "app" / "customer_job.py").read_text(encoding="utf-8")
        # set_customer_approval must not set uploaded
        fn = src[src.index("def set_customer_approval") : src.index("def set_customer_approval") + 1200]
        self.assertNotIn('upload_status="uploaded"', fn)
        self.assertNotIn("upload_status='uploaded'", fn)

    def test_65_ui_has_workflow_timeline(self):
        html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn("wsWorkflowTimeline", html)
        self.assertIn("wsQualityPanel", html)
        self.assertIn("wsApprovalPanel", html)
        self.assertIn("PREVIEW NOT AVAILABLE YET", html)

    def test_66_ui_js_renders_unknown_class(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("UNKNOWN", js)
        self.assertIn("unknown", js)
        self.assertIn("renderWorkspaceProjection", js)
        self.assertIn("/api/workspace/approval", js)

    def test_67_c05_closed_no_pipeline_edits_required(self):
        # customer_workspace must not touch generation_payload materialization
        src = (ROOT / "app" / "customer_workspace.py").read_text(encoding="utf-8")
        self.assertNotIn("generation_payload", src)

    def test_68_quality_dimensions_complete(self):
        from app.customer_workspace import QUALITY_DIMENSIONS

        for d in (
            "Technical",
            "Creative",
            "Continuity",
            "Audio",
            "Localization",
            "Multimodal",
            "Artifact",
            "Rendering",
            "Publishability",
        ):
            self.assertIn(d, QUALITY_DIMENSIONS)


class C06AMoreStageTransitionTests(unittest.TestCase):
    def test_69_approved_completes_approval(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job={
                "job_id": 1,
                "state": "READY_FOR_REVIEW",
                "publishable": True,
                "artifact_available": True,
                "approval": {"state": "APPROVED"},
                "created_at": "t",
                "updated_at": "t",
            },
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        by = {s["stage"]: s for s in stages}
        self.assertEqual(by["APPROVAL"]["status"], "COMPLETED")

    def test_70_rejected_fails_approval(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job={
                "job_id": 1,
                "state": "READY_FOR_REVIEW",
                "publishable": True,
                "artifact_available": True,
                "approval_state": "REJECTED",
                "created_at": "t",
                "updated_at": "t",
            },
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        by = {s["stage"]: s for s in stages}
        self.assertEqual(by["APPROVAL"]["status"], "FAILED")

    def test_71_queued_running_generate(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job={"job_id": 1, "state": "QUEUED", "created_at": "t", "updated_at": "t"},
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        by = {s["stage"]: s for s in stages}
        self.assertEqual(by["GENERATE"]["status"], "RUNNING")

    def test_72_channel_language_parse(self):
        from app.customer_workspace import build_project_header

        h = build_project_header(
            channel={"id": 3, "languages_json": '["bn","en"]', "youtube_name": "BN"},
            job=None,
            login_id="x",
        )
        self.assertEqual(h["language"], "bn")

    def test_73_action_completed_when_approved(self):
        from app.customer_workspace import derive_action_model, derive_workflow_stages

        job = {
            "job_id": 1,
            "state": "READY_FOR_REVIEW",
            "publishable": True,
            "artifact_available": True,
            "approval": {"state": "APPROVED"},
            "created_at": "t",
            "updated_at": "t",
        }
        stages = derive_workflow_stages(
            job=job, foundation={"generate_allowed": True}, access={"production_allowed": True}
        )
        act = derive_action_model(stages=stages, job=job, access={"production_allowed": True})
        self.assertEqual(act["kind"], "COMPLETED")

    def test_74_sidecar_publishability(self):
        from app.customer_workspace import project_quality_panel

        panel = project_quality_panel(
            {"state": "READY_FOR_REVIEW", "publishable": False, "result_planes": {}},
            sidecar={"publishability": "BLOCKED"},
        )
        self.assertEqual(panel["publishability"], "BLOCKED")

    def test_75_load_quality_sidecar(self):
        from app.customer_workspace import load_quality_sidecar

        with TemporaryDirectory() as td:
            art = Path(td) / "f.mp4"
            art.write_bytes(b"1")
            (Path(td) / "PUBLISHABILITY_GATE.json").write_text(
                json.dumps({"publishable": True}), encoding="utf-8"
            )
            (Path(td) / "ARTIFACT_GATE.json").write_text(
                json.dumps({"observation_status": "UNKNOWN", "verdict": "PASS"}), encoding="utf-8"
            )
            sc = load_quality_sidecar({"artifact_path": str(art)})
            self.assertEqual(sc["publishability"], "PASS")
            self.assertEqual(sc["artifact"], "UNKNOWN")

    def test_76_normalize_pass_variants(self):
        from app.customer_workspace import _normalize_verdict

        self.assertEqual(_normalize_verdict("PUBLISHABLE"), "PASS")
        self.assertEqual(_normalize_verdict(True), "PASS")
        self.assertEqual(_normalize_verdict(False), "FAIL")

    def test_77_partition_still_works(self):
        from app.customer_job import partition_jobs

        parts = partition_jobs(
            [
                {"job_id": 1, "state": "GENERATING", "terminal": False},
                {"job_id": 2, "state": "READY_FOR_REVIEW", "terminal": True},
            ]
        )
        self.assertEqual(len(parts["active_jobs"]), 1)
        self.assertEqual(len(parts["recent_jobs"]), 1)

    def test_78_to_customer_view_includes_approval_fields(self):
        from app import db as store
        from app.customer_job import (
            create_generation_job,
            ensure_job_columns,
            to_customer_view,
            get_job,
            CUSTOMER_VIEW_FIELDS,
        )

        with TemporaryDirectory() as td:
            orig = store.DB_PATH
            store.DB_PATH = Path(td) / "v.db"
            try:
                store.init_db()
                ensure_job_columns()
                ch = store.upsert_channel(
                    {
                        "youtube_name": "V",
                        "niche": "v",
                        "niche_id": 1,
                        "short_upload_time": "12:00",
                        "long_upload_time": "18:00",
                    }
                )
                row = create_generation_job(channel_id=ch, video_type="short")
                view = to_customer_view(get_job(int(row["id"])))
                for k in view:
                    self.assertIn(k, CUSTOMER_VIEW_FIELDS)
                self.assertIn("approval_state", CUSTOMER_VIEW_FIELDS)
            finally:
                store.DB_PATH = orig

    def test_79_workspace_projection_action_on_ready_topic(self):
        from app.customer_workspace import build_workspace_projection

        proj = build_workspace_projection(
            login_id="a",
            channel={"id": 1},
            job=None,
            live={},
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        self.assertEqual(proj["action"]["kind"], "CUSTOMER_ACTION_REQUIRED")

    def test_80_forged_access_main_workspace_source(self):
        from app import main as main_mod

        src = inspect.getsource(main_mod.workspace)
        self.assertIn("ownership_violation", src)
        self.assertIn("job_access_denied", src)


class C06AExtraCoverageTests(unittest.TestCase):
    """Additional deterministic coverage to exceed 80 tests."""

    def test_81_system_blocked_kind(self):
        from app.customer_workspace import derive_action_model

        stages = [
            {
                "stage": "QUALITY",
                "status": "BLOCKED",
                "blocked_reason": "verification_unknown",
                "error_code": "p04_unknown",
                "action_required": "Wait for observation",
            }
        ]
        act = derive_action_model(
            stages=stages,
            job={"state": "VALIDATING"},
            access={"production_allowed": True},
        )
        self.assertEqual(act["kind"], "SYSTEM_BLOCKED")

    def test_82_preview_message_constant(self):
        from app.customer_workspace import project_preview

        self.assertEqual(project_preview({})["status"], "PREVIEW_NOT_AVAILABLE_YET")

    def test_83_approval_states_constant(self):
        from app.customer_workspace import APPROVAL_STATES

        self.assertIn("APPROVED", APPROVAL_STATES)
        self.assertIn("REJECTED", APPROVAL_STATES)

    def test_84_action_kinds_constant(self):
        from app.customer_workspace import ACTION_KINDS

        self.assertIn("CUSTOMER_ACTION_REQUIRED", ACTION_KINDS)
        self.assertIn("SYSTEM_RUNNING", ACTION_KINDS)

    def test_85_completed_state_marks_all(self):
        from app.customer_workspace import derive_workflow_stages

        stages = derive_workflow_stages(
            job={"job_id": 1, "state": "COMPLETED", "created_at": "t", "updated_at": "t"},
            foundation={"generate_allowed": True},
            access={"production_allowed": True},
        )
        self.assertTrue(all(s["status"] == "COMPLETED" for s in stages))

    def test_86_audit_doc_exists(self):
        p = ROOT / "docs" / "marathon" / "customer_product" / "C06A_PRE_WORKSPACE_AUDIT.md"
        self.assertTrue(p.is_file())
        text = p.read_text(encoding="utf-8")
        self.assertIn("GET /api/workspace", text)

    def test_87_no_paid_api_in_tests(self):
        # Ensure tests do not invoke live provider clients (avoid self-matching assert strings)
        import ast

        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    calls.append(f"{getattr(node.func.value, 'id', '')}.{node.func.attr}")
                elif isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
        self.assertNotIn("requests.post", calls)
        self.assertNotIn("httpx.post", calls)
        self.assertNotIn("urlopen", calls)

    def test_88_css_workflow_present(self):
        css = (ROOT / "ui" / "static" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn("workflow-timeline", css)
        self.assertIn("quality-dim.unknown", css)

    def test_89_mark_from_pipeline_still_authority(self):
        from app.customer_job import mark_from_pipeline_result

        self.assertTrue(callable(mark_from_pipeline_result))

    def test_90_foundation_unknown_blocks(self):
        from app.customer_foundation import build_foundation_snapshot

        snap = build_foundation_snapshot(
            media_cap={"FFMPEG_AVAILABLE": True, "FFPROBE_AVAILABLE": True},
            operational={},
            api_readiness={"active": True},
        )
        self.assertFalse(snap["generate_allowed"])
        self.assertEqual(snap["production"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
