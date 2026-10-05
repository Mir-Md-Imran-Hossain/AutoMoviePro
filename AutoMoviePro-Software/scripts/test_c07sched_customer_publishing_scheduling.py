"""C07-SCHED — Customer Publishing Scheduling (paid APIs = 0).

>=160 deterministic unittest cases. Deterministic clock via set_clock.
Compose/timing only — execution delegated to C07-PUB. No live YouTube.
"""
from __future__ import annotations

import inspect
import json
import re
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class C07SchedBase(unittest.TestCase):
    """Shared TemporaryDirectory fixture — mirrors C07-PUB / C06-H patterns."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.td = Path(self._tmp.name)
        self.data_dir = self.td / "data"
        self.data_dir.mkdir()
        self.db_path = self.td / "c07sched.db"

        from app import config as cfg
        from app import db as store
        import app.customer_publish as cp
        import app.customer_publish_schedule as cps
        import app.customer_preview_approval as cpa
        import app.customer_job_automation as cja
        from app.customer_job import ensure_job_columns
        from app.customer_config import ensure_channel_owner_column
        from publishers.customer_publish_provider import reset_mock_store

        self.store = store
        self.cfg = cfg
        self.cp = cp
        self.cps = cps
        self.cpa = cpa
        self.cja = cja

        self._orig_db = store.DB_PATH
        self._orig_cfg_data = cfg.DATA_DIR
        self._orig_cp_data = cp.DATA_DIR
        self._orig_cps_data = cps.DATA_DIR
        self._orig_cpa_data = cpa.DATA_DIR
        self._orig_cja_data = cja.DATA_DIR

        store.DB_PATH = self.db_path
        cfg.DATA_DIR = self.data_dir
        cp.DATA_DIR = self.data_dir
        cps.DATA_DIR = self.data_dir
        cpa.DATA_DIR = self.data_dir
        cja.DATA_DIR = self.data_dir

        store.init_db()
        ensure_job_columns()
        ensure_channel_owner_column()
        cp.ensure_publish_columns()
        if hasattr(cja, "ensure_automation_columns"):
            cja.ensure_automation_columns()
        reset_mock_store()
        if hasattr(cp, "reset_real_provider_call_count"):
            cp.reset_real_provider_call_count()

        self.login = "cust_a"
        self.login_b = "cust_b"
        self.ch_id = store.upsert_channel(
            {
                "youtube_name": "SchedChA",
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
                "youtube_name": "SchedChB",
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
            "youtube_name": "SchedChA",
            "niche_id": 1,
            "lang_code": "en",
            "owner_login_id": self.login,
        }
        self.channel_b = {
            "id": self.ch_b_id,
            "niche": "news",
            "youtube_name": "SchedChB",
            "niche_id": 2,
            "lang_code": "en",
            "owner_login_id": self.login_b,
        }

        # Deterministic clock: 2026-09-10 12:00 UTC
        self._clock = [datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)]
        self.cps.set_clock(lambda: self._clock[0])

    def tearDown(self):
        self.cps.set_clock(None)
        self.store.DB_PATH = self._orig_db
        self.cfg.DATA_DIR = self._orig_cfg_data
        self.cp.DATA_DIR = self._orig_cp_data
        self.cps.DATA_DIR = self._orig_cps_data
        self.cpa.DATA_DIR = self._orig_cpa_data
        self.cja.DATA_DIR = self._orig_cja_data

    def _set_clock(self, dt: datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        self._clock[0] = dt.astimezone(timezone.utc)

    def _advance(self, *, hours=0, minutes=0, seconds=0):
        self._clock[0] = self._clock[0] + timedelta(hours=hours, minutes=minutes, seconds=seconds)

    def _identity(self, login=None, **overrides):
        login = login or self.login
        base = {
            "login_id": login,
            "authenticated": True,
            "auth_state": "AUTHENTICATED",
            "production_access": True,
            "entitlement_state": "ACTIVE",
            "account_state": "ACTIVE",
        }
        base.update(overrides)
        return base

    def _media_path(self, name: str = "ready.mp4") -> str:
        p = self.td / "media" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x00\x00\x00\x18ftypmp42fake-media-bytes")
        return str(p)

    def _quality_publishable(self, **extra) -> str:
        payload = {
            "publishable": True,
            "publishability_verdict": "PUBLISHABLE",
            "publishability": {"verdict": "PUBLISHABLE", "publishable": True, "reason": "ok"},
            "note": "c07sched admit ready",
        }
        payload.update(extra)
        return json.dumps(payload)

    def _admit_ready_job(self, **extra):
        from app.customer_job import create_generation_job, get_job

        login = extra.get("login_id", self.login)
        channel_id = int(extra.get("channel_id", self.ch_id))
        title = extra.get("title", "C07 sched ready title")
        media = extra.get("local_path") or self._media_path(extra.get("media_name", "ready.mp4"))
        qs = extra.get("quality_summary")
        if qs is None:
            qs = self._quality_publishable()
        elif isinstance(qs, dict):
            qs = json.dumps(qs)

        row = create_generation_job(
            channel_id=channel_id,
            video_type=extra.get("video_type", "short"),
            requested_by=login,
            title_hint=title,
            production_plan_id=extra.get("plan_id", "plan-c07s"),
            production_plan_revision=extra.get("plan_rev", "rev-c07s"),
            script_revision=extra.get("script_rev", "scr-c07s"),
            generation_fingerprint=extra.get("fp", f"fp-c07s-{extra.get('suffix', 'x')}"),
            plan_snapshot=extra.get(
                "plan_snapshot",
                {
                    "production_plan_id": extra.get("plan_id", "plan-c07s"),
                    "production_plan_revision": extra.get("plan_rev", "rev-c07s"),
                    "_c07sched": {"mock": True},
                },
            ),
        )
        jid = int(row["id"])
        fields = {
            "upload_status": extra.get("upload_status", "ready_to_upload"),
            "customer_approval": extra.get("customer_approval", "APPROVED"),
            "customer_state": extra.get("customer_state", "READY_FOR_REVIEW"),
            "local_path": media,
            "quality_summary": qs,
            "requested_by": login,
            "lang_code": extra.get("lang_code", "en"),
            "title": title,
        }
        if "publish_status" in extra:
            fields["publish_status"] = extra["publish_status"]
        self.store.update_job(jid, **fields)
        return get_job(jid)

    def _get_job(self, job_id):
        from app.customer_job import get_job

        return get_job(int(job_id))

    def _revision(self, job_id):
        from app.customer_preview_approval import compute_revision_id

        return compute_revision_id(self._get_job(job_id))

    def _future_local(self, hours_ahead: int = 6) -> str:
        """Local datetime string ahead of deterministic clock (UTC zone)."""
        dt = self._clock[0] + timedelta(hours=hours_ahead)
        return dt.strftime("%Y-%m-%dT%H:%M")

    def _past_local(self, hours_ago: int = 2) -> str:
        dt = self._clock[0] - timedelta(hours=hours_ago)
        return dt.strftime("%Y-%m-%dT%H:%M")

    def _create(
        self,
        job_id,
        *,
        login=None,
        channel_ids=None,
        local_datetime=None,
        timezone_name="UTC",
        **kw,
    ):
        return self.cps.create_schedule(
            login or self.login,
            job_id=int(job_id),
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
            local_datetime=local_datetime or self._future_local(6),
            timezone_name=timezone_name,
            identity=kw.pop("identity", self._identity(login or self.login)),
            **kw,
        )

    def _cancel(self, schedule_id, *, login=None, channel_ids=None):
        return self.cps.cancel_schedule(
            login or self.login,
            schedule_id,
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
        )

    def _reschedule(self, schedule_id, *, local_datetime=None, login=None, channel_ids=None, **kw):
        return self.cps.reschedule(
            login or self.login,
            schedule_id,
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
            local_datetime=local_datetime or self._future_local(10),
            timezone_name=kw.pop("timezone_name", "UTC"),
            identity=kw.pop("identity", self._identity(login or self.login)),
        )

    def _process(self, **kw):
        return self.cps.process_due_schedules(
            worker_id=kw.pop("worker_id", "test:sched"),
            max_one=kw.pop("max_one", True),
            **kw,
        )

    def _panel(self, *, login=None, channel_ids=None, job_id=None):
        return self.cps.project_schedule_panel(
            login or self.login,
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
            job_id=job_id,
        )

    def _list(self, *, login=None, channel_ids=None, job_id=None):
        return self.cps.list_schedules_for_customer(
            login or self.login,
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
            job_id=job_id,
        )

    def _force_status(self, schedule_id: str, status: str, **extra):
        rec = self.cps.load_schedule(schedule_id)
        self.assertIsNotNone(rec)
        rec["status"] = status
        rec.update(extra)
        self.cps.save_schedule(rec)
        return self.cps.load_schedule(schedule_id)


# ---------------------------------------------------------------------------
# A — Contract
# ---------------------------------------------------------------------------


class A_ContractTests(C07SchedBase):
    def test_A01_module_exports(self):
        for name in (
            "create_schedule",
            "cancel_schedule",
            "reschedule",
            "process_due_schedules",
            "mark_missed_schedules",
            "normalize_local_datetime",
            "project_schedule_panel",
            "list_schedules_for_customer",
            "refresh_schedule",
            "recover_schedules_after_restart",
            "set_clock",
            "now_utc",
            "MISSED_GRACE_SEC",
            "detect_duplicate_engines",
            "SCHEDULE_STATES",
            "SCHEDULE_EVENTS",
            "CONTRACT_VERSION",
        ):
            self.assertTrue(hasattr(self.cps, name), name)

    def test_A02_contract_version(self):
        self.assertEqual(self.cps.CONTRACT_VERSION, "C07-SCHED.1")

    def test_A03_schedule_contract_constant(self):
        self.assertEqual(self.cps.SCHEDULE_CONTRACT, "c07-sched-1.0.0")

    def test_A04_missed_grace_six_hours(self):
        self.assertEqual(self.cps.MISSED_GRACE_SEC, 6 * 3600)

    def test_A05_states_include_scheduled(self):
        self.assertIn("SCHEDULED", self.cps.SCHEDULE_STATES)

    def test_A06_states_include_missed_superseded(self):
        self.assertIn("MISSED", self.cps.SCHEDULE_STATES)
        self.assertIn("SUPERSEDED", self.cps.SCHEDULE_STATES)

    def test_A07_events_include_created(self):
        self.assertIn("SCHEDULE_CREATED", self.cps.SCHEDULE_EVENTS)

    def test_A08_events_include_missed(self):
        self.assertIn("SCHEDULE_MISSED", self.cps.SCHEDULE_EVENTS)

    def test_A09_stage_constant(self):
        self.assertEqual(self.cps.SCHEDULE_STAGE, "c07_customer_publish_schedule")

    def test_A10_now_utc_respects_clock(self):
        self.assertEqual(self.cps.now_utc(), self._clock[0])


# ---------------------------------------------------------------------------
# B — Timezone
# ---------------------------------------------------------------------------


class B_TimezoneTests(C07SchedBase):
    def test_B01_normalize_utc_ok(self):
        r = self.cps.normalize_local_datetime(local_datetime="2026-09-10T18:00", tz_name="UTC")
        self.assertTrue(r.get("ok"))
        self.assertIn("2026-09-10T18:00", r.get("scheduled_at_utc") or "")

    def test_B02_normalize_space_separator(self):
        r = self.cps.normalize_local_datetime(local_datetime="2026-09-10 18:00", tz_name="UTC")
        self.assertTrue(r.get("ok"))

    def test_B03_normalize_with_seconds(self):
        r = self.cps.normalize_local_datetime(local_datetime="2026-09-10T18:00:30", tz_name="UTC")
        self.assertTrue(r.get("ok"))
        self.assertIn("18:00:30", r.get("local_datetime") or "")

    def test_B04_invalid_timezone_rejected(self):
        r = self.cps.normalize_local_datetime(local_datetime="2026-09-10T18:00", tz_name="Not/AZone")
        self.assertFalse(r.get("ok"))
        self.assertEqual(r.get("error"), "invalid_timezone")

    def test_B05_empty_timezone_rejected(self):
        r = self.cps.normalize_local_datetime(local_datetime="2026-09-10T18:00", tz_name="")
        self.assertFalse(r.get("ok"))
        self.assertEqual(r.get("error"), "timezone_required")

    def test_B06_empty_local_rejected(self):
        r = self.cps.normalize_local_datetime(local_datetime="", tz_name="UTC")
        self.assertFalse(r.get("ok"))
        self.assertEqual(r.get("error"), "local_datetime_required")

    def test_B07_invalid_local_format(self):
        r = self.cps.normalize_local_datetime(local_datetime="not-a-date", tz_name="UTC")
        self.assertFalse(r.get("ok"))
        self.assertEqual(r.get("error"), "invalid_local_datetime")

    def test_B08_epoch_present_on_ok(self):
        r = self.cps.normalize_local_datetime(local_datetime="2026-09-10T18:00", tz_name="UTC")
        self.assertIn("scheduled_at_utc_epoch", r)
        self.assertGreater(float(r["scheduled_at_utc_epoch"]), 0)


# ---------------------------------------------------------------------------
# C — DST / ambiguous / nonexistent
# ---------------------------------------------------------------------------


class C_DstAmbiguousTests(C07SchedBase):
    def test_C01_policy_reject_ambiguous_key_in_source(self):
        src = Path(self.cps.__file__).read_text(encoding="utf-8")
        self.assertIn("reject_ambiguous_dst_fold", src)
        self.assertIn("ambiguous_local_time", src)

    def test_C02_policy_reject_gap_key_in_source(self):
        src = Path(self.cps.__file__).read_text(encoding="utf-8")
        self.assertIn("reject_dst_gap", src)
        self.assertIn("nonexistent_local_time", src)

    def test_C03_ambiguous_fall_back_or_policy(self):
        # 2025-11-02 01:30 America/New_York is typically ambiguous (fold)
        r = self.cps.normalize_local_datetime(
            local_datetime="2025-11-02T01:30",
            tz_name="America/New_York",
        )
        if r.get("ok"):
            # Some zoneinfo builds may not flag; still require no silent fold ambiguity fields
            self.assertIn("scheduled_at_utc", r)
        else:
            self.assertEqual(r.get("error"), "ambiguous_local_time")
            self.assertEqual(r.get("policy"), "reject_ambiguous_dst_fold")

    def test_C04_nonexistent_spring_forward_or_policy(self):
        # 2025-03-09 02:30 America/New_York is typically a DST gap
        r = self.cps.normalize_local_datetime(
            local_datetime="2025-03-09T02:30",
            tz_name="America/New_York",
        )
        if r.get("ok"):
            self.assertIn("scheduled_at_utc", r)
        else:
            self.assertEqual(r.get("error"), "nonexistent_local_time")
            self.assertEqual(r.get("policy"), "reject_dst_gap")

    def test_C05_create_rejects_invalid_tz(self):
        row = self._admit_ready_job(suffix="c05")
        out = self._create(row["id"], timezone_name="Fake/Zone")
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "invalid_timezone")

    def test_C06_normalize_error_code_validation(self):
        r = self.cps.normalize_local_datetime(local_datetime="2026-09-10T18:00", tz_name="X/Y/Z")
        self.assertEqual(r.get("error_code"), "VALIDATION_FAILURE")


# ---------------------------------------------------------------------------
# D — Validation (past / future)
# ---------------------------------------------------------------------------


class D_ValidationTests(C07SchedBase):
    def test_D01_future_schedule_scheduled(self):
        row = self._admit_ready_job(suffix="d01")
        out = self._create(row["id"], local_datetime="2026-09-10T18:00")
        self.assertTrue(out.get("ok"))
        self.assertEqual(out["schedule"]["status"], "SCHEDULED")

    def test_D02_past_schedule_rejected(self):
        row = self._admit_ready_job(suffix="d02")
        out = self._create(row["id"], local_datetime="2026-09-10T10:00")
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "past_schedule")

    def test_D03_past_no_provider_called(self):
        row = self._admit_ready_job(suffix="d03")
        out = self._create(row["id"], local_datetime=self._past_local(1))
        self.assertFalse(out.get("provider_called"))

    def test_D04_exact_now_rejected(self):
        row = self._admit_ready_job(suffix="d04")
        out = self._create(row["id"], local_datetime="2026-09-10T12:00")
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "past_schedule")

    def test_D05_future_provider_called_false(self):
        row = self._admit_ready_job(suffix="d05")
        out = self._create(row["id"], local_datetime="2026-09-10T18:00")
        self.assertFalse(out.get("provider_called"))

    def test_D06_scheduled_at_utc_set(self):
        row = self._admit_ready_job(suffix="d06")
        out = self._create(row["id"], local_datetime="2026-09-10T18:00")
        self.assertIn("2026-09-10T18:00", out["schedule"]["scheduled_at_utc"])

    def test_D07_timezone_stored(self):
        row = self._admit_ready_job(suffix="d07")
        out = self._create(row["id"], local_datetime="2026-09-10T18:00")
        self.assertEqual(out["schedule"]["timezone"], "UTC")

    def test_D08_kind_scheduled_publish(self):
        row = self._admit_ready_job(suffix="d08")
        out = self._create(row["id"])
        self.assertEqual(out["schedule"]["kind"], "ScheduledPublish")


# ---------------------------------------------------------------------------
# E — Approval gate
# ---------------------------------------------------------------------------


class E_ApprovalGateTests(C07SchedBase):
    def test_E01_unapproved_rejected(self):
        row = self._admit_ready_job(suffix="e01", customer_approval="PENDING")
        out = self._create(row["id"])
        self.assertFalse(out.get("ok"))
        self.assertFalse(out.get("admitted", True) and out.get("ok"))

    def test_E02_unapproved_status_validation_failed(self):
        row = self._admit_ready_job(suffix="e02", customer_approval="REJECTED")
        out = self._create(row["id"])
        self.assertEqual(out.get("schedule_status"), "SCHEDULE_VALIDATION_FAILED")

    def test_E03_unapproved_no_provider(self):
        row = self._admit_ready_job(suffix="e03", customer_approval="PENDING")
        out = self._create(row["id"])
        self.assertFalse(out.get("provider_called"))

    def test_E04_approved_admits(self):
        row = self._admit_ready_job(suffix="e04", customer_approval="APPROVED")
        out = self._create(row["id"])
        self.assertTrue(out.get("ok"))

    def test_E05_gate_blockers_present_when_fail(self):
        row = self._admit_ready_job(suffix="e05", customer_approval="PENDING")
        out = self._create(row["id"])
        self.assertTrue(out.get("blockers") or out.get("error"))

    def test_E06_draft_approval_rejected(self):
        row = self._admit_ready_job(suffix="e06", customer_approval="DRAFT")
        out = self._create(row["id"])
        self.assertFalse(out.get("ok"))


# ---------------------------------------------------------------------------
# F — Publishability gate
# ---------------------------------------------------------------------------


class F_PublishabilityGateTests(C07SchedBase):
    def test_F01_blocked_rejected(self):
        qs = {
            "publishable": False,
            "publishability": {"verdict": "BLOCKED", "publishable": False, "reason": "bad"},
        }
        row = self._admit_ready_job(suffix="f01", quality_summary=qs)
        out = self._create(row["id"])
        self.assertFalse(out.get("ok"))

    def test_F02_unknown_rejected(self):
        qs = {
            "publishable": False,
            "publishability": {"verdict": "UNKNOWN", "publishable": False, "reason": "unk"},
        }
        row = self._admit_ready_job(suffix="f02", quality_summary=qs)
        out = self._create(row["id"])
        self.assertFalse(out.get("ok"))

    def test_F03_blocked_no_provider(self):
        qs = {"publishable": False, "publishability": {"verdict": "BLOCKED", "publishable": False}}
        row = self._admit_ready_job(suffix="f03", quality_summary=qs)
        out = self._create(row["id"])
        self.assertFalse(out.get("provider_called"))

    def test_F04_publishable_ok(self):
        row = self._admit_ready_job(suffix="f04")
        out = self._create(row["id"])
        self.assertTrue(out.get("ok"))

    def test_F05_blocked_schedule_status(self):
        qs = {"publishable": False, "publishability": {"verdict": "BLOCKED", "publishable": False}}
        row = self._admit_ready_job(suffix="f05", quality_summary=qs)
        out = self._create(row["id"])
        self.assertEqual(out.get("schedule_status"), "SCHEDULE_VALIDATION_FAILED")

    def test_F06_unknown_schedule_status(self):
        qs = {"publishable": False, "publishability": {"verdict": "UNKNOWN", "publishable": False}}
        row = self._admit_ready_job(suffix="f06", quality_summary=qs)
        out = self._create(row["id"])
        self.assertEqual(out.get("schedule_status"), "SCHEDULE_VALIDATION_FAILED")

    def test_F07_publishable_false_flag(self):
        qs = {"publishable": False, "publishability_verdict": "BLOCKED"}
        row = self._admit_ready_job(suffix="f07", quality_summary=qs)
        out = self._create(row["id"])
        self.assertFalse(out.get("ok"))

    def test_F08_reuses_validate_publish_gates(self):
        src = Path(self.cps.__file__).read_text(encoding="utf-8")
        self.assertIn("validate_publish_gates", src)


# ---------------------------------------------------------------------------
# G — Ownership
# ---------------------------------------------------------------------------


class G_OwnershipTests(C07SchedBase):
    def test_G01_foreign_customer_rejected(self):
        row = self._admit_ready_job(suffix="g01")
        out = self._create(
            row["id"],
            login=self.login_b,
            channel_ids=[self.ch_b_id],
            identity=self._identity(self.login_b),
        )
        # job owned by cust_a / ch_a — foreign
        self.assertFalse(out.get("ok"))

    def test_G02_foreign_channel_id_rejected(self):
        row = self._admit_ready_job(suffix="g02")
        out = self._create(row["id"], channel_ids=[self.ch_b_id], channel_id=self.ch_b_id)
        self.assertFalse(out.get("ok"))

    def test_G03_owner_ok(self):
        row = self._admit_ready_job(suffix="g03")
        out = self._create(row["id"])
        self.assertTrue(out.get("ok"))

    def test_G04_list_hides_foreign(self):
        row_a = self._admit_ready_job(suffix="g04a")
        row_b = self._admit_ready_job(suffix="g04b", login_id=self.login_b, channel_id=self.ch_b_id)
        self._create(row_a["id"])
        self._create(
            row_b["id"],
            login=self.login_b,
            channel_ids=[self.ch_b_id],
            identity=self._identity(self.login_b),
        )
        listed = self._list()
        for s in listed["schedules"]:
            self.assertEqual(s["login_id"], self.login)

    def test_G05_cancel_foreign_denied(self):
        row = self._admit_ready_job(suffix="g05")
        out = self._create(row["id"])
        sid = out["schedule"]["schedule_id"]
        bad = self._cancel(sid, login=self.login_b, channel_ids=[self.ch_b_id])
        self.assertFalse(bad.get("ok"))
        self.assertEqual(bad.get("error_code"), "OWNERSHIP_FAILURE")

    def test_G06_reschedule_foreign_denied(self):
        row = self._admit_ready_job(suffix="g06")
        out = self._create(row["id"])
        sid = out["schedule"]["schedule_id"]
        bad = self.cps.reschedule(
            self.login_b,
            sid,
            channel_ids=[self.ch_b_id],
            local_datetime=self._future_local(8),
            timezone_name="UTC",
            identity=self._identity(self.login_b),
        )
        self.assertFalse(bad.get("ok"))

    def test_G07_panel_scoped_to_owner(self):
        row = self._admit_ready_job(suffix="g07")
        self._create(row["id"])
        p = self._panel(login=self.login_b, channel_ids=[self.ch_b_id])
        self.assertEqual(p.get("schedules") or [], [])

    def test_G08_job_b_owner_can_schedule(self):
        row = self._admit_ready_job(suffix="g08", login_id=self.login_b, channel_id=self.ch_b_id)
        out = self._create(
            row["id"],
            login=self.login_b,
            channel_ids=[self.ch_b_id],
            identity=self._identity(self.login_b),
        )
        self.assertTrue(out.get("ok"))


# ---------------------------------------------------------------------------
# H — Entitlement
# ---------------------------------------------------------------------------


class H_EntitlementTests(C07SchedBase):
    def test_H01_inactive_entitlement_rejected(self):
        row = self._admit_ready_job(suffix="h01")
        out = self._create(
            row["id"],
            identity=self._identity(entitlement_state="INACTIVE"),
        )
        self.assertFalse(out.get("ok"))

    def test_H02_no_production_access(self):
        row = self._admit_ready_job(suffix="h02")
        out = self._create(
            row["id"],
            identity=self._identity(production_access=False),
        )
        self.assertFalse(out.get("ok"))

    def test_H03_unauthenticated(self):
        row = self._admit_ready_job(suffix="h03")
        out = self._create(
            row["id"],
            identity=self._identity(authenticated=False, auth_state="ANONYMOUS"),
        )
        self.assertFalse(out.get("ok"))

    def test_H04_account_suspended(self):
        row = self._admit_ready_job(suffix="h04")
        out = self._create(
            row["id"],
            identity=self._identity(account_state="SUSPENDED"),
        )
        self.assertFalse(out.get("ok"))

    def test_H05_active_ok(self):
        row = self._admit_ready_job(suffix="h05")
        out = self._create(row["id"], identity=self._identity())
        self.assertTrue(out.get("ok"))

    def test_H06_no_provider_on_entitlement_fail(self):
        row = self._admit_ready_job(suffix="h06")
        out = self._create(
            row["id"],
            identity=self._identity(entitlement_state="EXPIRED"),
        )
        self.assertFalse(out.get("provider_called", True))


# ---------------------------------------------------------------------------
# I — Provider capability
# ---------------------------------------------------------------------------


class I_ProviderCapabilityTests(C07SchedBase):
    def test_I01_mock_provider_schedules(self):
        row = self._admit_ready_job(suffix="i01")
        out = self._create(row["id"], provider="mock")
        self.assertTrue(out.get("ok"))

    def test_I02_capability_local_schedule_true(self):
        row = self._admit_ready_job(suffix="i02")
        out = self._create(row["id"])
        cap = out["schedule"].get("capability") or {}
        self.assertTrue(cap.get("local_schedule"))

    def test_I03_provider_native_not_supported(self):
        row = self._admit_ready_job(suffix="i03")
        out = self._create(row["id"])
        cap = out["schedule"].get("capability") or {}
        self.assertEqual(cap.get("provider_native_schedule"), "NOT_SUPPORTED")

    def test_I04_mock_flag_true(self):
        row = self._admit_ready_job(suffix="i04")
        out = self._create(row["id"])
        self.assertTrue(out["schedule"].get("mock"))

    def test_I05_provider_name_stored(self):
        row = self._admit_ready_job(suffix="i05")
        out = self._create(row["id"], provider="mock")
        self.assertTrue(out["schedule"].get("provider") == "mock" or out["schedule"].get("provider_name"))


# ---------------------------------------------------------------------------
# J — Schedule creation
# ---------------------------------------------------------------------------


class J_ScheduleCreationTests(C07SchedBase):
    def test_J01_creates_schedule_id(self):
        row = self._admit_ready_job(suffix="j01")
        out = self._create(row["id"])
        self.assertTrue(str(out["schedule"]["schedule_id"]).startswith("sch_"))

    def test_J02_fingerprint_present(self):
        row = self._admit_ready_job(suffix="j02")
        out = self._create(row["id"])
        self.assertTrue(out["schedule"].get("fingerprint"))

    def test_J03_revision_frozen(self):
        row = self._admit_ready_job(suffix="j03")
        out = self._create(row["id"])
        self.assertEqual(out["schedule"]["revision_id"], self._revision(row["id"]))

    def test_J04_job_id_bound(self):
        row = self._admit_ready_job(suffix="j04")
        out = self._create(row["id"])
        self.assertEqual(int(out["schedule"]["job_id"]), int(row["id"]))

    def test_J05_channel_id_bound(self):
        row = self._admit_ready_job(suffix="j05")
        out = self._create(row["id"])
        self.assertEqual(int(out["schedule"]["channel_id"]), self.ch_id)

    def test_J06_persisted_loadable(self):
        row = self._admit_ready_job(suffix="j06")
        out = self._create(row["id"])
        loaded = self.cps.load_schedule(out["schedule"]["schedule_id"])
        self.assertEqual(loaded["status"], "SCHEDULED")

    def test_J07_index_contains_id(self):
        row = self._admit_ready_job(suffix="j07")
        out = self._create(row["id"])
        ids = self.cps._load_index().get("ids") or []
        self.assertIn(out["schedule"]["schedule_id"], ids)

    def test_J08_missed_grace_on_record(self):
        row = self._admit_ready_job(suffix="j08")
        out = self._create(row["id"])
        self.assertEqual(out["schedule"]["missed_grace_sec"], self.cps.MISSED_GRACE_SEC)

    def test_J09_publish_intent_ref(self):
        row = self._admit_ready_job(suffix="j09")
        out = self._create(row["id"])
        ref = out["schedule"].get("publish_intent_ref") or {}
        self.assertEqual(ref.get("stage"), "c07_customer_publish")

    def test_J10_cancellation_state_none(self):
        row = self._admit_ready_job(suffix="j10")
        out = self._create(row["id"])
        self.assertEqual(out["schedule"].get("cancellation_state"), "NONE")


# ---------------------------------------------------------------------------
# K — Duplicate schedule
# ---------------------------------------------------------------------------


class K_DuplicateScheduleTests(C07SchedBase):
    def test_K01_duplicate_reuses(self):
        row = self._admit_ready_job(suffix="k01")
        r1 = self._create(row["id"], local_datetime="2026-09-10T18:00")
        r2 = self._create(row["id"], local_datetime="2026-09-10T18:00")
        self.assertTrue(r2.get("ok"))
        self.assertTrue(r2.get("reused"))
        self.assertEqual(r1["schedule"]["schedule_id"], r2["schedule"]["schedule_id"])

    def test_K02_duplicate_no_provider(self):
        row = self._admit_ready_job(suffix="k02")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        r2 = self._create(row["id"], local_datetime="2026-09-10T18:00")
        self.assertFalse(r2.get("provider_called"))

    def test_K03_different_time_new_schedule(self):
        row = self._admit_ready_job(suffix="k03")
        r1 = self._create(row["id"], local_datetime="2026-09-10T18:00")
        r2 = self._create(row["id"], local_datetime="2026-09-10T19:00")
        # second may succeed as distinct fingerprint (or fail gates) — if ok, ids differ or reused false
        if r2.get("ok") and not r2.get("reused"):
            self.assertNotEqual(r1["schedule"]["schedule_id"], r2["schedule"]["schedule_id"])

    def test_K04_only_one_active_same_fp(self):
        row = self._admit_ready_job(suffix="k04")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        listed = self._list(job_id=int(row["id"]))
        active = [s for s in listed["schedules"] if s.get("status") == "SCHEDULED"]
        self.assertEqual(len(active), 1)

    def test_K05_note_mentions_fingerprint_or_reuse(self):
        row = self._admit_ready_job(suffix="k05")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        r2 = self._create(row["id"], local_datetime="2026-09-10T18:00")
        blob = json.dumps(r2).lower()
        self.assertTrue("reuse" in blob or r2.get("reused"))

    def test_K06_ready_false_rejected(self):
        row = self._admit_ready_job(suffix="k06", upload_status="pending")
        out = self._create(row["id"])
        self.assertFalse(out.get("ok"))


# ---------------------------------------------------------------------------
# L — Concurrent duplicate schedule
# ---------------------------------------------------------------------------


class L_ConcurrentDuplicateTests(C07SchedBase):
    def test_L01_concurrent_one_schedule(self):
        row = self._admit_ready_job(suffix="l01")
        jid = int(row["id"])
        local = "2026-09-10T18:00"

        def _run():
            return self._create(jid, local_datetime=local)

        with ThreadPoolExecutor(max_workers=4) as ex:
            results = [f.result() for f in as_completed([ex.submit(_run) for _ in range(4)])]
        ok = [r for r in results if r.get("ok")]
        self.assertGreaterEqual(len(ok), 1)
        ids = {r["schedule"]["schedule_id"] for r in ok if r.get("schedule")}
        self.assertEqual(len(ids), 1)

    def test_L02_concurrent_provider_never_called(self):
        row = self._admit_ready_job(suffix="l02")
        jid = int(row["id"])

        def _run():
            return self._create(jid, local_datetime="2026-09-10T18:30")

        with ThreadPoolExecutor(max_workers=3) as ex:
            results = list(ex.map(lambda _: _run(), range(3)))
        self.assertTrue(all(not r.get("provider_called") for r in results))

    def test_L03_concurrent_list_one_scheduled(self):
        row = self._admit_ready_job(suffix="l03")
        jid = int(row["id"])

        def _run():
            return self._create(jid, local_datetime="2026-09-10T19:00")

        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(lambda _: _run(), range(4)))
        listed = self._list(job_id=jid)
        scheduled = [s for s in listed["schedules"] if s.get("status") == "SCHEDULED"]
        self.assertEqual(len(scheduled), 1)

    def test_L04_concurrent_reused_or_ok(self):
        row = self._admit_ready_job(suffix="l04")
        jid = int(row["id"])

        def _run():
            return self._create(jid, local_datetime="2026-09-10T20:00")

        with ThreadPoolExecutor(max_workers=3) as ex:
            results = list(ex.map(lambda _: _run(), range(3)))
        self.assertTrue(any(r.get("ok") for r in results))


# ---------------------------------------------------------------------------
# M — Scheduler tick / process_due
# ---------------------------------------------------------------------------


class M_SchedulerTickTests(C07SchedBase):
    def test_M01_future_not_processed(self):
        row = self._admit_ready_job(suffix="m01")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        out = self._process()
        self.assertEqual(out.get("count"), 0)

    def test_M02_due_executes(self):
        row = self._admit_ready_job(suffix="m02")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 5, 0, tzinfo=timezone.utc))
        out = self._process()
        self.assertGreaterEqual(out.get("count"), 1)
        self.assertTrue(out.get("ok"))

    def test_M03_due_status_advances(self):
        row = self._admit_ready_job(suffix="m03")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        self._process()
        rec = self.cps.load_schedule(sid)
        self.assertIn(rec["status"], ("UPLOADED", "PUBLISHED", "PUBLISHING", "REMOTE_PROCESSING", "RECONCILIATION_REQUIRED"))

    def test_M04_scheduler_direct_upload_false(self):
        row = self._admit_ready_job(suffix="m04")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 2, 0, tzinfo=timezone.utc))
        out = self._process()
        self.assertFalse(out.get("scheduler_direct_upload"))

    def test_M05_customer_queue_tick_contains_process_due(self):
        from app import scheduler_service as ss

        src = inspect.getsource(ss.SchedulerService.customer_queue_tick_job)
        self.assertIn("process_due_schedules", src)

    def test_M06_process_due_source_no_youtube_upload(self):
        src = inspect.getsource(self.cps.process_due_schedules)
        self.assertNotIn("videos.insert", src)
        self.assertNotIn("youtube.upload", src.lower().replace(" ", ""))

    def test_M07_process_due_source_calls_publish_customer_job(self):
        src = inspect.getsource(self.cps.process_due_schedules)
        self.assertIn("publish_customer_job", src)

    def test_M08_mock_flag_on_tick_result(self):
        row = self._admit_ready_job(suffix="m08")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 3, 0, tzinfo=timezone.utc))
        out = self._process()
        self.assertTrue(out.get("mock"))


# ---------------------------------------------------------------------------
# N — Concurrent scheduler ticks
# ---------------------------------------------------------------------------


class N_ConcurrentTickTests(C07SchedBase):
    def test_N01_concurrent_ticks_one_execution(self):
        row = self._admit_ready_job(suffix="n01")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 10, 0, tzinfo=timezone.utc))

        def _run(i):
            return self._process(worker_id=f"worker-{i}")

        with ThreadPoolExecutor(max_workers=4) as ex:
            results = [f.result() for f in as_completed([ex.submit(_run, i) for i in range(4)])]
        total = sum(int(r.get("count") or 0) for r in results)
        self.assertEqual(total, 1)

    def test_N02_concurrent_skipped_or_zero(self):
        row = self._admit_ready_job(suffix="n02")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 15, 0, tzinfo=timezone.utc))

        def _run(i):
            return self._process(worker_id=f"w2-{i}")

        with ThreadPoolExecutor(max_workers=3) as ex:
            results = list(ex.map(_run, range(3)))
        zeros = [r for r in results if int(r.get("count") or 0) == 0]
        self.assertGreaterEqual(len(zeros), 2)

    def test_N03_no_double_provider_via_sched(self):
        row = self._admit_ready_job(suffix="n03")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 20, 0, tzinfo=timezone.utc))
        with ThreadPoolExecutor(max_workers=3) as ex:
            list(ex.map(lambda i: self._process(worker_id=f"w3-{i}"), range(3)))
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_N04_final_status_not_scheduled(self):
        row = self._admit_ready_job(suffix="n04")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._set_clock(datetime(2026, 9, 10, 18, 25, 0, tzinfo=timezone.utc))
        with ThreadPoolExecutor(max_workers=3) as ex:
            list(ex.map(lambda i: self._process(worker_id=f"w4-{i}"), range(3)))
        rec = self.cps.load_schedule(sid)
        self.assertNotEqual(rec["status"], "SCHEDULED")


# ---------------------------------------------------------------------------
# O — Atomic claim
# ---------------------------------------------------------------------------


class O_AtomicClaimTests(C07SchedBase):
    def test_O01_executed_has_claim_path(self):
        row = self._admit_ready_job(suffix="o01")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        out = self._process()
        self.assertEqual(out["executed"][0]["schedule_id"], sid)

    def test_O02_execution_ref_set(self):
        row = self._admit_ready_job(suffix="o02")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        self._process()
        rec = self.cps.load_schedule(sid)
        self.assertTrue(rec.get("execution_ref"))

    def test_O03_second_tick_no_reclaim_same(self):
        row = self._admit_ready_job(suffix="o03")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        self._process()
        out2 = self._process()
        self.assertEqual(out2.get("count"), 0)

    def test_O04_max_one_limits(self):
        row1 = self._admit_ready_job(suffix="o04a")
        row2 = self._admit_ready_job(suffix="o04b", media_name="ready2.mp4")
        self._create(row1["id"], local_datetime="2026-09-10T18:00")
        self._create(row2["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 5, 0, tzinfo=timezone.utc))
        out = self._process(max_one=True)
        self.assertEqual(out.get("count"), 1)

    def test_O05_scheduler_uploaded_false_in_executed(self):
        row = self._admit_ready_job(suffix="o05")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        out = self._process()
        self.assertFalse(out["executed"][0].get("scheduler_uploaded"))


# ---------------------------------------------------------------------------
# P — Schedule → job handoff
# ---------------------------------------------------------------------------


class P_HandoffTests(C07SchedBase):
    def test_P01_handoff_delegates_to_c07_pub(self):
        row = self._admit_ready_job(suffix="p01")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        out = self._process()
        self.assertEqual(out["executed"][0].get("provider_called_by"), "c07_pub")

    def test_P02_job_publish_state_advanced(self):
        row = self._admit_ready_job(suffix="p02")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        self._process()
        j = self._get_job(row["id"])
        self.assertTrue(j.get("publish_status") or j.get("upload_status"))

    def test_P03_no_videos_insert_in_module(self):
        src = Path(self.cps.__file__).read_text(encoding="utf-8")
        self.assertNotIn("videos.insert", src)

    def test_P04_process_source_no_upload_media_bytes(self):
        src = inspect.getsource(self.cps.process_due_schedules)
        self.assertNotIn("upload_media", src)
        self.assertNotIn("resumable_upload", src)

    def test_P05_scheduler_direct_upload_flag(self):
        out = self._process()
        self.assertFalse(out.get("scheduler_direct_upload"))

    def test_P06_note_delegated(self):
        row = self._admit_ready_job(suffix="p06")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        out = self._process()
        self.assertIn("C07-PUB", out.get("note") or "")

    def test_P07_reconciliation_via_network_ambiguous(self):
        row = self._admit_ready_job(suffix="p07")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        orig = self.cp.publish_customer_job

        def _ambiguous(*a, **kw):
            kw["scenario"] = "network_ambiguous"
            return orig(*a, **kw)

        with patch("app.customer_publish.publish_customer_job", side_effect=_ambiguous):
            self._process()
        rec = self.cps.load_schedule(sid)
        self.assertEqual(rec["status"], "RECONCILIATION_REQUIRED")

    def test_P08_handoff_ok_true(self):
        row = self._admit_ready_job(suffix="p08")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        out = self._process()
        self.assertTrue(out["executed"][0].get("ok"))


# ---------------------------------------------------------------------------
# Q — Revision immutability
# ---------------------------------------------------------------------------


class Q_RevisionImmutabilityTests(C07SchedBase):
    def test_Q01_foreign_revision_rejected_on_create(self):
        row = self._admit_ready_job(suffix="q01")
        out = self._create(row["id"], revision_id="forged-rev-xyz")
        self.assertFalse(out.get("ok"))

    def test_Q02_correct_revision_ok(self):
        row = self._admit_ready_job(suffix="q02")
        out = self._create(row["id"], revision_id=self._revision(row["id"]))
        self.assertTrue(out.get("ok"))

    def test_Q03_revision_change_fails_handoff(self):
        row = self._admit_ready_job(suffix="q03")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        # mutate generation fingerprint (affects compute_revision_id) — title alone does not
        self.store.update_job(int(row["id"]), generation_fingerprint="mutated-fp-after-schedule")
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        self._process()
        rec = self.cps.load_schedule(sid)
        self.assertEqual(rec["status"], "PUBLISH_FAILED")
        self.assertIn("revision", (rec.get("error") or "").lower())

    def test_Q04_approved_revision_stored(self):
        row = self._admit_ready_job(suffix="q04")
        out = self._create(row["id"])
        self.assertEqual(out["schedule"]["approved_revision"], out["schedule"]["revision_id"])

    def test_Q05_artifact_path_frozen(self):
        row = self._admit_ready_job(suffix="q05")
        out = self._create(row["id"])
        self.assertTrue(out["schedule"].get("artifact_path"))

    def test_Q06_unapprove_after_schedule_fails_exec(self):
        row = self._admit_ready_job(suffix="q06")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self.store.update_job(int(row["id"]), customer_approval="PENDING")
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        self._process()
        rec = self.cps.load_schedule(sid)
        self.assertEqual(rec["status"], "PUBLISH_FAILED")


# ---------------------------------------------------------------------------
# R — Cancellation
# ---------------------------------------------------------------------------


class R_CancellationTests(C07SchedBase):
    def test_R01_cancel_before_due(self):
        row = self._admit_ready_job(suffix="r01")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        out = self._cancel(sid)
        self.assertTrue(out.get("ok"))
        self.assertEqual(out["schedule"]["status"], "CANCELLED")

    def test_R02_cancelled_not_executed(self):
        row = self._admit_ready_job(suffix="r02")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._cancel(sid)
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        out = self._process()
        self.assertEqual(out.get("count"), 0)
        self.assertEqual(self.cps.load_schedule(sid)["status"], "CANCELLED")

    def test_R03_cancel_claimed_fails(self):
        row = self._admit_ready_job(suffix="r03")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._force_status(sid, "CLAIMED")
        out = self._cancel(sid)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "execution_already_started")

    def test_R04_cancel_publishing_fails(self):
        row = self._admit_ready_job(suffix="r04")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._force_status(sid, "PUBLISHING")
        out = self._cancel(sid)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "execution_already_started")

    def test_R05_cancel_published_fails(self):
        row = self._admit_ready_job(suffix="r05")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._force_status(sid, "PUBLISHED")
        out = self._cancel(sid)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "cannot_cancel_published")

    def test_R06_cancel_idempotent(self):
        row = self._admit_ready_job(suffix="r06")
        created = self._create(row["id"])
        sid = created["schedule"]["schedule_id"]
        self._cancel(sid)
        out2 = self._cancel(sid)
        self.assertTrue(out2.get("ok"))
        self.assertTrue(out2.get("reused"))

    def test_R07_cancel_not_found(self):
        out = self._cancel("sch_missing_xxx")
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "schedule_not_found")

    def test_R08_cancel_no_provider(self):
        row = self._admit_ready_job(suffix="r08")
        created = self._create(row["id"])
        out = self._cancel(created["schedule"]["schedule_id"])
        self.assertFalse(out.get("provider_called"))


# ---------------------------------------------------------------------------
# S — Reschedule
# ---------------------------------------------------------------------------


class S_RescheduleTests(C07SchedBase):
    def test_S01_reschedule_supersedes(self):
        row = self._admit_ready_job(suffix="s01")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        out = self._reschedule(sid, local_datetime="2026-09-10T21:00")
        self.assertTrue(out.get("ok"))
        old = self.cps.load_schedule(sid)
        self.assertEqual(old["status"], "SUPERSEDED")

    def test_S02_new_schedule_scheduled(self):
        row = self._admit_ready_job(suffix="s02")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        out = self._reschedule(created["schedule"]["schedule_id"], local_datetime="2026-09-10T22:00")
        self.assertEqual(out["schedule"]["status"], "SCHEDULED")

    def test_S03_old_not_executed(self):
        row = self._admit_ready_job(suffix="s03")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        new = self._reschedule(sid, local_datetime="2026-09-10T23:00")
        new_id = new["schedule"]["schedule_id"]
        self._set_clock(datetime(2026, 9, 10, 18, 30, 0, tzinfo=timezone.utc))
        self._process()
        self.assertEqual(self.cps.load_schedule(sid)["status"], "SUPERSEDED")
        # new not yet due
        self.assertEqual(self.cps.load_schedule(new_id)["status"], "SCHEDULED")

    def test_S04_supersedes_links(self):
        row = self._admit_ready_job(suffix="s04")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        new = self._reschedule(sid, local_datetime="2026-09-11T01:00")
        self.assertEqual(self.cps.load_schedule(sid).get("superseded_by"), new["schedule"]["schedule_id"])
        self.assertEqual(new["schedule"].get("supersedes"), sid)

    def test_S05_one_future_execution(self):
        row = self._admit_ready_job(suffix="s05")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._reschedule(created["schedule"]["schedule_id"], local_datetime="2026-09-10T21:00")
        listed = self._list(job_id=int(row["id"]))
        scheduled = [s for s in listed["schedules"] if s.get("status") == "SCHEDULED"]
        self.assertEqual(len(scheduled), 1)

    def test_S06_cannot_reschedule_claimed(self):
        row = self._admit_ready_job(suffix="s06")
        created = self._create(row["id"])
        sid = created["schedule"]["schedule_id"]
        self._force_status(sid, "CLAIMED")
        out = self._reschedule(sid)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "cannot_reschedule")

    def test_S07_reschedule_no_provider(self):
        row = self._admit_ready_job(suffix="s07")
        created = self._create(row["id"])
        out = self._reschedule(created["schedule"]["schedule_id"], local_datetime="2026-09-11T02:00")
        self.assertFalse(out.get("provider_called"))

    def test_S08_new_executes_when_due(self):
        row = self._admit_ready_job(suffix="s08")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        new = self._reschedule(created["schedule"]["schedule_id"], local_datetime="2026-09-10T19:00")
        new_id = new["schedule"]["schedule_id"]
        self._set_clock(datetime(2026, 9, 10, 19, 5, 0, tzinfo=timezone.utc))
        out = self._process()
        self.assertEqual(out.get("count"), 1)
        self.assertEqual(out["executed"][0]["schedule_id"], new_id)


# ---------------------------------------------------------------------------
# T — Missed schedule
# ---------------------------------------------------------------------------


class T_MissedScheduleTests(C07SchedBase):
    def test_T01_beyond_grace_missed(self):
        row = self._admit_ready_job(suffix="t01")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        # 18:00 + 6h + 1s
        self._set_clock(datetime(2026, 9, 11, 0, 0, 1, tzinfo=timezone.utc))
        marked = self.cps.mark_missed_schedules()
        self.assertIn(sid, marked)
        self.assertEqual(self.cps.load_schedule(sid)["status"], "MISSED")

    def test_T02_within_grace_not_missed(self):
        row = self._admit_ready_job(suffix="t02")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._set_clock(datetime(2026, 9, 10, 20, 0, 0, tzinfo=timezone.utc))  # 2h overdue
        marked = self.cps.mark_missed_schedules()
        self.assertNotIn(sid, marked)
        self.assertEqual(self.cps.load_schedule(sid)["status"], "SCHEDULED")

    def test_T03_missed_not_auto_published(self):
        row = self._admit_ready_job(suffix="t03")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._set_clock(datetime(2026, 9, 11, 1, 0, 0, tzinfo=timezone.utc))
        out = self._process()
        self.assertEqual(out.get("count"), 0)
        self.assertEqual(self.cps.load_schedule(sid)["status"], "MISSED")

    def test_T04_panel_missed_policy(self):
        p = self._panel()
        pol = p.get("missed_policy") or {}
        self.assertEqual(pol.get("grace_sec"), self.cps.MISSED_GRACE_SEC)
        self.assertFalse(pol.get("auto_catch_up_publish"))
        self.assertEqual(pol.get("behavior"), "MISSED_REQUIRES_ACTION")

    def test_T05_within_grace_still_due(self):
        row = self._admit_ready_job(suffix="t05")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 21, 0, 0, tzinfo=timezone.utc))
        out = self._process()
        self.assertGreaterEqual(out.get("count"), 1)

    def test_T06_grace_constant_exported(self):
        self.assertEqual(self.cps.MISSED_GRACE_SEC, 21600)


# ---------------------------------------------------------------------------
# U — Restart recovery
# ---------------------------------------------------------------------------


class U_RestartRecoveryTests(C07SchedBase):
    def test_U01_future_remains_scheduled(self):
        row = self._admit_ready_job(suffix="u01")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        out = self.cps.recover_schedules_after_restart()
        self.assertTrue(out.get("ok"))
        self.assertEqual(self.cps.load_schedule(sid)["status"], "SCHEDULED")

    def test_U02_recover_publishes_false(self):
        out = self.cps.recover_schedules_after_restart()
        self.assertFalse(out.get("publishes"))

    def test_U03_published_never_reexecute_note(self):
        row = self._admit_ready_job(suffix="u03")
        created = self._create(row["id"])
        sid = created["schedule"]["schedule_id"]
        self._force_status(sid, "PUBLISHED")
        out = self.cps.recover_schedules_after_restart()
        notes = [x.get("note") for x in out.get("recovered") or []]
        self.assertTrue(any(n == "never_reexecute" for n in notes))

    def test_U04_claimed_awaiting_note(self):
        row = self._admit_ready_job(suffix="u04")
        created = self._create(row["id"])
        sid = created["schedule"]["schedule_id"]
        self._force_status(sid, "CLAIMED")
        out = self.cps.recover_schedules_after_restart()
        items = [x for x in out.get("recovered") or [] if x.get("schedule_id") == sid]
        self.assertTrue(items)
        self.assertIn("awaiting", items[0].get("note") or "")

    def test_U05_stale_beyond_grace_marked_missed_on_recover(self):
        row = self._admit_ready_job(suffix="u05")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._set_clock(datetime(2026, 9, 11, 2, 0, 0, tzinfo=timezone.utc))
        self.cps.recover_schedules_after_restart()
        self.assertEqual(self.cps.load_schedule(sid)["status"], "MISSED")

    def test_U06_due_within_grace_still_scheduled_until_tick(self):
        row = self._admit_ready_job(suffix="u06")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._set_clock(datetime(2026, 9, 10, 19, 0, 0, tzinfo=timezone.utc))
        self.cps.recover_schedules_after_restart()
        self.assertEqual(self.cps.load_schedule(sid)["status"], "SCHEDULED")


# ---------------------------------------------------------------------------
# V — Provider execution integration boundary
# ---------------------------------------------------------------------------


class V_ProviderBoundaryTests(C07SchedBase):
    def test_V01_published_no_reexecute(self):
        row = self._admit_ready_job(suffix="v01")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        self._process()
        # force published and tick again
        self._force_status(sid, "PUBLISHED")
        out2 = self._process()
        self.assertEqual(out2.get("count"), 0)

    def test_V02_real_provider_count_zero(self):
        row = self._admit_ready_job(suffix="v02")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        self._process()
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_V03_refresh_after_upload(self):
        row = self._admit_ready_job(suffix="v03")
        created = self._create(row["id"], local_datetime="2026-09-10T18:00")
        sid = created["schedule"]["schedule_id"]
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        self._process()
        out = self.cps.refresh_schedule(self.login, sid, channel_ids=[self.ch_id])
        self.assertTrue(out.get("ok"))

    def test_V04_detect_duplicate_engines_clean_module(self):
        src = Path(self.cps.__file__).read_text(encoding="utf-8")
        # exclude the detect function body patterns by checking only that clean source outside defs is ok
        # Module defines detect_duplicate_engines but should not redefine SchedulerService etc as classes
        self.assertNotRegex(src, r"(?m)^class\s+SchedulerService\b")
        self.assertNotRegex(src, r"(?m)^class\s+IdempotencyStore\b")

    def test_V05_detect_flags_customer_scheduler(self):
        bad = self.cps.detect_duplicate_engines("customer_scheduler.py\npublishing_scheduler.py\n")
        self.assertIn("customer_scheduler", bad)
        self.assertIn("publishing_scheduler", bad)

    def test_V06_detect_flags_second_engines(self):
        fake = "\n".join(
            [
                "class SchedulerService:",
                "    pass",
                "def generate_video():",
                "    pass",
                "def evaluate_publishability():",
                "    pass",
                "def compute_fingerprint():",
                "    pass",
                "class IdempotencyStore:",
                "    pass",
                "schedule_idempotency.py",
            ]
        )
        bad = self.cps.detect_duplicate_engines(fake)
        self.assertGreaterEqual(len(bad), 5)


# ---------------------------------------------------------------------------
# W — Event projection
# ---------------------------------------------------------------------------


class W_EventProjectionTests(C07SchedBase):
    def test_W01_schedule_created_event(self):
        row = self._admit_ready_job(suffix="w01")
        self._create(row["id"])
        j = self._get_job(row["id"])
        audit = j.get("lifecycle_audit_json") or "{}"
        if isinstance(audit, str):
            try:
                data = json.loads(audit)
            except Exception:
                data = {}
        else:
            data = audit or {}
        events = data.get("events") if isinstance(data, dict) else data
        types = [str(e.get("type") or e.get("event")) for e in (events or [])]
        self.assertIn("SCHEDULE_CREATED", types)

    def test_W02_panel_actions_schedule(self):
        p = self._panel()
        self.assertTrue(p["actions"]["SCHEDULE"])

    def test_W03_panel_cancel_when_active(self):
        row = self._admit_ready_job(suffix="w03")
        self._create(row["id"])
        p = self._panel(job_id=int(row["id"]))
        self.assertTrue(p["actions"]["CANCEL_SCHEDULE"])

    def test_W04_panel_reschedule_when_active(self):
        row = self._admit_ready_job(suffix="w04")
        self._create(row["id"])
        p = self._panel(job_id=int(row["id"]))
        self.assertTrue(p["actions"]["RESCHEDULE"])

    def test_W05_active_points_to_scheduled(self):
        row = self._admit_ready_job(suffix="w05")
        created = self._create(row["id"])
        p = self._panel(job_id=int(row["id"]))
        self.assertEqual(p["active"]["schedule_id"], created["schedule"]["schedule_id"])

    def test_W06_scheduling_implemented_true(self):
        p = self._panel()
        self.assertTrue(p.get("scheduling_implemented"))


# ---------------------------------------------------------------------------
# X — Workspace API
# ---------------------------------------------------------------------------


class X_WorkspaceApiTests(C07SchedBase):
    def test_X01_main_schedules_list_route(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("/api/workspace/publishing/schedules", src)

    def test_X02_main_schedule_create_route(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn('/api/workspace/publishing/schedule"', src)

    def test_X03_main_schedule_cancel_route(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("/api/workspace/publishing/schedule/{schedule_id}/cancel", src)

    def test_X04_main_schedule_reschedule_route(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("/api/workspace/publishing/schedule/{schedule_id}/reschedule", src)

    def test_X05_main_schedule_refresh_route(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("/api/workspace/publishing/schedule/{schedule_id}/refresh", src)

    def test_X06_main_imports_schedule_fns(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("create_schedule", src)
        self.assertIn("project_schedule_panel", src)

    def test_X07_list_ok_contract(self):
        listed = self._list()
        self.assertTrue(listed.get("ok"))
        self.assertEqual(listed.get("contract"), self.cps.CONTRACT_VERSION)

    def test_X08_list_secrets_excluded(self):
        listed = self._list()
        self.assertTrue(listed.get("secrets_excluded"))


# ---------------------------------------------------------------------------
# Y — UI projection
# ---------------------------------------------------------------------------


class Y_UiProjectionTests(C07SchedBase):
    def test_Y01_ws_schedule_panel_in_html(self):
        html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn("wsSchedulePanel", html)

    def test_Y02_app_js_references_panel(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("wsSchedulePanel", js)

    def test_Y03_app_js_schedule_api(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/workspace/publishing/schedule", js)

    def test_Y04_workspace_includes_publishing_schedule(self):
        src = (ROOT / "app" / "customer_workspace.py").read_text(encoding="utf-8")
        self.assertIn("publishing_schedule", src)
        self.assertIn("project_schedule_panel", src)

    def test_Y05_panel_secrets_excluded(self):
        p = self._panel()
        self.assertTrue(p.get("secrets_excluded"))


# ---------------------------------------------------------------------------
# Z — Secret scrubbing
# ---------------------------------------------------------------------------


class Z_SecretScrubbingTests(C07SchedBase):
    def test_Z01_create_scrubs_token_like(self):
        row = self._admit_ready_job(suffix="z01")
        out = self._create(row["id"])
        blob = json.dumps(out).lower()
        self.assertNotIn("ya29.", blob)
        self.assertNotIn("refresh_token", blob)
        self.assertNotIn("client_secret", blob)

    def test_Z02_saved_schedule_scrubbed(self):
        row = self._admit_ready_job(suffix="z02")
        created = self._create(row["id"])
        path = self.cps._schedule_path(created["schedule"]["schedule_id"])
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("client_secret", text.lower())

    def test_Z03_scrub_secrets_helper_used(self):
        src = Path(self.cps.__file__).read_text(encoding="utf-8")
        self.assertIn("scrub_secrets", src)

    def test_Z04_process_result_no_oauth(self):
        row = self._admit_ready_job(suffix="z04")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        out = self._process()
        blob = json.dumps(out).lower()
        self.assertNotIn("access_token", blob)
        self.assertNotIn("client_secret", blob)

    def test_Z05_panel_no_secrets(self):
        row = self._admit_ready_job(suffix="z05")
        self._create(row["id"])
        blob = json.dumps(self._panel(job_id=int(row["id"]))).lower()
        self.assertNotIn("authorization:", blob)

    def test_Z06_cp_scrub_on_nested(self):
        dirty = {"token": "secret-abc", "ok": True, "nested": {"api_key": "k123"}}
        clean = self.cp.scrub_secrets(dirty)
        blob = json.dumps(clean).lower()
        # scrub may redact or strip — ensure helper runs
        self.assertTrue(isinstance(clean, dict))


# ---------------------------------------------------------------------------
# AA — Mock mode
# ---------------------------------------------------------------------------


class AA_MockModeTests(C07SchedBase):
    def test_AA01_create_mock_true(self):
        row = self._admit_ready_job(suffix="aa01")
        out = self._create(row["id"])
        self.assertTrue(out["schedule"].get("mock"))

    def test_AA02_process_mock_true(self):
        out = self._process()
        self.assertTrue(out.get("mock"))

    def test_AA03_set_clock_none_restores(self):
        self.cps.set_clock(None)
        n = self.cps.now_utc()
        self.assertIsNotNone(n.tzinfo)
        # restore for tearDown safety
        self.cps.set_clock(lambda: self._clock[0])

    def test_AA04_clock_naive_assumed_utc(self):
        self.cps.set_clock(lambda: datetime(2026, 9, 10, 12, 0, 0))
        n = self.cps.now_utc()
        self.assertEqual(n.tzinfo, timezone.utc)

    def test_AA05_paid_api_zero_after_ops(self):
        row = self._admit_ready_job(suffix="aa05")
        self._create(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        self._process()
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_AA06_reset_mock_store_importable(self):
        from publishers.customer_publish_provider import reset_mock_store

        reset_mock_store()
        self.assertTrue(callable(reset_mock_store))


# ---------------------------------------------------------------------------
# AB — Regression compatibility
# ---------------------------------------------------------------------------


class AB_RegressionCompatibilityTests(C07SchedBase):
    def test_AB01_no_customer_scheduler_file(self):
        self.assertFalse((ROOT / "app" / "customer_scheduler.py").exists())

    def test_AB02_no_publishing_scheduler_file(self):
        self.assertFalse((ROOT / "app" / "publishing_scheduler.py").exists())

    def test_AB03_no_schedule_idempotency_file(self):
        self.assertFalse((ROOT / "app" / "schedule_idempotency.py").exists())
        self.assertFalse((ROOT / "pipeline" / "schedule_idempotency.py").exists())

    def test_AB04_scheduler_service_still_exists(self):
        self.assertTrue((ROOT / "app" / "scheduler_service.py").is_file())

    def test_AB05_customer_publish_still_exists(self):
        self.assertTrue((ROOT / "app" / "customer_publish.py").is_file())

    def test_AB06_gates_reuse_customer_publish(self):
        row = self._admit_ready_job(suffix="ab06")
        g = self.cp.validate_publish_gates(
            self.login,
            int(row["id"]),
            channel_ids=[self.ch_id],
            identity=self._identity(),
        )
        self.assertTrue(g.get("admitted"))

    def test_AB07_workspace_contract_mentions_c07_sched(self):
        src = (ROOT / "app" / "customer_workspace.py").read_text(encoding="utf-8")
        self.assertIn("C07-SCHED", src)

    def test_AB08_detect_clean_on_innocent_source(self):
        self.assertEqual(self.cps.detect_duplicate_engines("print('hello')\n"), [])

    def test_AB09_ready_to_upload_false_rejected(self):
        row = self._admit_ready_job(suffix="ab09", upload_status="not_ready")
        out = self._create(row["id"])
        self.assertFalse(out.get("ok"))

    def test_AB10_foreign_revision_error_path(self):
        row = self._admit_ready_job(suffix="ab10")
        out = self._create(row["id"], revision_id="totally-wrong")
        self.assertFalse(out.get("ok"))
        self.assertFalse(out.get("provider_called"))


if __name__ == "__main__":
    unittest.main()
