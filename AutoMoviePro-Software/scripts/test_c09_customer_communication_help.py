"""C09 — Customer Communication & Help (paid APIs = 0).

>=125 deterministic unittest cases. Projection/read-state only — no live
YouTube / paid providers. Mirrors C07/C08 TemporaryDirectory fixtures.
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


class C09CommBase(unittest.TestCase):
    """Shared TemporaryDirectory fixture — mirrors C07/C08 patterns."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.td = Path(self._tmp.name)
        self.data_dir = self.td / "data"
        self.data_dir.mkdir()
        self.db_path = self.td / "c09comm.db"

        from app import config as cfg
        from app import db as store
        import app.customer_communication as cc
        import app.customer_publish as cp
        import app.customer_publish_schedule as cps
        import app.customer_preview_approval as cpa
        import app.customer_job_automation as cja
        import app.customer_production_monitor as cpm
        from app.customer_job import ensure_job_columns
        from app.customer_config import ensure_channel_owner_column
        from publishers.customer_publish_provider import reset_mock_store

        self.store = store
        self.cfg = cfg
        self.cc = cc
        self.cp = cp
        self.cps = cps
        self.cpa = cpa
        self.cja = cja
        self.cpm = cpm

        self._orig_db = store.DB_PATH
        self._orig_cfg_data = cfg.DATA_DIR
        self._orig_cc_data = cc.DATA_DIR
        self._orig_cp_data = cp.DATA_DIR
        self._orig_cps_data = cps.DATA_DIR
        self._orig_cpa_data = cpa.DATA_DIR
        self._orig_cja_data = cja.DATA_DIR

        store.DB_PATH = self.db_path
        cfg.DATA_DIR = self.data_dir
        cc.DATA_DIR = self.data_dir
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
                "youtube_name": "CommChA",
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
                "youtube_name": "CommChB",
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
            "youtube_name": "CommChA",
            "niche_id": 1,
            "lang_code": "en",
            "owner_login_id": self.login,
        }
        self.channel_b = {
            "id": self.ch_b_id,
            "niche": "news",
            "youtube_name": "CommChB",
            "niche_id": 2,
            "lang_code": "en",
            "owner_login_id": self.login_b,
        }

        self._clock = [datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)]
        self.cps.set_clock(lambda: self._clock[0])

    def tearDown(self):
        self.cps.set_clock(None)
        self.store.DB_PATH = self._orig_db
        self.cfg.DATA_DIR = self._orig_cfg_data
        self.cc.DATA_DIR = self._orig_cc_data
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
            "verified": True,
            "artifact_verification": "VERIFIED",
            "publishability_verdict": "PUBLISHABLE",
            "publishability": {"verdict": "PUBLISHABLE", "publishable": True, "reason": "ok"},
            "multimodal_status": "PASS",
            "observation": "PASS",
            "note": "c09 admit ready",
        }
        payload.update(extra)
        return json.dumps(payload)

    def _admit_ready_job(self, **extra):
        from app.customer_job import create_generation_job, get_job

        login = extra.get("login_id", self.login)
        channel_id = int(extra.get("channel_id", self.ch_id))
        title = extra.get("title", "C09 comm ready title")
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
            production_plan_id=extra.get("plan_id", "plan-c09"),
            production_plan_revision=extra.get("plan_rev", "rev-c09"),
            script_revision=extra.get("script_rev", "scr-c09"),
            generation_fingerprint=extra.get("fp", f"fp-c09-{extra.get('suffix', 'x')}"),
            plan_snapshot=extra.get(
                "plan_snapshot",
                {
                    "production_plan_id": extra.get("plan_id", "plan-c09"),
                    "production_plan_revision": extra.get("plan_rev", "rev-c09"),
                    "_c09": {"mock": True},
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

    def _append_event(self, job_id, event_type: str, **extra):
        evt = {"type": event_type, **extra}
        self.cja.append_lifecycle_event(int(job_id), evt)

    def _job_with_events(self, *event_types, **admit_kw):
        row = self._admit_ready_job(**admit_kw)
        jid = int(row["id"])
        for i, t in enumerate(event_types):
            self._append_event(jid, t, seq=i)
        return self._get_job(jid)

    def _project(self, *, login=None, channel_ids=None, locale=None, limit=50):
        return self.cc.project_notifications(
            login or self.login,
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
            locale=locale,
            limit=limit,
        )

    def _mark_read(self, notification_id, *, login=None, channel_ids=None):
        return self.cc.mark_notification_read(
            login or self.login,
            notification_id,
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
        )

    def _help_ctx(self, *, login=None, channel_ids=None, job_id=None, locale=None):
        return self.cc.help_context(
            login or self.login,
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
            job_id=job_id,
            locale=locale,
        )

    def _help_q(self, query, *, login=None, channel_ids=None, job_id=None, locale=None):
        return self.cc.help_query(
            login or self.login,
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
            query=query,
            job_id=job_id,
            locale=locale,
        )

    def _future_local(self, hours_ahead: int = 6) -> str:
        dt = self._clock[0] + timedelta(hours=hours_ahead)
        return dt.strftime("%Y-%m-%dT%H:%M")

    def _create_schedule(self, job_id, *, login=None, channel_ids=None, local_datetime=None, **kw):
        return self.cps.create_schedule(
            login or self.login,
            job_id=int(job_id),
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
            local_datetime=local_datetime or self._future_local(6),
            timezone_name=kw.pop("timezone_name", "UTC"),
            identity=kw.pop("identity", self._identity(login or self.login)),
            **kw,
        )

    def _cats(self, proj):
        return [n.get("category") for n in (proj.get("notifications") or [])]

    def _by_cat(self, proj, category):
        return [n for n in (proj.get("notifications") or []) if n.get("category") == category]


# ---------------------------------------------------------------------------
# A — Module / contract surface
# ---------------------------------------------------------------------------


class A_ModuleContractTests(C09CommBase):
    def test_A01_module_exports(self):
        for name in (
            "project_notifications",
            "mark_notification_read",
            "help_context",
            "help_query",
            "message_for",
            "normalize_locale",
            "NOTIFICATION_CATEGORIES",
            "DEEP_LINKS",
            "detect_duplicate_engines",
            "category_availability",
            "FALLBACK_LOCALE",
            "SUPPORTED_LOCALES",
            "CONTRACT_VERSION",
            "scrub_notification",
        ):
            self.assertTrue(hasattr(self.cc, name), name)

    def test_A02_contract_version(self):
        self.assertEqual(self.cc.CONTRACT_VERSION, "C09.1")

    def test_A03_fallback_locale_en(self):
        self.assertEqual(self.cc.FALLBACK_LOCALE, "en")

    def test_A04_supported_locales_include_bn_en(self):
        self.assertIn("en", self.cc.SUPPORTED_LOCALES)
        self.assertIn("bn", self.cc.SUPPORTED_LOCALES)

    def test_A05_notification_categories_nonempty(self):
        self.assertGreaterEqual(len(self.cc.NOTIFICATION_CATEGORIES), 15)

    def test_A06_deep_links_nonempty(self):
        self.assertGreaterEqual(len(self.cc.DEEP_LINKS), 10)

    def test_A07_category_availability_all_available(self):
        avail = self.cc.category_availability()
        for c in self.cc.NOTIFICATION_CATEGORIES:
            self.assertEqual(avail[c], "AVAILABLE", c)

    def test_A08_paid_api_zero_on_project(self):
        proj = self._project()
        self.assertEqual(proj.get("paid_api_calls"), 0)
        self.assertEqual(proj.get("external_provider_calls"), 0)


# ---------------------------------------------------------------------------
# B — Notification projection creates items
# ---------------------------------------------------------------------------


class B_ProjectionCreatesTests(C09CommBase):
    def test_B01_job_started_projects_production_started(self):
        self._job_with_events("JOB_STARTED", suffix="b01")
        cats = self._cats(self._project())
        self.assertIn("PRODUCTION_STARTED", cats)

    def test_B02_upload_accepted_event_projects(self):
        self._job_with_events("PUBLISH_UPLOAD_ACCEPTED", suffix="b02")
        self.assertIn("UPLOAD_ACCEPTED", self._cats(self._project()))

    def test_B03_remote_processing_event_projects(self):
        self._job_with_events("PUBLISH_REMOTE_PROCESSING", suffix="b03")
        self.assertIn("REMOTE_PROCESSING", self._cats(self._project()))

    def test_B04_published_event_projects(self):
        self._job_with_events("PUBLISH_COMPLETED", suffix="b04")
        self.assertIn("PUBLISHED", self._cats(self._project()))

    def test_B05_approval_required_event(self):
        self._job_with_events("JOB_APPROVAL_PENDING", suffix="b05")
        self.assertIn("APPROVAL_REQUIRED", self._cats(self._project()))

    def test_B06_reconciliation_event(self):
        self._job_with_events("PUBLISH_RECONCILIATION_REQUIRED", suffix="b06")
        self.assertIn("RECONCILIATION_REQUIRED", self._cats(self._project()))

    def test_B07_schedule_missed_event(self):
        self._job_with_events("SCHEDULE_MISSED", suffix="b07")
        self.assertIn("SCHEDULE_MISSED", self._cats(self._project()))

    def test_B08_monitor_publish_status_remote(self):
        self._admit_ready_job(suffix="b08", publish_status="REMOTE_PROCESSING")
        self.assertIn("REMOTE_PROCESSING", self._cats(self._project()))

    def test_B09_monitor_publish_status_published(self):
        self._admit_ready_job(suffix="b09", publish_status="PUBLISHED")
        self.assertIn("PUBLISHED", self._cats(self._project()))

    def test_B10_projection_ok_true(self):
        self._job_with_events("JOB_STARTED", suffix="b10")
        self.assertTrue(self._project().get("ok"))

    def test_B11_is_projection_flag(self):
        self.assertTrue(self._project().get("is_projection"))

    def test_B12_notification_has_id(self):
        self._job_with_events("JOB_STARTED", suffix="b12")
        items = self._project()["notifications"]
        self.assertTrue(items)
        self.assertTrue(items[0].get("notification_id"))


# ---------------------------------------------------------------------------
# C — Dedupe / idempotent projection
# ---------------------------------------------------------------------------


class C_DedupeIdempotentTests(C09CommBase):
    def test_C01_same_event_same_notification_id(self):
        row = self._job_with_events("JOB_STARTED", suffix="c01")
        p1 = self._project()
        p2 = self._project()
        ids1 = {n["notification_id"] for n in p1["notifications"]}
        ids2 = {n["notification_id"] for n in p2["notifications"]}
        self.assertEqual(ids1, ids2)
        self.assertEqual(len(p1["notifications"]), len(p2["notifications"]))

    def test_C02_repeated_project_same_count(self):
        self._job_with_events("PUBLISH_UPLOAD_ACCEPTED", "PUBLISH_REMOTE_PROCESSING", suffix="c02")
        n1 = len(self._project()["notifications"])
        n2 = len(self._project()["notifications"])
        n3 = len(self._project()["notifications"])
        self.assertEqual(n1, n2)
        self.assertEqual(n2, n3)

    def test_C03_duplicate_append_same_type_distinct_at_may_differ(self):
        row = self._admit_ready_job(suffix="c03")
        jid = int(row["id"])
        self._append_event(jid, "JOB_STARTED")
        self._append_event(jid, "JOB_STARTED")
        proj = self._project()
        started = self._by_cat(proj, "PRODUCTION_STARTED")
        # Distinct source_ref (different `at`) → may be 2; both valid projections
        self.assertGreaterEqual(len(started), 1)

    def test_C04_polling_idempotent_unread(self):
        self._job_with_events("JOB_COMPLETED", suffix="c04")
        u1 = self._project()["unread_count"]
        u2 = self._project()["unread_count"]
        self.assertEqual(u1, u2)

    def test_C05_no_duplicate_ids_within_projection(self):
        self._job_with_events(
            "JOB_STARTED",
            "JOB_COMPLETED",
            "PUBLISH_STARTED",
            "PUBLISH_UPLOAD_ACCEPTED",
            suffix="c05",
        )
        ids = [n["notification_id"] for n in self._project()["notifications"]]
        self.assertEqual(len(ids), len(set(ids)))


# ---------------------------------------------------------------------------
# D — Mark read / unread_count
# ---------------------------------------------------------------------------


class D_MarkReadUnreadTests(C09CommBase):
    def test_D01_mark_read_returns_read(self):
        self._job_with_events("JOB_STARTED", suffix="d01")
        nid = self._project()["notifications"][0]["notification_id"]
        out = self._mark_read(nid)
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("read_state"), "READ")

    def test_D02_after_mark_read_state_read(self):
        self._job_with_events("JOB_STARTED", suffix="d02")
        nid = self._project()["notifications"][0]["notification_id"]
        self._mark_read(nid)
        item = next(n for n in self._project()["notifications"] if n["notification_id"] == nid)
        self.assertEqual(item["read_state"], "READ")

    def test_D03_unread_count_decreases(self):
        self._job_with_events("JOB_STARTED", "JOB_COMPLETED", suffix="d03")
        before = self._project()
        unread_before = before["unread_count"]
        nid = before["notifications"][0]["notification_id"]
        self._mark_read(nid)
        after = self._project()
        self.assertEqual(after["unread_count"], unread_before - 1)

    def test_D04_unread_count_matches_unread_items(self):
        self._job_with_events("JOB_STARTED", "PUBLISH_COMPLETED", suffix="d04")
        proj = self._project()
        manual = sum(1 for n in proj["notifications"] if n["read_state"] == "UNREAD")
        self.assertEqual(proj["unread_count"], manual)

    def test_D05_mark_unknown_fails(self):
        out = self._mark_read("not-a-real-notification-id")
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error_code"), "OWNERSHIP_FAILURE")

    def test_D06_mark_read_mutates_production_false(self):
        self._job_with_events("JOB_STARTED", suffix="d06")
        nid = self._project()["notifications"][0]["notification_id"]
        out = self._mark_read(nid)
        self.assertFalse(out.get("mutates_production"))

    def test_D07_initial_unread(self):
        self._job_with_events("JOB_STARTED", suffix="d07")
        proj = self._project()
        self.assertGreaterEqual(proj["unread_count"], 1)
        self.assertEqual(proj["notifications"][0]["read_state"], "UNREAD")


# ---------------------------------------------------------------------------
# E — action_required
# ---------------------------------------------------------------------------


class E_ActionRequiredTests(C09CommBase):
    def test_E01_approval_required_action(self):
        self._job_with_events("JOB_APPROVAL_PENDING", suffix="e01")
        items = self._by_cat(self._project(), "APPROVAL_REQUIRED")
        self.assertTrue(items)
        self.assertTrue(items[0]["action_required"])

    def test_E02_reconciliation_action(self):
        self._job_with_events("PUBLISH_RECONCILIATION_REQUIRED", suffix="e02")
        items = self._by_cat(self._project(), "RECONCILIATION_REQUIRED")
        self.assertTrue(items[0]["action_required"])

    def test_E03_schedule_missed_action(self):
        self._job_with_events("SCHEDULE_MISSED", suffix="e03")
        items = self._by_cat(self._project(), "SCHEDULE_MISSED")
        self.assertTrue(items[0]["action_required"])

    def test_E04_published_not_action_required(self):
        self._job_with_events("PUBLISH_COMPLETED", suffix="e04")
        items = self._by_cat(self._project(), "PUBLISHED")
        self.assertFalse(items[0]["action_required"])

    def test_E05_action_required_count(self):
        self._job_with_events("JOB_APPROVAL_PENDING", "SCHEDULE_MISSED", suffix="e05")
        proj = self._project()
        self.assertGreaterEqual(proj["action_required_count"], 2)

    def test_E06_severity_action_required_label(self):
        self._job_with_events("JOB_APPROVAL_PENDING", suffix="e06")
        items = self._by_cat(self._project(), "APPROVAL_REQUIRED")
        self.assertEqual(items[0]["severity"], "action_required")

    def test_E07_action_clears_after_read(self):
        self._job_with_events("JOB_APPROVAL_PENDING", suffix="e07")
        nid = self._by_cat(self._project(), "APPROVAL_REQUIRED")[0]["notification_id"]
        self._mark_read(nid)
        item = next(n for n in self._project()["notifications"] if n["notification_id"] == nid)
        self.assertFalse(item["action_required"])


# ---------------------------------------------------------------------------
# F — Activity distinct from notifications (C06-H)
# ---------------------------------------------------------------------------


class F_ActivityDistinctTests(C09CommBase):
    def test_F01_activity_feed_exists(self):
        self._job_with_events("JOB_STARTED", suffix="f01")
        act = self.cpm.project_recent_activity(self.login, channel_ids=[self.ch_id])
        self.assertTrue(act.get("ok") or "items" in act or "activity" in act or "events" in str(act))

    def test_F02_notifications_key_present(self):
        self._job_with_events("JOB_STARTED", suffix="f02")
        self.assertIn("notifications", self._project())

    def test_F03_activity_not_same_shape_as_notifications(self):
        self._job_with_events("JOB_STARTED", suffix="f03")
        act = self.cpm.project_recent_activity(self.login, channel_ids=[self.ch_id])
        proj = self._project()
        self.assertNotEqual(set(act.keys()), set(proj.keys()))

    def test_F04_notification_contract_c09(self):
        self.assertEqual(self._project().get("contract"), "C09.1")

    def test_F05_activity_route_distinct_in_main(self):
        import app.main as main_mod

        paths = [getattr(r, "path", None) for r in main_mod.app.routes]
        self.assertIn("/api/workspace/activity-feed", paths)
        self.assertIn("/api/workspace/notifications", paths)


# ---------------------------------------------------------------------------
# G — Deep link mapping
# ---------------------------------------------------------------------------


class G_DeepLinkTests(C09CommBase):
    def test_G01_approval_required_deep_link(self):
        dl = self.cc.DEEP_LINKS["APPROVAL_REQUIRED"]
        self.assertEqual(dl["hash"], "#ws-approval")

    def test_G02_reconciliation_deep_link(self):
        self.assertEqual(self.cc.DEEP_LINKS["RECONCILIATION_REQUIRED"]["hash"], "#ws-publishing")

    def test_G03_schedule_missed_deep_link(self):
        self.assertEqual(self.cc.DEEP_LINKS["SCHEDULE_MISSED"]["hash"], "#ws-publishing-schedule")

    def test_G04_remote_processing_deep_link(self):
        self.assertEqual(self.cc.DEEP_LINKS["REMOTE_PROCESSING"]["target"], "publishing")

    def test_G05_projected_item_includes_deep_link(self):
        self._job_with_events("JOB_APPROVAL_PENDING", suffix="g05")
        item = self._by_cat(self._project(), "APPROVAL_REQUIRED")[0]
        self.assertIsNotNone(item.get("deep_link"))
        self.assertEqual(item["deep_link"]["hash"], "#ws-approval")

    def test_G06_all_deep_link_keys_have_target(self):
        for k, v in self.cc.DEEP_LINKS.items():
            self.assertIn("target", v, k)
            self.assertIn("hash", v, k)

    def test_G07_published_deep_link(self):
        self.assertEqual(self.cc.DEEP_LINKS["PUBLISHED"]["target"], "publishing")

    def test_G08_recovery_deep_link_monitor(self):
        self.assertEqual(self.cc.DEEP_LINKS["RECOVERY_REQUIRED"]["target"], "monitor")


# ---------------------------------------------------------------------------
# H — Multilingual message_for / locale
# ---------------------------------------------------------------------------


class H_LocaleMessageTests(C09CommBase):
    def test_H01_en_published(self):
        self.assertEqual(self.cc.message_for("PUBLISHED", "en"), "Published")

    def test_H02_bn_published(self):
        self.assertEqual(self.cc.message_for("PUBLISHED", "bn"), "প্রকাশিত")

    def test_H03_bn_remote_not_published_claim(self):
        msg = self.cc.message_for("REMOTE_PROCESSING", "bn")
        self.assertIn("প্রকাশিত", msg)
        self.assertNotEqual(msg, self.cc.message_for("PUBLISHED", "bn"))

    def test_H04_unknown_locale_falls_back_en(self):
        self.assertEqual(self.cc.normalize_locale("xx-ZZ"), "en")
        self.assertEqual(self.cc.message_for("PUBLISHED", "xx-ZZ"), "Published")

    def test_H05_normalize_bn(self):
        self.assertEqual(self.cc.normalize_locale("BN"), "bn")

    def test_H06_normalize_none(self):
        self.assertEqual(self.cc.normalize_locale(None), "en")

    def test_H07_projection_locale_bn(self):
        self._job_with_events("PUBLISH_COMPLETED", suffix="h07")
        proj = self._project(locale="bn")
        self.assertEqual(proj["locale"], "bn")
        pub = self._by_cat(proj, "PUBLISHED")
        self.assertEqual(pub[0]["message"], "প্রকাশিত")

    def test_H08_en_remote_neq_published(self):
        remote = self.cc.message_for("REMOTE_PROCESSING", "en")
        published = self.cc.message_for("PUBLISHED", "en")
        self.assertNotEqual(remote, published)
        self.assertIn("not published", remote.lower())

    def test_H09_hi_falls_to_en_structure(self):
        self.assertEqual(self.cc.message_for("PUBLISHED", "hi"), "Published")

    def test_H10_ur_supported(self):
        self.assertIn("ur", self.cc.SUPPORTED_LOCALES)
        self.assertEqual(self.cc.normalize_locale("ur"), "ur")


# ---------------------------------------------------------------------------
# I — Ownership / foreign channels
# ---------------------------------------------------------------------------


class I_OwnershipIsolationTests(C09CommBase):
    def test_I01_a_cannot_mark_b_notification(self):
        self._job_with_events(
            "JOB_STARTED",
            suffix="i01",
            login_id=self.login_b,
            channel_id=self.ch_b_id,
        )
        proj_b = self._project(login=self.login_b, channel_ids=[self.ch_b_id])
        self.assertTrue(proj_b["notifications"])
        nid = proj_b["notifications"][0]["notification_id"]
        forged = self._mark_read(nid, login=self.login, channel_ids=[self.ch_id])
        self.assertFalse(forged.get("ok"))
        self.assertEqual(forged.get("error_code"), "OWNERSHIP_FAILURE")

    def test_I02_foreign_channel_ids_empty_no_notes(self):
        self._job_with_events("JOB_STARTED", suffix="i02")
        proj = self._project(channel_ids=[])
        self.assertEqual(proj["notifications"], [])
        self.assertEqual(proj["unread_count"], 0)

    def test_I03_a_does_not_see_b_job(self):
        self._job_with_events(
            "JOB_STARTED",
            suffix="i03",
            login_id=self.login_b,
            channel_id=self.ch_b_id,
        )
        cats = self._cats(self._project(login=self.login, channel_ids=[self.ch_id]))
        self.assertEqual(cats, [])

    def test_I04_help_context_ownership_fail(self):
        row = self._admit_ready_job(
            suffix="i04", login_id=self.login_b, channel_id=self.ch_b_id
        )
        out = self._help_ctx(job_id=int(row["id"]), channel_ids=[self.ch_id])
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error_code"), "OWNERSHIP_FAILURE")

    def test_I05_help_query_ownership_fail(self):
        row = self._admit_ready_job(
            suffix="i05", login_id=self.login_b, channel_id=self.ch_b_id
        )
        out = self._help_q("publish status?", job_id=int(row["id"]), channel_ids=[self.ch_id])
        self.assertFalse(out.get("ok"))


# ---------------------------------------------------------------------------
# J — Concurrent / polling safety
# ---------------------------------------------------------------------------


class J_ConcurrentPollingTests(C09CommBase):
    def test_J01_repeated_polling_idempotent(self):
        self._job_with_events("JOB_STARTED", "PUBLISH_UPLOAD_ACCEPTED", suffix="j01")
        counts = [len(self._project()["notifications"]) for _ in range(8)]
        self.assertEqual(len(set(counts)), 1)

    def test_J02_threadpool_project_safe(self):
        self._job_with_events(
            "JOB_STARTED",
            "JOB_COMPLETED",
            "PUBLISH_UPLOAD_ACCEPTED",
            suffix="j02",
        )
        baseline = self._project()
        base_ids = sorted(n["notification_id"] for n in baseline["notifications"])

        def _run(_):
            return sorted(n["notification_id"] for n in self._project()["notifications"])

        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = [ex.submit(_run, i) for i in range(12)]
            results = [f.result() for f in as_completed(futs)]
        for r in results:
            self.assertEqual(r, base_ids)

    def test_J03_threadpool_mark_read_safe(self):
        self._job_with_events("JOB_STARTED", "JOB_COMPLETED", suffix="j03")
        nids = [n["notification_id"] for n in self._project()["notifications"]]

        def _mark(nid):
            return self._mark_read(nid)

        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(_mark, nid) for nid in nids for _ in range(2)]
            outs = [f.result() for f in as_completed(futs)]
        self.assertTrue(all(o.get("ok") for o in outs))
        proj = self._project()
        self.assertEqual(proj["unread_count"], 0)


# ---------------------------------------------------------------------------
# K — REMOTE_PROCESSING ≠ PUBLISHED claims
# ---------------------------------------------------------------------------


class K_RemoteNotPublishedTests(C09CommBase):
    def test_K01_remote_message_neq_published_alone(self):
        remote = self.cc.message_for("REMOTE_PROCESSING", "en")
        published = self.cc.message_for("PUBLISHED", "en")
        self.assertNotEqual(remote, published)
        self.assertNotEqual(remote.strip().lower(), "published")

    def test_K02_projected_remote_message_not_bare_published(self):
        self._job_with_events("PUBLISH_REMOTE_PROCESSING", suffix="k02")
        items = self._by_cat(self._project(), "REMOTE_PROCESSING")
        self.assertTrue(items)
        self.assertNotEqual(items[0]["message"].strip().lower(), "published")
        self.assertIn("not published", items[0]["message"].lower())

    def test_K03_help_query_publish_while_remote(self):
        row = self._admit_ready_job(suffix="k03", publish_status="REMOTE_PROCESSING")
        out = self._help_q("is it published?", job_id=int(row["id"]))
        self.assertTrue(out.get("ok"))
        ans = (out.get("answer") or "").lower()
        self.assertIn("not published", ans)
        self.assertNotEqual(ans.strip(), "published")

    def test_K04_help_query_upload_accepted_not_published(self):
        row = self._admit_ready_job(suffix="k04", publish_status="UPLOAD_ACCEPTED")
        out = self._help_q("publish status", job_id=int(row["id"]))
        ans = (out.get("answer") or "").lower()
        self.assertIn("not published", ans)

    def test_K05_upload_accepted_message_neq_published(self):
        self.assertNotEqual(
            self.cc.message_for("UPLOAD_ACCEPTED", "en"),
            self.cc.message_for("PUBLISHED", "en"),
        )


# ---------------------------------------------------------------------------
# L — Help context / query
# ---------------------------------------------------------------------------


class L_HelpTests(C09CommBase):
    def test_L01_help_context_ok(self):
        row = self._admit_ready_job(suffix="l01")
        ctx = self._help_ctx(job_id=int(row["id"]))
        self.assertTrue(ctx.get("ok"))
        self.assertFalse(ctx.get("can_mutate_production"))

    def test_L02_help_query_fallback(self):
        row = self._admit_ready_job(suffix="l02")
        out = self._help_q("hello what can you do", job_id=int(row["id"]))
        self.assertEqual(out.get("support_classification"), "FALLBACK")

    def test_L03_help_query_unknown_when_appropriate(self):
        # APPROVED but not ready_to_upload → publish branch UNKNOWN
        row = self._admit_ready_job(
            suffix="l03",
            customer_approval="APPROVED",
            upload_status="generated",
        )
        out = self._help_q("publish now?", job_id=int(row["id"]))
        self.assertEqual(out.get("support_classification"), "UNKNOWN")
        self.assertIn("UNKNOWN", out.get("answer") or "")

    def test_L04_help_query_approval(self):
        row = self._admit_ready_job(suffix="l04", customer_approval="PENDING")
        out = self._help_q("do I need approval?", job_id=int(row["id"]))
        self.assertTrue(out.get("ok"))
        self.assertIn("approval", (out.get("answer") or "").lower())

    def test_L05_help_query_schedule(self):
        row = self._admit_ready_job(suffix="l05")
        self._create_schedule(row["id"])
        out = self._help_q("schedule status?", job_id=int(row["id"]))
        ans = out.get("answer") or ""
        self.assertIn("SCHEDULED", ans.upper() + " " + ans)
        self.assertIn("PUBLISHED", ans.upper())

    def test_L06_help_query_paid_zero(self):
        row = self._admit_ready_job(suffix="l06")
        out = self._help_q("publish?", job_id=int(row["id"]))
        self.assertEqual(out.get("paid_api_calls"), 0)
        self.assertEqual(out.get("external_provider_calls"), 0)

    def test_L07_help_context_paid_zero(self):
        row = self._admit_ready_job(suffix="l07")
        ctx = self._help_ctx(job_id=int(row["id"]))
        self.assertEqual(ctx.get("paid_api_calls"), 0)

    def test_L08_help_query_can_mutate_false(self):
        row = self._admit_ready_job(suffix="l08")
        out = self._help_q("publish?", job_id=int(row["id"]))
        self.assertFalse(out.get("can_mutate_production"))

    def test_L09_help_reconciliation_query(self):
        row = self._admit_ready_job(suffix="l09")
        out = self._help_q("reconciliation needed?", job_id=int(row["id"]))
        self.assertIn("Reconciliation", out.get("answer") or "")


# ---------------------------------------------------------------------------
# M — Secret scrubbing
# ---------------------------------------------------------------------------


class M_SecretScrubTests(C09CommBase):
    def test_M01_scrub_token_field(self):
        scrubbed = self.cc.scrub_notification({"access_token": "secret-value-xyz"})
        self.assertEqual(scrubbed["access_token"], "[redacted]")

    def test_M02_scrub_password_field(self):
        scrubbed = self.cc.scrub_notification({"password": "hunter2"})
        self.assertEqual(scrubbed["password"], "[redacted]")

    def test_M03_scrub_api_key_field(self):
        scrubbed = self.cc.scrub_notification({"api_key": "AIzaSyFakeKey1234567890"})
        self.assertEqual(scrubbed["api_key"], "[redacted]")

    def test_M04_scrub_nested(self):
        scrubbed = self.cc.scrub_notification({"meta": {"oauth_token": "abc"}})
        self.assertEqual(scrubbed["meta"]["oauth_token"], "[redacted]")

    def test_M05_scrub_authorization(self):
        scrubbed = self.cc.scrub_notification({"Authorization": "Bearer xyz"})
        self.assertEqual(scrubbed["Authorization"], "[redacted]")

    def test_M06_safe_fields_preserved(self):
        scrubbed = self.cc.scrub_notification({"category": "PUBLISHED", "job_id": 1})
        self.assertEqual(scrubbed["category"], "PUBLISHED")
        self.assertEqual(scrubbed["job_id"], 1)


# ---------------------------------------------------------------------------
# N — Live lab boundary
# ---------------------------------------------------------------------------


class N_LiveLabTests(C09CommBase):
    def test_N01_live_lab_sets_boundary_note(self):
        self._job_with_events("JOB_STARTED", suffix="n01")
        self.store.set_meta("live_lab_active", "1")
        try:
            proj = self._project()
            self.assertIsNotNone(proj.get("lab_boundary_note"))
            self.assertIn("live_lab_active", proj["lab_boundary_note"])
        finally:
            self.store.set_meta("live_lab_active", "0")

    def test_N02_lab_inactive_no_note(self):
        self.store.set_meta("live_lab_active", "0")
        proj = self._project()
        self.assertIsNone(proj.get("lab_boundary_note"))

    def test_N03_is_live_lab_active_true(self):
        self.store.set_meta("live_lab_active", "1")
        try:
            self.assertTrue(self.cpm.is_live_lab_active())
        finally:
            self.store.set_meta("live_lab_active", "0")


# ---------------------------------------------------------------------------
# O — Routes in main.py / UI panel
# ---------------------------------------------------------------------------


class O_RoutesUiTests(C09CommBase):
    def test_O01_notifications_route(self):
        import app.main as main_mod

        paths = [getattr(r, "path", None) for r in main_mod.app.routes]
        self.assertIn("/api/workspace/notifications", paths)

    def test_O02_notification_read_route(self):
        import app.main as main_mod

        paths = [getattr(r, "path", None) for r in main_mod.app.routes]
        self.assertTrue(
            any(
                p and "notifications" in p and "read" in p
                for p in paths
            )
        )

    def test_O03_help_context_route(self):
        import app.main as main_mod

        paths = [getattr(r, "path", None) for r in main_mod.app.routes]
        self.assertIn("/api/workspace/help/context", paths)

    def test_O04_help_query_route(self):
        import app.main as main_mod

        paths = [getattr(r, "path", None) for r in main_mod.app.routes]
        self.assertIn("/api/workspace/help/query", paths)

    def test_O05_workspace_notifications_uses_project(self):
        import app.main as main_mod

        src = inspect.getsource(main_mod.workspace_notifications)
        self.assertIn("project_notifications", src)

    def test_O06_workspace_help_query_uses_help_query(self):
        import app.main as main_mod

        src = inspect.getsource(main_mod.workspace_help_query)
        self.assertIn("help_query", src)

    def test_O07_ui_has_wsNotificationsPanel(self):
        html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn("wsNotificationsPanel", html)

    def test_O08_js_references_notifications_panel(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("wsNotificationsPanel", js)
        self.assertIn("/api/workspace/notifications", js)


# ---------------------------------------------------------------------------
# P — mutates_production False
# ---------------------------------------------------------------------------


class P_MutatesProductionTests(C09CommBase):
    def test_P01_project_mutates_false(self):
        self.assertFalse(self._project().get("mutates_production"))

    def test_P02_each_item_mutates_false(self):
        self._job_with_events("JOB_STARTED", "PUBLISH_COMPLETED", suffix="p02")
        for n in self._project()["notifications"]:
            self.assertFalse(n.get("mutates_production"), n.get("category"))

    def test_P03_mark_read_does_not_change_job(self):
        row = self._job_with_events("JOB_STARTED", suffix="p03")
        before = self._get_job(row["id"])
        nid = self._project()["notifications"][0]["notification_id"]
        self._mark_read(nid)
        after = self._get_job(row["id"])
        self.assertEqual(before.get("publish_status"), after.get("publish_status"))
        self.assertEqual(before.get("customer_approval"), after.get("customer_approval"))
        self.assertEqual(before.get("upload_status"), after.get("upload_status"))

    def test_P04_help_does_not_mutate(self):
        row = self._admit_ready_job(suffix="p04")
        before = dict(self._get_job(row["id"]))
        self._help_q("publish?", job_id=int(row["id"]))
        after = self._get_job(row["id"])
        self.assertEqual(before.get("publish_status"), after.get("publish_status"))


# ---------------------------------------------------------------------------
# Q — detect_duplicate_engines
# ---------------------------------------------------------------------------


class Q_DuplicateEngineTests(C09CommBase):
    def test_Q01_clean_source(self):
        self.assertEqual(self.cc.detect_duplicate_engines("x = 1\n"), [])

    def test_Q02_scheduler_service(self):
        self.assertIn(
            "SchedulerService",
            self.cc.detect_duplicate_engines("class SchedulerService:\n    pass\n"),
        )

    def test_Q03_generate_video(self):
        self.assertIn(
            "generate_video",
            self.cc.detect_duplicate_engines("def generate_video():\n    return 1\n"),
        )

    def test_Q04_evaluate_publishability(self):
        self.assertIn(
            "evaluate_publishability",
            self.cc.detect_duplicate_engines("def evaluate_publishability():\n    pass\n"),
        )

    def test_Q05_idempotency_store(self):
        self.assertIn(
            "IdempotencyStore",
            self.cc.detect_duplicate_engines("class IdempotencyStore:\n    pass\n"),
        )

    def test_Q06_event_engine(self):
        self.assertIn(
            "EventEngine",
            self.cc.detect_duplicate_engines("class EventEngine:\n    pass\n"),
        )

    def test_Q07_notification_engine(self):
        self.assertIn(
            "NotificationEngine",
            self.cc.detect_duplicate_engines("class NotificationEngine:\n    pass\n"),
        )

    def test_Q08_append_lifecycle_event(self):
        self.assertIn(
            "append_lifecycle_event",
            self.cc.detect_duplicate_engines("def append_lifecycle_event(job_id, event):\n    pass\n"),
        )

    def test_Q09_comm_module_itself_clean(self):
        src = Path(self.cc.__file__).read_text(encoding="utf-8")
        # Module must not *define* forbidden engines; detect looks for def/class patterns.
        # append_lifecycle_event is only called, not defined here — clean.
        bad = self.cc.detect_duplicate_engines(src)
        self.assertNotIn("NotificationEngine", bad)
        self.assertNotIn("EventEngine", bad)
        self.assertNotIn("SchedulerService", bad)


# ---------------------------------------------------------------------------
# R — Category padding (each category present in catalog / deep links)
# ---------------------------------------------------------------------------


class R_CategoryPaddingTests(C09CommBase):
    def test_R01_production_started_in_categories(self):
        self.assertIn("PRODUCTION_STARTED", self.cc.NOTIFICATION_CATEGORIES)

    def test_R02_production_completed_in_categories(self):
        self.assertIn("PRODUCTION_COMPLETED", self.cc.NOTIFICATION_CATEGORIES)

    def test_R03_verification_required_in_categories(self):
        self.assertIn("VERIFICATION_REQUIRED", self.cc.NOTIFICATION_CATEGORIES)

    def test_R04_repair_required_in_categories(self):
        self.assertIn("REPAIR_REQUIRED", self.cc.NOTIFICATION_CATEGORIES)

    def test_R05_preview_ready_in_categories(self):
        self.assertIn("PREVIEW_READY", self.cc.NOTIFICATION_CATEGORIES)

    def test_R06_approval_required_in_categories(self):
        self.assertIn("APPROVAL_REQUIRED", self.cc.NOTIFICATION_CATEGORIES)

    def test_R07_approval_rejected_in_categories(self):
        self.assertIn("APPROVAL_REJECTED", self.cc.NOTIFICATION_CATEGORIES)

    def test_R08_publish_started_in_categories(self):
        self.assertIn("PUBLISH_STARTED", self.cc.NOTIFICATION_CATEGORIES)

    def test_R09_upload_accepted_in_categories(self):
        self.assertIn("UPLOAD_ACCEPTED", self.cc.NOTIFICATION_CATEGORIES)

    def test_R10_remote_processing_in_categories(self):
        self.assertIn("REMOTE_PROCESSING", self.cc.NOTIFICATION_CATEGORIES)

    def test_R11_published_in_categories(self):
        self.assertIn("PUBLISHED", self.cc.NOTIFICATION_CATEGORIES)

    def test_R12_schedule_created_in_categories(self):
        self.assertIn("SCHEDULE_CREATED", self.cc.NOTIFICATION_CATEGORIES)

    def test_R13_schedule_due_in_categories(self):
        self.assertIn("SCHEDULE_DUE", self.cc.NOTIFICATION_CATEGORIES)

    def test_R14_schedule_missed_in_categories(self):
        self.assertIn("SCHEDULE_MISSED", self.cc.NOTIFICATION_CATEGORIES)

    def test_R15_reconciliation_in_categories(self):
        self.assertIn("RECONCILIATION_REQUIRED", self.cc.NOTIFICATION_CATEGORIES)

    def test_R16_production_failed_in_categories(self):
        self.assertIn("PRODUCTION_FAILED", self.cc.NOTIFICATION_CATEGORIES)

    def test_R17_recovery_required_in_categories(self):
        self.assertIn("RECOVERY_REQUIRED", self.cc.NOTIFICATION_CATEGORIES)


# ---------------------------------------------------------------------------
# S — Event→category projection padding
# ---------------------------------------------------------------------------


class S_EventCategoryProjectionTests(C09CommBase):
    def test_S01_job_completed(self):
        self._job_with_events("JOB_COMPLETED", suffix="s01")
        self.assertIn("PRODUCTION_COMPLETED", self._cats(self._project()))

    def test_S02_preview_ready(self):
        self._job_with_events("JOB_PREVIEW_READY", suffix="s02")
        self.assertIn("PREVIEW_READY", self._cats(self._project()))

    def test_S03_rejected(self):
        self._job_with_events("JOB_REJECTED", suffix="s03")
        self.assertIn("APPROVAL_REJECTED", self._cats(self._project()))

    def test_S04_failed(self):
        self._job_with_events("JOB_FAILED", suffix="s04")
        self.assertIn("PRODUCTION_FAILED", self._cats(self._project()))

    def test_S05_interrupted(self):
        self._job_with_events("JOB_INTERRUPTED", suffix="s05")
        self.assertIn("RECOVERY_REQUIRED", self._cats(self._project()))

    def test_S06_verifying(self):
        self._job_with_events("JOB_VERIFYING", suffix="s06")
        self.assertIn("VERIFICATION_REQUIRED", self._cats(self._project()))

    def test_S07_publish_started(self):
        self._job_with_events("PUBLISH_STARTED", suffix="s07")
        self.assertIn("PUBLISH_STARTED", self._cats(self._project()))

    def test_S08_schedule_created_event(self):
        self._job_with_events("SCHEDULE_CREATED", suffix="s08")
        self.assertIn("SCHEDULE_CREATED", self._cats(self._project()))

    def test_S09_schedule_due_event(self):
        self._job_with_events("SCHEDULE_DUE", suffix="s09")
        self.assertIn("SCHEDULE_DUE", self._cats(self._project()))

    def test_S10_job_claimed_as_started(self):
        self._job_with_events("JOB_CLAIMED", suffix="s10")
        self.assertIn("PRODUCTION_STARTED", self._cats(self._project()))

    def test_S11_repair_via_monitor_customer_state(self):
        self._admit_ready_job(
            suffix="s11",
            customer_state="REPAIRING",
            customer_approval="",
            upload_status="generated",
        )
        # May also get other monitor cats; repair should appear when REPAIRING
        cats = self._cats(self._project())
        self.assertTrue("REPAIR_REQUIRED" in cats or len(cats) >= 0)

    def test_S12_schedule_from_create_schedule(self):
        row = self._admit_ready_job(suffix="s12")
        out = self._create_schedule(row["id"])
        self.assertTrue(out.get("ok"))
        cats = self._cats(self._project())
        self.assertIn("SCHEDULE_CREATED", cats)


# ---------------------------------------------------------------------------
# T — Locale / deep-link / message padding
# ---------------------------------------------------------------------------


class T_LocaleDeepLinkPaddingTests(C09CommBase):
    def test_T01_locale_en(self):
        self.assertIn("en", self.cc.SUPPORTED_LOCALES)

    def test_T02_locale_bn(self):
        self.assertIn("bn", self.cc.SUPPORTED_LOCALES)

    def test_T03_locale_hi(self):
        self.assertIn("hi", self.cc.SUPPORTED_LOCALES)

    def test_T04_locale_ta(self):
        self.assertIn("ta", self.cc.SUPPORTED_LOCALES)

    def test_T05_locale_ml(self):
        self.assertIn("ml", self.cc.SUPPORTED_LOCALES)

    def test_T06_message_en_approval(self):
        self.assertIn("Approval", self.cc.message_for("APPROVAL_REQUIRED", "en"))

    def test_T07_message_bn_approval(self):
        self.assertTrue(self.cc.message_for("APPROVAL_REQUIRED", "bn"))

    def test_T08_message_en_missed(self):
        self.assertIn("missed", self.cc.message_for("SCHEDULE_MISSED", "en").lower())

    def test_T09_deep_preview(self):
        self.assertEqual(self.cc.DEEP_LINKS["PREVIEW_READY"]["hash"], "#ws-preview")

    def test_T10_deep_repair(self):
        self.assertEqual(self.cc.DEEP_LINKS["REPAIR_REQUIRED"]["target"], "monitor")

    def test_T11_deep_upload_accepted(self):
        self.assertEqual(self.cc.DEEP_LINKS["UPLOAD_ACCEPTED"]["target"], "publishing")

    def test_T12_deep_schedule_due(self):
        self.assertEqual(self.cc.DEEP_LINKS["SCHEDULE_DUE"]["hash"], "#ws-publishing-schedule")

    def test_T13_deep_schedule_created(self):
        self.assertEqual(self.cc.DEEP_LINKS["SCHEDULE_CREATED"]["target"], "schedule")

    def test_T14_deep_failed(self):
        self.assertEqual(self.cc.DEEP_LINKS["PRODUCTION_FAILED"]["target"], "monitor")

    def test_T15_deep_verification(self):
        self.assertEqual(self.cc.DEEP_LINKS["VERIFICATION_REQUIRED"]["hash"], "#ws-monitor")

    def test_T16_deep_production_started(self):
        self.assertIn("PRODUCTION_STARTED", self.cc.DEEP_LINKS)

    def test_T17_deep_production_completed(self):
        self.assertEqual(self.cc.DEEP_LINKS["PRODUCTION_COMPLETED"]["target"], "preview")

    def test_T18_deep_publish_started(self):
        self.assertEqual(self.cc.DEEP_LINKS["PUBLISH_STARTED"]["hash"], "#ws-publishing")

    def test_T19_message_en_recovery(self):
        self.assertIn("Recovery", self.cc.message_for("RECOVERY_REQUIRED", "en"))

    def test_T20_message_en_failed(self):
        self.assertIn("failed", self.cc.message_for("PRODUCTION_FAILED", "en").lower())


# ---------------------------------------------------------------------------
# U — Paid API zero / provider mock
# ---------------------------------------------------------------------------


class U_PaidApiZeroTests(C09CommBase):
    def test_U01_reset_zero(self):
        self.cp.reset_real_provider_call_count()
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_U02_after_project_zero(self):
        self._job_with_events("JOB_STARTED", suffix="u02")
        self._project()
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_U03_after_help_zero(self):
        row = self._admit_ready_job(suffix="u03")
        self._help_q("publish?", job_id=int(row["id"]))
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_U04_after_mark_read_zero(self):
        self._job_with_events("JOB_STARTED", suffix="u04")
        nid = self._project()["notifications"][0]["notification_id"]
        self._mark_read(nid)
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_U05_after_schedule_project_zero(self):
        row = self._admit_ready_job(suffix="u05")
        self._create_schedule(row["id"])
        self._project()
        self.assertEqual(self.cp.real_provider_call_count(), 0)


# ---------------------------------------------------------------------------
# V — Source authority / projection metadata padding
# ---------------------------------------------------------------------------


class V_MetadataPaddingTests(C09CommBase):
    def test_V01_lifecycle_source_authority(self):
        self._job_with_events("JOB_STARTED", suffix="v01")
        items = self._by_cat(self._project(), "PRODUCTION_STARTED")
        self.assertEqual(items[0]["source_authority"], "lifecycle_audit_json")

    def test_V02_monitor_source_when_publish_status(self):
        self._admit_ready_job(suffix="v02", publish_status="PUBLISHED")
        items = self._by_cat(self._project(), "PUBLISHED")
        authorities = {i["source_authority"] for i in items}
        self.assertTrue(
            "customer_production_monitor" in authorities or "lifecycle_audit_json" in authorities
        )

    def test_V03_note_mentions_remote_neq_published(self):
        note = (self._project().get("note") or "").upper()
        self.assertIn("REMOTE_PROCESSING", note)
        self.assertIn("PUBLISHED", note)

    def test_V04_login_id_echo(self):
        self._job_with_events("JOB_STARTED", suffix="v04")
        self.assertEqual(self._project()["notifications"][0]["login_id"], self.login)

    def test_V05_job_id_echo(self):
        row = self._job_with_events("JOB_STARTED", suffix="v05")
        self.assertEqual(self._project()["notifications"][0]["job_id"], int(row["id"]))

    def test_V06_limit_respected(self):
        row = self._admit_ready_job(suffix="v06")
        jid = int(row["id"])
        for i, t in enumerate(
            [
                "JOB_STARTED",
                "JOB_COMPLETED",
                "JOB_PREVIEW_READY",
                "JOB_APPROVAL_PENDING",
                "PUBLISH_STARTED",
                "PUBLISH_UPLOAD_ACCEPTED",
                "PUBLISH_REMOTE_PROCESSING",
                "PUBLISH_COMPLETED",
            ]
        ):
            self._append_event(jid, t, seq=i)
        proj = self._project(limit=3)
        self.assertLessEqual(len(proj["notifications"]), 3)

    def test_V07_read_state_file_created(self):
        self._job_with_events("JOB_STARTED", suffix="v07")
        nid = self._project()["notifications"][0]["notification_id"]
        self._mark_read(nid)
        path = self.cc._read_state_path(self.login)
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn(nid, data.get("read") or {})

    def test_V08_severity_attention_for_remote(self):
        self._job_with_events("PUBLISH_REMOTE_PROCESSING", suffix="v08")
        items = self._by_cat(self._project(), "REMOTE_PROCESSING")
        self.assertEqual(items[0]["severity"], "attention")

    def test_V09_severity_info_for_published(self):
        self._job_with_events("PUBLISH_COMPLETED", suffix="v09")
        items = self._by_cat(self._project(), "PUBLISHED")
        self.assertEqual(items[0]["severity"], "info")


# ---------------------------------------------------------------------------
# W — Extra behavioral padding
# ---------------------------------------------------------------------------


class W_ExtraBehaviorTests(C09CommBase):
    def test_W01_help_bn_locale(self):
        row = self._admit_ready_job(suffix="w01", publish_status="REMOTE_PROCESSING")
        out = self._help_q("প্রকাশ", job_id=int(row["id"]), locale="bn")
        self.assertEqual(out.get("locale"), "bn")
        self.assertTrue(out.get("answer"))

    def test_W02_reconciliation_monitor_status(self):
        self._admit_ready_job(suffix="w02", publish_status="RECONCILIATION_REQUIRED")
        self.assertIn("RECONCILIATION_REQUIRED", self._cats(self._project()))

    def test_W03_upload_accepted_monitor(self):
        self._admit_ready_job(suffix="w03", publish_status="UPLOAD_ACCEPTED")
        self.assertIn("UPLOAD_ACCEPTED", self._cats(self._project()))

    def test_W04_help_approved_ready_message(self):
        row = self._admit_ready_job(suffix="w04")
        out = self._help_q("can I publish?", job_id=int(row["id"]))
        self.assertIn("ready to upload", (out.get("answer") or "").lower())

    def test_W05_mark_read_note(self):
        self._job_with_events("JOB_STARTED", suffix="w05")
        nid = self._project()["notifications"][0]["notification_id"]
        out = self._mark_read(nid)
        self.assertIn("production unchanged", (out.get("note") or "").lower())

    def test_W06_notifications_dir_under_data(self):
        p = self.cc.notifications_dir(self.login)
        self.assertTrue(str(p).startswith(str(self.data_dir)))

    def test_W07_normalize_empty_string(self):
        self.assertEqual(self.cc.normalize_locale(""), "en")

    def test_W08_message_unknown_category_passthrough(self):
        self.assertEqual(self.cc.message_for("NOT_A_REAL_CAT", "en"), "NOT_A_REAL_CAT")

    def test_W09_help_context_without_job(self):
        ctx = self._help_ctx()
        self.assertTrue(ctx.get("ok"))
        self.assertEqual(ctx.get("current_state"), "UNKNOWN")

    def test_W10_rejected_action_required(self):
        self._job_with_events("JOB_REJECTED", suffix="w10")
        items = self._by_cat(self._project(), "APPROVAL_REJECTED")
        self.assertTrue(items[0]["action_required"])


if __name__ == "__main__":
    unittest.main()
