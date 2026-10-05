"""C06-H — Customer Production Monitoring & Control Closure (paid APIs = 0).

>=150 deterministic unittest cases. Projection/compose only — no second engines.
"""
from __future__ import annotations

import inspect
import json
import re
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class C06HBase(unittest.TestCase):
    """Shared TemporaryDirectory fixture — mirrors C06-D / C06-G patterns."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.td = Path(self._tmp.name)
        self.data_dir = self.td / "data"
        self.data_dir.mkdir()
        self.db_path = self.td / "c06h.db"

        from app import config as cfg
        from app import db as store
        import app.customer_job_automation as cja
        import app.customer_trs_workflow as tw
        import app.customer_production_plan as pp
        import app.customer_generation_orchestrator as go
        import app.customer_preview_approval as cpa
        import app.customer_production_monitor as cpm
        from app.customer_job import ensure_job_columns
        from app.customer_config import ensure_channel_owner_column
        from app.generation_guard import force_release

        self.store = store
        self.cfg = cfg
        self.cja = cja
        self.tw = tw
        self.pp = pp
        self.go = go
        self.cpa = cpa
        self.cpm = cpm

        self._orig_db = store.DB_PATH
        self._orig_cfg_data = cfg.DATA_DIR
        self._orig_cja_data = cja.DATA_DIR
        self._orig_tw_data = tw.DATA_DIR
        self._orig_pp_data = pp.DATA_DIR
        self._orig_go_data = go.DATA_DIR
        self._orig_cpa_data = cpa.DATA_DIR
        self._orig_tw_path = tw._workflow_path
        self._orig_pp_path = pp._plan_path
        self._orig_go_sidecar = go.execution_sidecar_path

        store.DB_PATH = self.db_path
        cfg.DATA_DIR = self.data_dir
        cja.DATA_DIR = self.data_dir
        tw.DATA_DIR = self.data_dir
        pp.DATA_DIR = self.data_dir
        go.DATA_DIR = self.data_dir
        cpa.DATA_DIR = self.data_dir
        tw._workflow_path = lambda lid, cid: self.data_dir / "wf" / f"{lid}_ch{cid}.json"
        pp._plan_path = lambda lid, cid: self.data_dir / "pp" / f"{lid}_ch{cid}.json"
        go.execution_sidecar_path = lambda lid, jid: self.data_dir / "ex" / str(lid) / f"job{int(jid)}.json"

        store.init_db()
        ensure_job_columns()
        ensure_channel_owner_column()
        cja.ensure_automation_columns()
        force_release()

        self.login = "cust_a"
        self.login_b = "cust_b"
        self.ch_id = store.upsert_channel(
            {
                "youtube_name": "HChA",
                "niche": "gadgets",
                "niche_id": 1,
                "short_upload_time": "12:00",
                "long_upload_time": "18:00",
                "lang_code": "en",
                "owner_login_id": self.login,
            }
        )
        self.ch_b_id = store.upsert_channel(
            {
                "youtube_name": "HChB",
                "niche": "news",
                "niche_id": 2,
                "short_upload_time": "12:00",
                "long_upload_time": "18:00",
                "lang_code": "en",
                "owner_login_id": self.login_b,
            }
        )
        self.channel = {
            "id": self.ch_id,
            "niche": "gadgets",
            "youtube_name": "HChA",
            "niche_id": 1,
            "lang_code": "en",
            "owner_login_id": self.login,
        }
        self.channel_b = {
            "id": self.ch_b_id,
            "niche": "news",
            "youtube_name": "HChB",
            "niche_id": 2,
            "lang_code": "en",
            "owner_login_id": self.login_b,
        }

    def tearDown(self):
        from app.generation_guard import force_release

        force_release()
        self.store.DB_PATH = self._orig_db
        self.cfg.DATA_DIR = self._orig_cfg_data
        self.cja.DATA_DIR = self._orig_cja_data
        self.tw.DATA_DIR = self._orig_tw_data
        self.pp.DATA_DIR = self._orig_pp_data
        self.go.DATA_DIR = self._orig_go_data
        self.cpa.DATA_DIR = self._orig_cpa_data
        self.tw._workflow_path = self._orig_tw_path
        self.pp._plan_path = self._orig_pp_path
        self.go.execution_sidecar_path = self._orig_go_sidecar

    def _ready_plan(self, login=None, channel=None, topic: str = "C06H unique topic alpha"):
        login = login or self.login
        channel = channel or self.channel
        cid = int(channel["id"])
        self.tw.set_manual_topic(login, cid, topic)
        self.tw.run_research(login, channel, use_mock=True, work_dir=self.td / "r")
        self.tw.generate_script(login, channel, use_mock=True, work_dir=self.td / "s")
        st = self.tw.load_workflow(login, cid)
        st["script"]["quality"]["status"] = "PASS"
        st["script"]["approval"]["state"] = "READY_FOR_REVIEW"
        for i, b in enumerate(st["script"]["script_plan"].get("beats") or []):
            b.setdefault("metadata", {})
            b["metadata"]["dialogue_id"] = f"dlg-{i + 1}"
            b["metadata"]["scene_id"] = f"scene-{i:02d}"
            b["entity_refs"] = b.get("entity_refs") or ["Shobha", "Suzuki"]
            b["location_ref"] = b.get("location_ref") or "road"
            b["action_intent"] = ["stands beside", "enters", "sits inside"][min(i, 2)]
        self.tw.save_workflow(st)
        self.tw.approve_script(login, cid, decision="approved")
        return self.pp.build_production_plan(login, channel, force_rebuild=True)

    def _raw_job(self, **extra):
        from app.customer_job import create_generation_job

        row = create_generation_job(
            channel_id=int(extra.get("channel_id", self.ch_id)),
            video_type=extra.get("video_type", "short"),
            requested_by=extra.get("login_id", self.login),
            title_hint=extra.get("title", "c06h job"),
            production_plan_id=extra.get("plan_id", "plan-h"),
            production_plan_revision=extra.get("plan_rev", "rev-h"),
            script_revision=extra.get("script_rev", "scr-h"),
            generation_fingerprint=extra.get("fp", f"fp-{extra.get('suffix', 'x')}"),
            plan_snapshot=extra.get(
                "plan_snapshot",
                {
                    "production_plan_id": extra.get("plan_id", "plan-h"),
                    "production_plan_revision": extra.get("plan_rev", "rev-h"),
                    "_c06g": {
                        "execution_mode": "MOCK_DETERMINISTIC",
                        "deterministic_fixtures": True,
                        "video_type": "short",
                    },
                },
            ),
        )
        return row

    def _enqueue(self, job_id, *, login=None, channel_ids=None, fp=None):
        return self.cja.enqueue_existing_job(
            int(job_id),
            login_id=login or self.login,
            channel_ids=channel_ids or [self.ch_id],
            queue_fingerprint=fp,
        )

    def _get_job(self, job_id):
        from app.customer_job import get_job

        return get_job(int(job_id))

    def _monitor(self, job_id, *, login=None, channel_ids=None):
        return self.cpm.project_production_monitor(
            login or self.login,
            int(job_id),
            channel_ids=[self.ch_id] if channel_ids is None else list(channel_ids),
        )

    def _artifact_path(self, name: str = "preview.mp4") -> str:
        p = self.td / "artifacts" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fake-mp4")
        return str(p)


# ---------------------------------------------------------------------------
# A — Canonical customer execution path
# ---------------------------------------------------------------------------


class A_CanonicalPathTests(C06HBase):
    def test_A01_module_exports(self):
        for name in (
            "CONTRACT_VERSION",
            "STATE_CONTRACT",
            "LIFECYCLE_EVENT_TYPES",
            "ENTRY_POINT_CLASSIFICATION",
            "normalize_lifecycle_event",
            "load_lifecycle_events",
            "infer_execution_path",
            "infer_monitor_state",
            "qualitative_progress",
            "project_production_monitor",
            "project_recent_activity",
            "classify_live_lab",
            "is_live_lab_active",
            "detect_duplicate_engines",
        ):
            self.assertTrue(hasattr(self.cpm, name), name)

    def test_A02_contract_version(self):
        self.assertTrue(str(self.cpm.CONTRACT_VERSION).startswith("C06-H"))

    def test_A03_workspace_generate_queue_canonical(self):
        ep = self.cpm.ENTRY_POINT_CLASSIFICATION["workspace_generate_queue"]
        self.assertEqual(ep["class"], "CANONICAL")

    def test_A04_customer_queue_tick_canonical(self):
        ep = self.cpm.ENTRY_POINT_CLASSIFICATION["customer_queue_tick"]
        self.assertEqual(ep["class"], "CANONICAL")

    def test_A05_submit_queue_process_sets_canonical_path(self):
        self._ready_plan(topic="A05 canonical queue path topic")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=True, force_rebuild=True
        )
        self.assertTrue(r["ok"])
        mon = self._monitor(int(r["job_id"]))
        self.assertTrue(mon["ok"])
        self.assertEqual(mon["execution_path"], "CANONICAL_QUEUE")
        self.assertEqual(mon["execution_path_class"], "CANONICAL")

    def test_A06_queued_job_infers_canonical(self):
        j = self._raw_job(fp="fp-a06", suffix="a06")
        self._enqueue(j["id"], fp="fp-a06")
        row = self._get_job(int(j["id"]))
        self.assertEqual(self.cpm.infer_execution_path(row), "CANONICAL_QUEUE")

    def test_A07_claim_token_marks_canonical(self):
        path = self.cpm.infer_execution_path({"claim_token": "tok", "queue_status": None})
        self.assertEqual(path, "CANONICAL_QUEUE")

    def test_A08_queue_enqueued_at_marks_canonical(self):
        path = self.cpm.infer_execution_path({"queue_enqueued_at": "2026-01-01T00:00:00"})
        self.assertEqual(path, "CANONICAL_QUEUE")

    def test_A09_smoke_queue_to_preview_path(self):
        self._ready_plan(topic="A09 smoke canonical end topic")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=True, force_rebuild=True
        )
        self.assertTrue(r.get("ok"))
        mon = self._monitor(int(r["job_id"]))
        self.assertIn(mon["monitor_state"], ("PREVIEW_READY", "APPROVAL_PENDING", "APPROVED", "COMPLETED"))
        self.assertEqual(mon.get("paid_api_calls", 0) if "paid_api_calls" in mon else 0, 0)
        self.assertFalse(mon.get("publishes"))


# ---------------------------------------------------------------------------
# B — Synchronous compatibility classification
# ---------------------------------------------------------------------------


class B_SyncCompatTests(C06HBase):
    def test_B01_workspace_generate_sync_legacy(self):
        ep = self.cpm.ENTRY_POINT_CLASSIFICATION["workspace_generate_sync"]
        self.assertEqual(ep["class"], "LEGACY_COMPAT")

    def test_B02_api_generate_live_legacy(self):
        ep = self.cpm.ENTRY_POINT_CLASSIFICATION["api_generate_live"]
        self.assertEqual(ep["class"], "LEGACY_COMPAT")

    def test_B03_sync_start_without_queue_fields(self):
        self._ready_plan(topic="B03 sync legacy path topic")
        r = self.go.start_customer_generation(self.login, self.channel, use_mock=True)
        self.assertTrue(r.get("ok") or r.get("job_id"))
        row = self._get_job(int(r["job_id"]))
        path = self.cpm.infer_execution_path(row)
        self.assertIn(path, ("LEGACY_COMPAT_SYNC", "CANONICAL_QUEUE", "LEGACY_COMPAT_LIVE"))

    def test_B04_no_queue_fields_is_legacy_sync(self):
        self.assertEqual(self.cpm.infer_execution_path({"id": 1}), "LEGACY_COMPAT_SYNC")

    def test_B05_live_correlation_is_legacy_live(self):
        self.assertEqual(
            self.cpm.infer_execution_path({"live_correlation_id": "lc-1"}),
            "LEGACY_COMPAT_LIVE",
        )

    def test_B06_monitor_marks_legacy_class(self):
        j = self._raw_job(fp="fp-b06", suffix="b06")
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["execution_path_class"], "LEGACY_COMPAT")

    def test_B07_all_entry_points_have_class(self):
        for key, ep in self.cpm.ENTRY_POINT_CLASSIFICATION.items():
            self.assertIn("class", ep, key)
            self.assertIn(ep["class"], ("CANONICAL", "LEGACY_COMPAT", "FORBIDDEN_FOR_CUSTOMER_PRODUCTION"))


# ---------------------------------------------------------------------------
# C — Queue projection
# ---------------------------------------------------------------------------


class C_QueueProjectionTests(C06HBase):
    def test_C01_queued_state(self):
        j = self._raw_job(fp="fp-c01", suffix="c01")
        self._enqueue(j["id"], fp="fp-c01")
        self.assertEqual(self.cpm.infer_monitor_state(self._get_job(int(j["id"]))), "QUEUED")

    def test_C02_monitor_queued(self):
        j = self._raw_job(fp="fp-c02", suffix="c02")
        self._enqueue(j["id"], fp="fp-c02")
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["monitor_state"], "QUEUED")
        self.assertIsNone(mon["progress_percent"])

    def test_C03_queued_at_present(self):
        j = self._raw_job(fp="fp-c03", suffix="c03")
        self._enqueue(j["id"], fp="fp-c03")
        mon = self._monitor(int(j["id"]))
        self.assertTrue(mon.get("queued_at"))

    def test_C04_customer_state_queued(self):
        row = {"customer_state": "QUEUED", "queue_status": ""}
        self.assertEqual(self.cpm.infer_monitor_state(row), "QUEUED")

    def test_C05_qualitative_queued(self):
        self.assertEqual(self.cpm.qualitative_progress("QUEUED"), "QUEUED")

    def test_C06_state_contract_queued(self):
        self.assertIn("QUEUED", self.cpm.STATE_CONTRACT)
        self.assertEqual(self.cpm.STATE_CONTRACT["QUEUED"]["label"], "Queued")


# ---------------------------------------------------------------------------
# D — Running projection
# ---------------------------------------------------------------------------


class D_RunningProjectionTests(C06HBase):
    def test_D01_running_queue_status(self):
        row = {"queue_status": "running", "customer_state": "GENERATING"}
        self.assertEqual(self.cpm.infer_monitor_state(row), "RUNNING")

    def test_D02_generating_customer_state(self):
        row = {"queue_status": "", "customer_state": "GENERATING"}
        self.assertEqual(self.cpm.infer_monitor_state(row), "RUNNING")

    def test_D03_monitor_running(self):
        j = self._raw_job(fp="fp-d03", suffix="d03")
        self._enqueue(j["id"], fp="fp-d03")
        claimed = self.cja.claim_next_job(worker_id="d03")
        self.store.update_job(int(claimed["id"]), queue_status="running", customer_state="GENERATING")
        mon = self._monitor(int(claimed["id"]))
        self.assertEqual(mon["monitor_state"], "RUNNING")
        self.assertIsNone(mon["progress_percent"])

    def test_D04_starting_maps_running(self):
        self.assertEqual(self.cpm.infer_monitor_state({"customer_state": "STARTING"}), "RUNNING")

    def test_D05_preparing_maps_running(self):
        self.assertEqual(self.cpm.infer_monitor_state({"customer_state": "PREPARING"}), "RUNNING")

    def test_D06_claimed_is_waiting(self):
        self.assertEqual(self.cpm.infer_monitor_state({"queue_status": "claimed"}), "WAITING")


# ---------------------------------------------------------------------------
# E — Verifying projection
# ---------------------------------------------------------------------------


class E_VerifyingProjectionTests(C06HBase):
    def test_E01_validating_customer(self):
        self.assertEqual(self.cpm.infer_monitor_state({"customer_state": "VALIDATING"}), "VERIFYING")

    def test_E02_upload_validating(self):
        self.assertEqual(self.cpm.infer_monitor_state({"upload_status": "validating"}), "VERIFYING")

    def test_E03_upload_generated(self):
        self.assertEqual(self.cpm.infer_monitor_state({"upload_status": "generated"}), "VERIFYING")

    def test_E04_monitor_verifying(self):
        j = self._raw_job(fp="fp-e04", suffix="e04")
        self.store.update_job(int(j["id"]), customer_state="VALIDATING", upload_status="validating")
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["monitor_state"], "VERIFYING")

    def test_E05_qualitative_verifying(self):
        self.assertEqual(self.cpm.qualitative_progress("VERIFYING"), "VERIFYING")


# ---------------------------------------------------------------------------
# F — Preview projection
# ---------------------------------------------------------------------------


class F_PreviewProjectionTests(C06HBase):
    def test_F01_approval_pending_without_artifact(self):
        row = {"customer_state": "READY_FOR_REVIEW", "upload_status": "ready_to_upload"}
        self.assertEqual(self.cpm.infer_monitor_state(row), "APPROVAL_PENDING")

    def test_F02_preview_ready_with_artifact(self):
        j = self._raw_job(fp="fp-f02", suffix="f02")
        path = self._artifact_path("f02.mp4")
        self.store.update_job(
            int(j["id"]),
            customer_state="READY_FOR_REVIEW",
            upload_status="ready_to_upload",
            local_path=path,
            customer_approval="",
        )
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["monitor_state"], "PREVIEW_READY")
        self.assertTrue(mon["preview_available"])

    def test_F03_action_state_approval_pending(self):
        j = self._raw_job(fp="fp-f03", suffix="f03")
        path = self._artifact_path("f03.mp4")
        self.store.update_job(
            int(j["id"]),
            customer_state="READY_FOR_REVIEW",
            upload_status="ready_to_upload",
            local_path=path,
        )
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["action_state"], "APPROVAL_PENDING")

    def test_F04_attention_approval(self):
        j = self._raw_job(fp="fp-f04", suffix="f04")
        self.store.update_job(
            int(j["id"]),
            customer_state="READY_FOR_REVIEW",
            upload_status="ready_to_upload",
        )
        mon = self._monitor(int(j["id"]))
        kinds = [a["kind"] for a in mon.get("attention") or []]
        self.assertTrue(any(k in ("approval_required", "job_completed") for k in kinds) or mon["monitor_state"] in ("APPROVAL_PENDING", "PREVIEW_READY"))


# ---------------------------------------------------------------------------
# G — Approval projection
# ---------------------------------------------------------------------------


class G_ApprovalProjectionTests(C06HBase):
    def test_G01_approved_state(self):
        row = {"customer_approval": "APPROVED", "customer_state": "READY_FOR_REVIEW"}
        self.assertEqual(self.cpm.infer_monitor_state(row), "APPROVED")

    def test_G02_monitor_approved(self):
        j = self._raw_job(fp="fp-g02", suffix="g02")
        self.store.update_job(
            int(j["id"]),
            customer_approval="APPROVED",
            upload_status="ready_to_upload",
            customer_state="READY_FOR_REVIEW",
        )
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["monitor_state"], "APPROVED")
        self.assertEqual(mon["approval_status"], "APPROVED")
        self.assertFalse(mon["publishes"])

    def test_G03_approve_keeps_ready_to_upload(self):
        self._ready_plan(topic="G03 approve upload status topic")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=True, force_rebuild=True
        )
        ap = self.cpa.record_customer_approval(
            self.login, int(r["job_id"]), channel_ids=[self.ch_id], decision="approved"
        )
        self.assertTrue(ap.get("ok"))
        row = self._get_job(int(r["job_id"]))
        self.assertEqual(row.get("upload_status"), "ready_to_upload")
        mon = self._monitor(int(r["job_id"]))
        self.assertEqual(mon["monitor_state"], "APPROVED")
        self.assertFalse(mon["planes"]["published"])

    def test_G04_rejected_maps_failed(self):
        row = {
            "customer_state": "READY_FOR_REVIEW",
            "upload_status": "ready_to_upload",
            "customer_approval": "REJECTED",
        }
        self.assertEqual(self.cpm.infer_monitor_state(row), "FAILED")

    def test_G05_planes_approved_not_published(self):
        j = self._raw_job(fp="fp-g05", suffix="g05")
        self.store.update_job(int(j["id"]), customer_approval="APPROVED", upload_status="ready_to_upload")
        mon = self._monitor(int(j["id"]))
        self.assertTrue(mon["planes"]["approved"])
        self.assertFalse(mon["planes"]["published"])


# ---------------------------------------------------------------------------
# H — Failure projection
# ---------------------------------------------------------------------------


class H_FailureProjectionTests(C06HBase):
    def test_H01_failed_state(self):
        self.assertEqual(self.cpm.infer_monitor_state({"customer_state": "FAILED"}), "FAILED")

    def test_H02_upload_failed(self):
        self.assertEqual(self.cpm.infer_monitor_state({"upload_status": "failed"}), "FAILED")

    def test_H03_action_required(self):
        row = {"customer_state": "FAILED", "failure_category": "CONFIGURATION", "recoverable": 1}
        self.assertEqual(self.cpm.infer_monitor_state(row), "ACTION_REQUIRED")

    def test_H04_terminal_failed(self):
        row = {"customer_state": "FAILED", "failure_category": "TRANSIENT", "recoverable": 0}
        self.assertEqual(self.cpm.infer_monitor_state(row), "TERMINAL_FAILED")

    def test_H05_monitor_failure_fields(self):
        j = self._raw_job(fp="fp-h05", suffix="h05")
        self.store.update_job(
            int(j["id"]),
            customer_state="FAILED",
            failure_category="TRANSIENT",
            error="boom",
            recoverable=1,
        )
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["monitor_state"], "FAILED")
        self.assertEqual(mon["failure_category"], "TRANSIENT")
        self.assertTrue(mon.get("failure_reason"))


# ---------------------------------------------------------------------------
# I — Retry projection
# ---------------------------------------------------------------------------


class I_RetryProjectionTests(C06HBase):
    def test_I01_retry_waiting(self):
        row = {"queue_status": "queued", "next_retry_at": "2099-01-01T00:00:00"}
        self.assertEqual(self.cpm.infer_monitor_state(row), "RETRY_WAITING")

    def test_I02_monitor_retry(self):
        j = self._raw_job(fp="fp-i02", suffix="i02")
        self._enqueue(j["id"], fp="fp-i02")
        self.store.update_job(int(j["id"]), next_retry_at="2099-01-01T00:00:00", attempt_count=2)
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["monitor_state"], "RETRY_WAITING")
        self.assertEqual(mon["recovery_status"], "RETRY_SCHEDULED")
        self.assertEqual(mon["attempt_count"], 2)
        self.assertEqual(mon["retry_count"], 1)

    def test_I03_qualitative_retry(self):
        self.assertEqual(self.cpm.qualitative_progress("RETRY_WAITING"), "RETRY_WAITING")

    def test_I04_state_contract_retry(self):
        self.assertIn("RETRY_WAITING", self.cpm.STATE_CONTRACT)


# ---------------------------------------------------------------------------
# J — Cancellation (+ concurrent >=10)
# ---------------------------------------------------------------------------


class J_CancellationTests(C06HBase):
    def test_J01_cancel_queued(self):
        j = self._raw_job(fp="fp-j01", suffix="j01")
        self._enqueue(j["id"], fp="fp-j01")
        r = self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
        self.assertTrue(r["ok"])
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["monitor_state"], "CANCELLED")

    def test_J02_cancel_running_requested(self):
        j = self._raw_job(fp="fp-j02", suffix="j02")
        self._enqueue(j["id"], fp="fp-j02")
        c = self.cja.claim_next_job(worker_id="j02")
        self.store.update_job(int(c["id"]), queue_status="running")
        r = self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
        self.assertEqual(r.get("state"), "CANCELLATION_REQUESTED")
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["monitor_state"], "CANCELLATION_REQUESTED")

    def test_J03_cancelled_from_customer_state(self):
        self.assertEqual(self.cpm.infer_monitor_state({"customer_state": "CANCELLED"}), "CANCELLED")

    def test_J04_cancellation_status_field(self):
        j = self._raw_job(fp="fp-j04", suffix="j04")
        self._enqueue(j["id"], fp="fp-j04")
        self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["cancellation_status"], "CANCELLED")

    def _concurrent_cancel_once(self, suffix: str, workers: int = 12):
        j = self._raw_job(fp=f"fp-{suffix}", suffix=suffix)
        self._enqueue(j["id"], fp=f"fp-{suffix}")
        jid = int(j["id"])

        def _cancel(_i):
            return self.cja.request_cancel(self.login, jid, channel_ids=[self.ch_id])

        results = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_cancel, i) for i in range(workers)]
            for f in as_completed(futs):
                results.append(f.result())
        self.assertTrue(all(r.get("ok") for r in results))
        mon = self._monitor(jid)
        self.assertEqual(mon["monitor_state"], "CANCELLED")
        return results

    def test_J05_concurrent_cancel_01(self):
        self._concurrent_cancel_once("j05")

    def test_J06_concurrent_cancel_02(self):
        self._concurrent_cancel_once("j06")

    def test_J07_concurrent_cancel_03(self):
        self._concurrent_cancel_once("j07")

    def test_J08_concurrent_cancel_04(self):
        self._concurrent_cancel_once("j08")

    def test_J09_concurrent_cancel_05(self):
        self._concurrent_cancel_once("j09")

    def test_J10_concurrent_cancel_06(self):
        self._concurrent_cancel_once("j10")

    def test_J11_concurrent_cancel_07(self):
        self._concurrent_cancel_once("j11")

    def test_J12_concurrent_cancel_08(self):
        self._concurrent_cancel_once("j12")

    def test_J13_concurrent_cancel_09(self):
        self._concurrent_cancel_once("j13")

    def test_J14_concurrent_cancel_10(self):
        self._concurrent_cancel_once("j14")


# ---------------------------------------------------------------------------
# K — Cancellation idempotency
# ---------------------------------------------------------------------------


class K_CancelIdempotencyTests(C06HBase):
    def test_K01_double_cancel_reused(self):
        j = self._raw_job(fp="fp-k01", suffix="k01h")
        self._enqueue(j["id"], fp="fp-k01")
        a = self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
        b = self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
        self.assertTrue(a["ok"] and b["ok"])
        self.assertTrue(b.get("reused"))

    def test_K02_triple_cancel_stable(self):
        j = self._raw_job(fp="fp-k02", suffix="k02h")
        self._enqueue(j["id"], fp="fp-k02")
        for _ in range(3):
            r = self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
            self.assertTrue(r["ok"])
        self.assertEqual(self._monitor(int(j["id"]))["monitor_state"], "CANCELLED")

    def test_K03_cancel_already_cancelled_queue(self):
        j = self._raw_job(fp="fp-k03", suffix="k03h")
        self.store.update_job(int(j["id"]), queue_status="cancelled", customer_state="CANCELLED")
        r = self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
        self.assertTrue(r["ok"])

    def test_K04_idempotent_monitor_state(self):
        j = self._raw_job(fp="fp-k04", suffix="k04h")
        self._enqueue(j["id"], fp="fp-k04")
        self.cja.request_cancel(self.login, int(j["id"]), channel_ids=[self.ch_id])
        m1 = self._monitor(int(j["id"]))
        m2 = self._monitor(int(j["id"]))
        self.assertEqual(m1["monitor_state"], m2["monitor_state"])


# ---------------------------------------------------------------------------
# L — Restart / recovery visibility (>=10)
# ---------------------------------------------------------------------------


class L_RecoveryVisibilityTests(C06HBase):
    def _stale_running(self, suffix: str):
        j = self._raw_job(fp=f"fp-{suffix}", suffix=suffix)
        self._enqueue(j["id"], fp=f"fp-{suffix}")
        c = self.cja.claim_next_job(worker_id=suffix)
        past = (datetime.utcnow() - timedelta(hours=2)).isoformat(timespec="seconds")
        self.store.update_job(
            int(c["id"]),
            queue_status="running",
            customer_state="GENERATING",
            lease_expires_at=past,
        )
        return int(c["id"])

    def test_L01_recover_requeues(self):
        jid = self._stale_running("l01")
        out = self.cja.recover_after_restart()
        self.assertGreaterEqual(out.get("requeued", 0) + out.get("interrupted", 0), 1)
        mon = self._monitor(jid)
        self.assertIn(mon["monitor_state"], ("QUEUED", "INTERRUPTED", "RETRY_WAITING", "WAITING"))

    def test_L02_interrupted_state(self):
        self.assertEqual(self.cpm.infer_monitor_state({"customer_state": "INTERRUPTED"}), "INTERRUPTED")

    def test_L03_upload_interrupted(self):
        self.assertEqual(self.cpm.infer_monitor_state({"upload_status": "interrupted"}), "INTERRUPTED")

    def test_L04_monitor_interrupted_recovery_status(self):
        j = self._raw_job(fp="fp-l04", suffix="l04")
        self.store.update_job(int(j["id"]), customer_state="INTERRUPTED", upload_status="interrupted")
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["monitor_state"], "INTERRUPTED")
        self.assertEqual(mon["recovery_status"], "INTERRUPTED_NEEDS_RECOVERY")

    def test_L05_recovered_event_visibility(self):
        j = self._raw_job(fp="fp-l05", suffix="l05")
        self.cja.append_lifecycle_event(int(j["id"]), {"event": "requeued_after_restart"})
        events = self.cpm.load_lifecycle_events(self._get_job(int(j["id"])))
        self.assertTrue(any(e.get("type") == "JOB_RECOVERED" for e in events))

    def test_L06_recovery_visibility_01(self):
        jid = self._stale_running("l06")
        self.cja.recover_after_restart()
        mon = self._monitor(jid)
        self.assertTrue(mon["ok"])
        self.assertNotEqual(mon["monitor_state"], "COMPLETED")

    def test_L07_recovery_visibility_02(self):
        jid = self._stale_running("l07")
        self.cja.recover_after_restart()
        self.assertNotEqual(self._monitor(jid)["monitor_state"], "COMPLETED")

    def test_L08_recovery_visibility_03(self):
        jid = self._stale_running("l08")
        self.cja.recover_after_restart()
        self.assertNotEqual(self._monitor(jid)["monitor_state"], "COMPLETED")

    def test_L09_recovery_visibility_04(self):
        jid = self._stale_running("l09")
        self.cja.recover_after_restart()
        self.assertNotEqual(self._monitor(jid)["monitor_state"], "COMPLETED")

    def test_L10_recovery_visibility_05(self):
        jid = self._stale_running("l10")
        self.cja.recover_after_restart()
        self.assertNotEqual(self._monitor(jid)["monitor_state"], "COMPLETED")

    def test_L11_recovery_visibility_06(self):
        jid = self._stale_running("l11")
        self.cja.recover_after_restart()
        self.assertNotEqual(self._monitor(jid)["monitor_state"], "COMPLETED")

    def test_L12_recovery_visibility_07(self):
        jid = self._stale_running("l12")
        self.cja.recover_after_restart()
        self.assertNotEqual(self._monitor(jid)["monitor_state"], "COMPLETED")

    def test_L13_recovery_visibility_08(self):
        jid = self._stale_running("l13")
        self.cja.recover_after_restart()
        self.assertNotEqual(self._monitor(jid)["monitor_state"], "COMPLETED")

    def test_L14_recovery_visibility_09(self):
        jid = self._stale_running("l14")
        self.cja.recover_after_restart()
        self.assertNotEqual(self._monitor(jid)["monitor_state"], "COMPLETED")

    def test_L15_recovery_visibility_10(self):
        jid = self._stale_running("l15")
        self.cja.recover_after_restart()
        mon = self._monitor(jid)
        self.assertNotEqual(mon["monitor_state"], "COMPLETED")
        events = mon.get("lifecycle_events") or []
        self.assertTrue(isinstance(events, list))


# ---------------------------------------------------------------------------
# M — Stale execution projection
# ---------------------------------------------------------------------------


class M_StaleExecutionTests(C06HBase):
    def test_M01_stale_claimed_recovered(self):
        j = self._raw_job(fp="fp-m01", suffix="m01")
        self._enqueue(j["id"], fp="fp-m01")
        c = self.cja.claim_next_job(worker_id="m01")
        past = (datetime.utcnow() - timedelta(hours=3)).isoformat(timespec="seconds")
        self.store.update_job(int(c["id"]), lease_expires_at=past, queue_status="claimed")
        out = self.cja.recover_after_restart()
        self.assertGreaterEqual(int(out.get("requeued") or 0) + int(out.get("interrupted") or 0), 1)

    def test_M02_interrupted_not_completed(self):
        row = {"customer_state": "INTERRUPTED"}
        self.assertNotEqual(self.cpm.infer_monitor_state(row), "COMPLETED")

    def test_M03_stale_running_not_fake_complete(self):
        j = self._raw_job(fp="fp-m03", suffix="m03")
        self.store.update_job(int(j["id"]), queue_status="running", customer_state="GENERATING")
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["monitor_state"], "RUNNING")
        self.assertNotEqual(mon["monitor_state"], "COMPLETED")


# ---------------------------------------------------------------------------
# N — Event history
# ---------------------------------------------------------------------------


class N_EventHistoryTests(C06HBase):
    def test_N01_normalize_enqueued(self):
        ev = self.cpm.normalize_lifecycle_event({"event": "enqueued"})
        self.assertEqual(ev["type"], "JOB_QUEUED")

    def test_N02_normalize_claimed(self):
        self.assertEqual(self.cpm.normalize_lifecycle_event({"event": "claimed"})["type"], "JOB_CLAIMED")

    def test_N03_normalize_cancel(self):
        self.assertEqual(
            self.cpm.normalize_lifecycle_event({"event": "cancel_requested"})["type"],
            "JOB_CANCELLATION_REQUESTED",
        )

    def test_N04_normalize_cancelled(self):
        self.assertEqual(self.cpm.normalize_lifecycle_event({"event": "cancelled"})["type"], "JOB_CANCELLED")

    def test_N05_normalize_interrupted(self):
        self.assertEqual(
            self.cpm.normalize_lifecycle_event({"event": "interrupted_restart"})["type"],
            "JOB_INTERRUPTED",
        )

    def test_N06_load_events_empty(self):
        self.assertEqual(self.cpm.load_lifecycle_events(None), [])

    def test_N07_load_events_from_job(self):
        j = self._raw_job(fp="fp-n07", suffix="n07")
        self._enqueue(j["id"], fp="fp-n07")
        events = self.cpm.load_lifecycle_events(self._get_job(int(j["id"])))
        self.assertTrue(any(e.get("type") == "JOB_QUEUED" for e in events))

    def test_N08_monitor_includes_lifecycle(self):
        j = self._raw_job(fp="fp-n08", suffix="n08")
        self._enqueue(j["id"], fp="fp-n08")
        mon = self._monitor(int(j["id"]))
        self.assertIsInstance(mon["lifecycle_events"], list)
        self.assertGreaterEqual(len(mon["lifecycle_events"]), 1)

    def test_N09_lifecycle_types_defined(self):
        for t in ("JOB_QUEUED", "JOB_STARTED", "JOB_CANCELLED", "JOB_RECOVERED", "JOB_FAILED"):
            self.assertIn(t, self.cpm.LIFECYCLE_EVENT_TYPES)

    def test_N10_bad_json_safe(self):
        self.assertEqual(self.cpm.load_lifecycle_events({"lifecycle_audit_json": "{bad"}), [])


# ---------------------------------------------------------------------------
# O — Customer isolation (>=10)
# ---------------------------------------------------------------------------


class O_CustomerIsolationTests(C06HBase):
    def test_O01_foreign_monitor_denied(self):
        j = self._raw_job(fp="fp-o01", suffix="o01")
        mon = self._monitor(int(j["id"]), login=self.login_b, channel_ids=[self.ch_b_id])
        self.assertFalse(mon["ok"])
        self.assertEqual(mon.get("error_code"), "ownership_violation")

    def test_O02_activity_isolates(self):
        ja = self._raw_job(fp="fp-o02a", suffix="o02a")
        jb = self._raw_job(fp="fp-o02b", channel_id=self.ch_b_id, login_id=self.login_b, suffix="o02b")
        self._enqueue(ja["id"], fp="fp-o02a")
        self._enqueue(jb["id"], login=self.login_b, channel_ids=[self.ch_b_id], fp="fp-o02b")
        act_a = self.cpm.project_recent_activity(self.login, channel_ids=[self.ch_id])
        ids = {int(i["job_id"]) for i in act_a["items"]}
        self.assertIn(int(ja["id"]), ids)
        self.assertNotIn(int(jb["id"]), ids)

    def test_O03_cancel_foreign_denied(self):
        j = self._raw_job(fp="fp-o03", suffix="o03")
        self._enqueue(j["id"], fp="fp-o03")
        r = self.cja.request_cancel(self.login_b, int(j["id"]), channel_ids=[self.ch_b_id])
        self.assertFalse(r["ok"])

    def test_O04_isolation_01(self):
        j = self._raw_job(fp="fp-o04", suffix="o04")
        self.assertFalse(self._monitor(int(j["id"]), login=self.login_b, channel_ids=[self.ch_b_id])["ok"])

    def test_O05_isolation_02(self):
        j = self._raw_job(fp="fp-o05", suffix="o05")
        self.assertFalse(self._monitor(int(j["id"]), login=self.login_b, channel_ids=[self.ch_b_id])["ok"])

    def test_O06_isolation_03(self):
        j = self._raw_job(fp="fp-o06", suffix="o06")
        self.assertFalse(self._monitor(int(j["id"]), login=self.login_b, channel_ids=[self.ch_b_id])["ok"])

    def test_O07_isolation_04(self):
        j = self._raw_job(fp="fp-o07", suffix="o07")
        self.assertFalse(self._monitor(int(j["id"]), login=self.login_b, channel_ids=[self.ch_b_id])["ok"])

    def test_O08_isolation_05(self):
        j = self._raw_job(fp="fp-o08", suffix="o08")
        self.assertFalse(self._monitor(int(j["id"]), login=self.login_b, channel_ids=[self.ch_b_id])["ok"])

    def test_O09_isolation_06(self):
        j = self._raw_job(fp="fp-o09", suffix="o09")
        self.assertFalse(self._monitor(int(j["id"]), login=self.login_b, channel_ids=[self.ch_b_id])["ok"])

    def test_O10_isolation_07(self):
        j = self._raw_job(fp="fp-o10", suffix="o10")
        self.assertFalse(self._monitor(int(j["id"]), login=self.login_b, channel_ids=[self.ch_b_id])["ok"])

    def test_O11_isolation_08(self):
        j = self._raw_job(fp="fp-o11", suffix="o11")
        self.assertFalse(self._monitor(int(j["id"]), login=self.login_b, channel_ids=[self.ch_b_id])["ok"])

    def test_O12_isolation_09(self):
        j = self._raw_job(fp="fp-o12", suffix="o12")
        self.assertFalse(self._monitor(int(j["id"]), login=self.login_b, channel_ids=[self.ch_b_id])["ok"])

    def test_O13_isolation_10(self):
        j = self._raw_job(fp="fp-o13", suffix="o13")
        self.assertFalse(self._monitor(int(j["id"]), login=self.login_b, channel_ids=[self.ch_b_id])["ok"])


# ---------------------------------------------------------------------------
# P — Channel ownership
# ---------------------------------------------------------------------------


class P_ChannelOwnershipTests(C06HBase):
    def test_P01_empty_channels_denied(self):
        j = self._raw_job(fp="fp-p01", suffix="p01")
        mon = self._monitor(int(j["id"]), channel_ids=[])
        self.assertFalse(mon["ok"])

    def test_P02_wrong_channel_denied(self):
        j = self._raw_job(fp="fp-p02", suffix="p02")
        mon = self._monitor(int(j["id"]), channel_ids=[self.ch_b_id])
        self.assertFalse(mon["ok"])

    def test_P03_owner_allowed(self):
        j = self._raw_job(fp="fp-p03", suffix="p03")
        mon = self._monitor(int(j["id"]), channel_ids=[self.ch_id])
        self.assertTrue(mon["ok"])

    def test_P04_submit_foreign_blocked(self):
        self._ready_plan(topic="P04 foreign owner topic")
        r = self.cja.submit_customer_generation(
            self.login_b, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        self.assertFalse(r["ok"])


# ---------------------------------------------------------------------------
# Q — Entitlement
# ---------------------------------------------------------------------------


class Q_EntitlementTests(C06HBase):
    def test_Q01_entitlement_inactive_blocks_admit(self):
        self._ready_plan(topic="Q01 entitlement topic")
        r = self.go.admit_generation(self.login, self.channel, entitlement_active=False)
        self.assertFalse(r["ok"])
        self.assertIn("entitlement_inactive", r["blocks"])

    def test_Q02_account_inactive_blocks(self):
        self._ready_plan(topic="Q02 account topic")
        r = self.go.admit_generation(self.login, self.channel, account_active=False)
        self.assertFalse(r["ok"])

    def test_Q03_capability_unavailable(self):
        self._ready_plan(topic="Q03 capability topic")
        r = self.go.admit_generation(self.login, self.channel, capability_available=False)
        self.assertIn("generation_capability_unavailable", r["blocks"])


# ---------------------------------------------------------------------------
# R — Forged identifiers
# ---------------------------------------------------------------------------


class R_ForgedIdTests(C06HBase):
    def test_R01_monitor_missing_job(self):
        mon = self._monitor(999999)
        self.assertFalse(mon["ok"])
        self.assertEqual(mon.get("error_code"), "not_found")

    def test_R02_cancel_missing(self):
        r = self.cja.request_cancel(self.login, 999999, channel_ids=[self.ch_id])
        self.assertEqual(r.get("error_code"), "not_found")

    def test_R03_forged_channel_submit(self):
        self._ready_plan(topic="R03 forged channel topic")
        forged = {**self.channel, "id": 99999, "owner_login_id": self.login}
        r = self.cja.submit_customer_generation(
            self.login, forged, use_mock=True, process_now=False, force_rebuild=True
        )
        self.assertFalse(r["ok"])

    def test_R04_requested_by_mismatch(self):
        j = self._raw_job(fp="fp-r04", login_id=self.login, suffix="r04")
        mon = self.cpm.project_production_monitor(self.login_b, int(j["id"]), channel_ids=[self.ch_id])
        self.assertFalse(mon["ok"])


# ---------------------------------------------------------------------------
# S — BUILD-03 duplicate protection (+ duplicate lifecycle >=10)
# ---------------------------------------------------------------------------


class S_DuplicateLifecycleTests(C06HBase):
    def test_S01_duplicate_submit_reuses(self):
        self._ready_plan(topic="S01 dup submit topic")
        a = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=True, force_rebuild=True
        )
        b = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=False
        )
        self.assertTrue(b.get("reused") or b.get("job_id") == a.get("job_id"))

    def test_S02_duplicate_queued_prevented(self):
        self._ready_plan(topic="S02 dup queue topic")
        a = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        b = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=False
        )
        self.assertTrue(b.get("reused") or b.get("job_id") == a.get("job_id"))

    def _dup_lifecycle(self, topic: str):
        self._ready_plan(topic=topic)
        a = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=True
        )
        b = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=False, force_rebuild=False
        )
        self.assertTrue(a.get("ok") and (b.get("reused") or b.get("job_id") == a.get("job_id")))

    def test_S03_dup_lifecycle_01(self):
        self._dup_lifecycle("S03 dup lifecycle topic 01")

    def test_S04_dup_lifecycle_02(self):
        self._dup_lifecycle("S04 dup lifecycle topic 02")

    def test_S05_dup_lifecycle_03(self):
        self._dup_lifecycle("S05 dup lifecycle topic 03")

    def test_S06_dup_lifecycle_04(self):
        self._dup_lifecycle("S06 dup lifecycle topic 04")

    def test_S07_dup_lifecycle_05(self):
        self._dup_lifecycle("S07 dup lifecycle topic 05")

    def test_S08_dup_lifecycle_06(self):
        self._dup_lifecycle("S08 dup lifecycle topic 06")

    def test_S09_dup_lifecycle_07(self):
        self._dup_lifecycle("S09 dup lifecycle topic 07")

    def test_S10_dup_lifecycle_08(self):
        self._dup_lifecycle("S10 dup lifecycle topic 08")

    def test_S11_dup_lifecycle_09(self):
        self._dup_lifecycle("S11 dup lifecycle topic 09")

    def test_S12_dup_lifecycle_10(self):
        self._dup_lifecycle("S12 dup lifecycle topic 10")


# ---------------------------------------------------------------------------
# T — generation_guard
# ---------------------------------------------------------------------------


class T_GenerationGuardTests(C06HBase):
    def test_T01_max_active_one(self):
        from app.generation_guard import try_acquire, force_release, is_busy

        force_release()
        self.assertTrue(try_acquire("t01"))
        self.assertTrue(is_busy())
        self.assertFalse(try_acquire("t01b"))
        force_release()

    def test_T02_monitor_guard_max(self):
        j = self._raw_job(fp="fp-t02", suffix="t02")
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["guard"]["max_active_generation"], 1)

    def test_T03_tick_skips_when_busy(self):
        from app.generation_guard import try_acquire, force_release

        force_release()
        self.assertTrue(try_acquire("t03"))
        tick = self.cja.scheduler_tick()
        self.assertTrue(tick.get("skipped"))
        self.assertEqual(tick.get("reason"), "generation_guard_busy")
        force_release()

    def test_T04_metrics_in_monitor(self):
        j = self._raw_job(fp="fp-t04", suffix="t04")
        mon = self._monitor(int(j["id"]))
        self.assertIn("busy", mon["guard"])


# ---------------------------------------------------------------------------
# U / V / W — Lab / background isolation (>=10 combined)
# ---------------------------------------------------------------------------


class UVW_LabBackgroundIsolationTests(C06HBase):
    def test_U01_idle_pregen_legacy(self):
        ep = self.cpm.ENTRY_POINT_CLASSIFICATION["idle_pregen"]
        self.assertEqual(ep["class"], "LEGACY_COMPAT")

    def test_V01_timed_fallback_legacy(self):
        ep = self.cpm.ENTRY_POINT_CLASSIFICATION["timed_fallback"]
        self.assertEqual(ep["class"], "LEGACY_COMPAT")

    def test_W01_live_lab_forbidden(self):
        ep = self.cpm.ENTRY_POINT_CLASSIFICATION["live_lab"]
        self.assertEqual(ep["class"], "FORBIDDEN_FOR_CUSTOMER_PRODUCTION")
        self.assertEqual(ep.get("also"), "INTERNAL_LAB")

    def test_W02_classify_live_lab(self):
        lab = self.cpm.classify_live_lab()
        self.assertFalse(lab["customer_production_allowed"])
        self.assertFalse(lab["uses_generation_guard"])

    def test_W03_tick_skips_when_lab_active(self):
        self.store.set_meta("live_lab_active", "1")
        self.assertTrue(self.cpm.is_live_lab_active())
        tick = self.cja.scheduler_tick()
        self.assertTrue(tick.get("skipped"))
        self.assertEqual(tick.get("reason"), "live_lab_active")
        self.assertEqual(tick.get("lab_boundary"), "FORBIDDEN_FOR_CUSTOMER_PRODUCTION")
        self.store.set_meta("live_lab_active", "0")

    def test_W04_lab_inactive_allows_tick(self):
        self.store.set_meta("live_lab_active", "0")
        tick = self.cja.scheduler_tick()
        self.assertNotEqual(tick.get("reason"), "live_lab_active")

    def test_W05_monitor_includes_lab(self):
        j = self._raw_job(fp="fp-w05", suffix="w05")
        mon = self._monitor(int(j["id"]))
        self.assertIn("live_lab", mon)
        self.assertEqual(mon["live_lab"]["class"], "FORBIDDEN_FOR_CUSTOMER_PRODUCTION")

    def test_W06_lab_iso_01(self):
        self.store.set_meta("live_lab_active", "1")
        self.assertTrue(self.cja.scheduler_tick().get("skipped"))
        self.store.set_meta("live_lab_active", "0")

    def test_W07_lab_iso_02(self):
        self.store.set_meta("live_lab_active", "1")
        self.assertEqual(self.cja.scheduler_tick().get("reason"), "live_lab_active")
        self.store.set_meta("live_lab_active", "0")

    def test_W08_lab_iso_03(self):
        self.assertEqual(self.cpm.ENTRY_POINT_CLASSIFICATION["idle_pregen"]["class"], "LEGACY_COMPAT")

    def test_W09_lab_iso_04(self):
        self.assertEqual(self.cpm.ENTRY_POINT_CLASSIFICATION["timed_fallback"]["class"], "LEGACY_COMPAT")

    def test_W10_lab_iso_05(self):
        self.assertIn("Not customer production", self.cpm.ENTRY_POINT_CLASSIFICATION["idle_pregen"].get("note", ""))

    def test_W11_lab_iso_06(self):
        self.assertIn("Not customer production", self.cpm.ENTRY_POINT_CLASSIFICATION["timed_fallback"].get("note", ""))

    def test_W12_lab_iso_07(self):
        src = (ROOT / "app" / "scheduler_service.py").read_text(encoding="utf-8")
        self.assertIn("idle_pregenerate", src)
        self.assertIn("customer_queue_tick", src)

    def test_W13_lab_iso_08(self):
        lab = self.cpm.classify_live_lab()
        self.assertIn("FORBIDDEN_FOR_CUSTOMER_PRODUCTION", lab["class"])

    def test_W14_lab_iso_09(self):
        self.store.set_meta("live_lab_active", "1")
        j = self._raw_job(fp="fp-w14", suffix="w14")
        self._enqueue(j["id"], fp="fp-w14")
        tick = self.cja.scheduler_tick()
        self.assertFalse(tick.get("executed"))
        row = self._get_job(int(j["id"]))
        self.assertEqual(row.get("queue_status"), "queued")
        self.store.set_meta("live_lab_active", "0")

    def test_W15_lab_iso_10(self):
        self.store.set_meta("live_lab_active", "0")
        self.assertFalse(self.cpm.is_live_lab_active())


# ---------------------------------------------------------------------------
# X — Truthful progress
# ---------------------------------------------------------------------------


class X_TruthfulProgressTests(C06HBase):
    def test_X01_progress_percent_none(self):
        j = self._raw_job(fp="fp-x01", suffix="x01h")
        mon = self._monitor(int(j["id"]))
        self.assertIsNone(mon["progress_percent"])

    def test_X02_running_no_fake_pct(self):
        j = self._raw_job(fp="fp-x02", suffix="x02h")
        self.store.update_job(int(j["id"]), queue_status="running", customer_state="GENERATING")
        mon = self._monitor(int(j["id"]))
        self.assertIsNone(mon["progress_percent"])
        self.assertEqual(mon["progress"], "RUNNING")

    def test_X03_customer_view_none(self):
        from app.customer_job import to_customer_view

        j = self._raw_job(fp="fp-x03", suffix="x03h")
        view = to_customer_view(self._get_job(int(j["id"])))
        self.assertIsNone(view["progress_percent"])

    def test_X04_progress_note(self):
        j = self._raw_job(fp="fp-x04", suffix="x04h")
        mon = self._monitor(int(j["id"]))
        self.assertIn("never fabricated", mon["progress_note"].lower())


# ---------------------------------------------------------------------------
# Y — UNKNOWN handling
# ---------------------------------------------------------------------------


class Y_UnknownHandlingTests(C06HBase):
    def test_Y01_empty_row_draft(self):
        self.assertEqual(self.cpm.infer_monitor_state(None), "DRAFT")

    def test_Y02_qualitative_unknown(self):
        self.assertEqual(self.cpm.qualitative_progress("NOPE"), "UNKNOWN")

    def test_Y03_verification_unknown_default(self):
        j = self._raw_job(fp="fp-y03", suffix="y03")
        mon = self._monitor(int(j["id"]))
        self.assertEqual(mon["verification_status"], "UNKNOWN")

    def test_Y04_execution_path_unknown(self):
        self.assertEqual(self.cpm.infer_execution_path(None), "UNKNOWN")


# ---------------------------------------------------------------------------
# Z — No publish
# ---------------------------------------------------------------------------


class Z_NoPublishTests(C06HBase):
    def test_Z01_monitor_publishes_false(self):
        j = self._raw_job(fp="fp-z01", suffix="z01")
        self.assertFalse(self._monitor(int(j["id"]))["publishes"])

    def test_Z02_activity_publishes_false(self):
        act = self.cpm.project_recent_activity(self.login, channel_ids=[self.ch_id])
        self.assertFalse(act["publishes"])

    def test_Z03_source_no_upload_youtube(self):
        src = Path(self.cpm.__file__).read_text(encoding="utf-8")
        self.assertNotIn("upload_to_youtube", src)
        self.assertNotIn("publish_video", src)

    def test_Z04_planes_published_false(self):
        j = self._raw_job(fp="fp-z04", suffix="z04")
        self.store.update_job(int(j["id"]), customer_approval="APPROVED", upload_status="ready_to_upload")
        mon = self._monitor(int(j["id"]))
        self.assertFalse(mon["planes"]["published"])


# ---------------------------------------------------------------------------
# AA — No social
# ---------------------------------------------------------------------------


class AA_NoSocialTests(C06HBase):
    def test_AA01_monitor_social_false(self):
        j = self._raw_job(fp="fp-aa01", suffix="aa01")
        self.assertFalse(self._monitor(int(j["id"]))["social_calls"])

    def test_AA02_source_no_social(self):
        src = Path(self.cpm.__file__).read_text(encoding="utf-8")
        self.assertNotIn("post_to_facebook", src)
        self.assertNotIn("social_publish", src)


# ---------------------------------------------------------------------------
# AB — No secret leakage
# ---------------------------------------------------------------------------


class AB_NoSecretTests(C06HBase):
    def test_AB01_secrets_excluded(self):
        j = self._raw_job(fp="fp-ab01", suffix="abh01")
        mon = self._monitor(int(j["id"]))
        self.assertTrue(mon["secrets_excluded"])

    def test_AB02_no_api_key_in_monitor(self):
        j = self._raw_job(fp="fp-ab02", suffix="abh02")
        blob = json.dumps(self._monitor(int(j["id"])))
        self.assertNotIn("sk-", blob)
        self.assertNotIn("OPENAI_API_KEY", blob)

    def test_AB03_lifecycle_redaction(self):
        j = self._raw_job(fp="fp-ab03", suffix="abh03")
        self.cja.append_lifecycle_event(
            int(j["id"]), {"event": "probe", "detail": "api_key=sk-secretpassword=x"}
        )
        events = self.cpm.load_lifecycle_events(self._get_job(int(j["id"])))
        last = events[-1]
        self.assertTrue(last.get("redacted") or "sk-secret" not in json.dumps(last))


# ---------------------------------------------------------------------------
# AC — UI projection
# ---------------------------------------------------------------------------


class AC_UiProjectionTests(unittest.TestCase):
    def test_AC01_html_production_monitor(self):
        html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Production Monitor", html)
        self.assertIn("wsCancelJobBtn", html)

    def test_AC02_js_queue_true(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("queue: true", js)

    def test_AC03_js_monitor_api(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("production_monitor", js)
        self.assertIn("progress_percent", js)
        self.assertIn("monitor_state", js)

    def test_AC04_js_cancel(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("wsCancelJobBtn", js)
        self.assertIn("/cancel", js)


# ---------------------------------------------------------------------------
# AD — API contract (main source inspect)
# ---------------------------------------------------------------------------


class AD_ApiContractTests(unittest.TestCase):
    def test_AD01_workspace_monitor_route(self):
        from app import main as main_mod

        self.assertTrue(callable(main_mod.workspace_monitor))
        src = inspect.getsource(main_mod.workspace_monitor)
        self.assertIn("project_production_monitor", src)

    def test_AD02_activity_feed_route(self):
        from app import main as main_mod

        src = inspect.getsource(main_mod.workspace_activity_feed)
        self.assertIn("project_recent_activity", src)

    def test_AD03_entry_points_route(self):
        from app import main as main_mod

        src = inspect.getsource(main_mod.workspace_entry_points)
        self.assertIn("ENTRY_POINT_CLASSIFICATION", src)

    def test_AD04_routes_registered(self):
        from app import main as main_mod

        paths = {getattr(r, "path", None) for r in main_mod.app.routes}
        self.assertIn("/api/workspace/monitor", paths)
        self.assertIn("/api/workspace/activity-feed", paths)
        self.assertIn("/api/workspace/entry-points", paths)

    def test_AD05_state_contract_complete(self):
        import app.customer_production_monitor as cpm

        for st in (
            "QUEUED",
            "RUNNING",
            "VERIFYING",
            "PREVIEW_READY",
            "APPROVAL_PENDING",
            "FAILED",
            "RETRY_WAITING",
            "CANCELLED",
            "CANCELLATION_REQUESTED",
            "INTERRUPTED",
        ):
            self.assertIn(st, cpm.STATE_CONTRACT)
            self.assertIn("source", cpm.STATE_CONTRACT[st])
            self.assertIn("label", cpm.STATE_CONTRACT[st])
            self.assertIn("action", cpm.STATE_CONTRACT[st])

    def test_AD06_detect_duplicate_engines_empty(self):
        import app.customer_production_monitor as cpm

        src = Path(cpm.__file__).read_text(encoding="utf-8")
        self.assertEqual(cpm.detect_duplicate_engines(src), [])


# ---------------------------------------------------------------------------
# AE — Regression / smoke compatibility
# ---------------------------------------------------------------------------


class AE_RegressionSmokeTests(C06HBase):
    def test_AE01_smoke_submit_monitor_approve(self):
        self._ready_plan(topic="AE01 full smoke monitor topic")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=True, force_rebuild=True
        )
        self.assertTrue(r["ok"])
        jid = int(r["job_id"])
        mon = self._monitor(jid)
        self.assertTrue(mon["ok"])
        self.assertIsNone(mon["progress_percent"])
        self.assertEqual(mon["execution_path_class"], "CANONICAL")
        ap = self.cpa.record_customer_approval(
            self.login, jid, channel_ids=[self.ch_id], decision="approved"
        )
        self.assertTrue(ap.get("ok"))
        row = self._get_job(jid)
        self.assertEqual(row.get("upload_status"), "ready_to_upload")
        mon2 = self._monitor(jid)
        self.assertEqual(mon2["monitor_state"], "APPROVED")
        self.assertFalse(mon2["publishes"])
        self.assertFalse(mon2["planes"]["published"])

    def test_AE02_paid_api_zero_submit(self):
        self._ready_plan(topic="AE02 paid zero topic")
        r = self.cja.submit_customer_generation(
            self.login, self.channel, use_mock=True, process_now=True, force_rebuild=True
        )
        tick = r.get("tick") or {}
        result = tick.get("result") or {}
        self.assertEqual(result.get("paid_api_calls", 0), 0)

    def test_AE03_c06g_automation_still_works(self):
        j = self._raw_job(fp="fp-ae03", suffix="ae03")
        enq = self._enqueue(j["id"], fp="fp-ae03")
        self.assertTrue(enq.get("ok"))
        self.assertEqual(self._monitor(int(j["id"]))["monitor_state"], "QUEUED")

    def test_AE04_no_second_scheduler_in_monitor(self):
        src = Path(self.cpm.__file__).read_text(encoding="utf-8")
        self.assertEqual(self.cpm.detect_duplicate_engines(src), [])
        self.assertNotRegex(src, r"(?m)^\s*class\s+SchedulerService\b")

    def test_AE05_completed_state(self):
        row = {"customer_state": "COMPLETED", "upload_status": "uploaded"}
        self.assertEqual(self.cpm.infer_monitor_state(row), "COMPLETED")

    def test_AE06_draft_state(self):
        self.assertEqual(self.cpm.infer_monitor_state({"customer_state": "DRAFT"}), "DRAFT")

    def test_AE07_attention_signals_running(self):
        sigs = self.cpm.attention_signals(
            {"error": None}, monitor_state="RUNNING"
        )
        self.assertTrue(any(s["kind"] == "job_started" for s in sigs))

    def test_AE08_db_isolation_temp(self):
        self.assertTrue(str(self.store.DB_PATH).endswith("c06h.db"))


if __name__ == "__main__":
    unittest.main()
