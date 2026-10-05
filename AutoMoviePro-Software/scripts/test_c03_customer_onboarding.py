"""C03 — Customer onboarding + dashboard foundation (paid APIs = 0)."""
from __future__ import annotations

import inspect
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.customer_foundation import build_foundation_snapshot
from app.customer_onboarding import (
    BLOCKED,
    COMPLETED,
    IN_PROGRESS,
    ITEM_BLOCKED,
    ITEM_COMPLETE,
    ITEM_NOT_CONFIGURED,
    ITEM_UNKNOWN,
    NOT_STARTED,
    READY,
    UNKNOWN,
    assert_customer_scope,
    build_checklist,
    build_dashboard,
    complete_onboarding,
    derive_onboarding_state,
    ensure_onboarding_table,
    get_onboarding_record,
    start_onboarding,
    upsert_onboarding_record,
)


def _id(**kw):
    base = {
        "auth_state": "AUTHENTICATED",
        "account_state": "ACTIVE",
        "entitlement_state": "ACTIVE",
        "production_access": True,
        "logged_in": True,
        "login_id": "alice",
        "display_name": "Alice",
    }
    base.update(kw)
    return base


def _ready_f():
    return build_foundation_snapshot(
        media_cap={"FFMPEG_AVAILABLE": True, "FFPROBE_AVAILABLE": True},
        operational={"status": "READY", "production_ready": True, "issues": []},
        api_readiness={"active": True},
    )


def _unknown_media_f():
    return build_foundation_snapshot(
        media_cap={},
        operational={"status": "READY", "production_ready": True, "issues": []},
        api_readiness={"active": True},
    )


def _blocked_f():
    return build_foundation_snapshot(
        media_cap={"FFMPEG_AVAILABLE": False, "FFPROBE_AVAILABLE": False},
        operational={"status": "BLOCKED", "production_ready": False, "issues": ["x"]},
        api_readiness={"active": True},
    )


class C03Base(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        from app import db as store

        self.store = store
        self._orig = store.DB_PATH
        store.DB_PATH = Path(self._tmp.name) / "c03.db"
        store.init_db()
        ensure_onboarding_table()

    def tearDown(self):
        self.store.DB_PATH = self._orig

    def _channel(self):
        cid = self.store.upsert_channel(
            {
                "youtube_name": "YT",
                "niche": "gadgets",
                "niche_id": 1,
                "short_upload_time": "12:00",
                "long_upload_time": "18:00",
                "languages_json": '["en","bn"]',
            }
        )
        return self.store.get_channel(cid)


class C03StartupTests(C03Base):
    def test_01_unauthenticated_startup(self):
        from app.main import dashboard

        with patch("app.main._require_session", return_value=None):
            out = dashboard()
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "login_required")

    def test_02_authenticated_first_run(self):
        ch = self._channel()
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": True},
            foundation=_ready_f(),
            channels=[ch],
            api_readiness={"active": True},
            active_jobs=[],
            recent_jobs=[],
        )
        # First run without start → READY if all complete, or NOT_STARTED if incomplete
        # With all complete and no record → READY (setup checks done, not completed)
        self.assertEqual(dash["onboarding"]["state"], READY)
        self.assertEqual(dash["startup_route"], "dashboard")

    def test_03_authenticated_incomplete_onboarding(self):
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": False, "message": "no"},
            foundation=_ready_f(),
            channels=[],
            api_readiness={"active": False, "message": "missing"},
            active_jobs=[],
            recent_jobs=[],
        )
        self.assertIn(dash["onboarding"]["state"], (NOT_STARTED, IN_PROGRESS, BLOCKED))
        start_onboarding("alice")
        dash2 = build_dashboard(
            identity=_id(),
            access={"allowed": False},
            foundation=_ready_f(),
            channels=[],
            api_readiness={"active": False},
            active_jobs=[],
            recent_jobs=[],
        )
        self.assertEqual(dash2["onboarding"]["state"], IN_PROGRESS)
        self.assertEqual(dash2["startup_route"], "onboarding_resume")

    def test_04_authenticated_completed_onboarding(self):
        ch = self._channel()
        start_onboarding("alice")
        # Force READY then complete
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": True},
            foundation=_ready_f(),
            channels=[ch],
            api_readiness={"active": True},
            active_jobs=[],
            recent_jobs=[],
        )
        self.assertEqual(dash["onboarding"]["state"], READY)
        complete_onboarding("alice", state=READY)
        dash2 = build_dashboard(
            identity=_id(),
            access={"allowed": True},
            foundation=_ready_f(),
            channels=[ch],
            api_readiness={"active": True},
            active_jobs=[],
            recent_jobs=[],
        )
        self.assertEqual(dash2["onboarding"]["state"], COMPLETED)
        self.assertEqual(dash2["startup_route"], "workspace")

    def test_05_expired_session(self):
        from app.main import dashboard

        with patch("app.main._require_session", return_value=None), patch(
            "app.customer_auth.evaluate_session",
            return_value=_id(auth_state="SESSION_EXPIRED", logged_in=False, production_access=False),
        ):
            out = dashboard()
        self.assertFalse(out.get("ok"))

    def test_06_disabled_account(self):
        checklist = build_checklist(
            identity=_id(auth_state="ACCOUNT_DISABLED", account_state="DISABLED", production_access=False),
            foundation=_ready_f(),
            access={"allowed": False},
            channels=[self._channel()],
            api_readiness={"active": True},
        )
        state = derive_onboarding_state(
            identity=_id(auth_state="ACCOUNT_DISABLED", account_state="DISABLED", production_access=False),
            checklist=checklist,
            record=None,
        )
        self.assertEqual(state, BLOCKED)

    def test_07_denied_entitlement(self):
        identity = _id(
            auth_state="ENTITLEMENT_REQUIRED",
            entitlement_state="EXPIRED",
            production_access=False,
        )
        checklist = build_checklist(
            identity=identity,
            foundation=_ready_f(),
            access={"allowed": False},
            channels=[self._channel()],
            api_readiness={"active": True},
        )
        state = derive_onboarding_state(identity=identity, checklist=checklist, record=None)
        self.assertEqual(state, BLOCKED)


class C03OnboardingStateTests(C03Base):
    def test_08_not_started(self):
        state = derive_onboarding_state(
            identity=_id(),
            checklist=[{"blocking": True, "state": ITEM_NOT_CONFIGURED}],
            record=None,
        )
        self.assertEqual(state, NOT_STARTED)

    def test_09_in_progress(self):
        start_onboarding("alice")
        state = derive_onboarding_state(
            identity=_id(),
            checklist=[
                {"blocking": True, "state": ITEM_COMPLETE},
                {"blocking": True, "state": ITEM_NOT_CONFIGURED},
            ],
            record=get_onboarding_record("alice"),
        )
        self.assertEqual(state, IN_PROGRESS)

    def test_10_ready(self):
        state = derive_onboarding_state(
            identity=_id(),
            checklist=[{"blocking": True, "state": ITEM_COMPLETE}],
            record=None,
        )
        self.assertEqual(state, READY)

    def test_11_completed(self):
        upsert_onboarding_record("alice", started_at="t0", completed_at="t1")
        state = derive_onboarding_state(
            identity=_id(),
            checklist=[{"blocking": True, "state": ITEM_COMPLETE}],
            record=get_onboarding_record("alice"),
        )
        self.assertEqual(state, COMPLETED)

    def test_12_blocked(self):
        state = derive_onboarding_state(
            identity=_id(),
            checklist=[{"blocking": True, "state": ITEM_BLOCKED}],
            record=None,
        )
        self.assertEqual(state, BLOCKED)

    def test_13_unknown(self):
        state = derive_onboarding_state(
            identity=_id(),
            checklist=[{"blocking": True, "state": ITEM_UNKNOWN}],
            record=None,
        )
        self.assertEqual(state, UNKNOWN)

    def test_14_state_persistence(self):
        start_onboarding("alice")
        rec = get_onboarding_record("alice")
        self.assertIsNotNone(rec)
        self.assertTrue(rec["started_at"])
        # Same login_id restores
        self.assertEqual(get_onboarding_record("alice")["started_at"], rec["started_at"])
        # Other customer separate
        self.assertIsNone(get_onboarding_record("bob"))

    def test_15_resume_incomplete_onboarding(self):
        start_onboarding("alice")
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": False},
            foundation=_ready_f(),
            channels=[],
            api_readiness={"active": False},
            active_jobs=[],
            recent_jobs=[],
        )
        self.assertTrue(dash["onboarding"]["can_resume"])
        self.assertEqual(dash["onboarding"]["resume_hint"], "channel")


class C03ChecklistTests(C03Base):
    def test_16_truthful_incomplete_item(self):
        items = build_checklist(
            identity=_id(),
            foundation=_ready_f(),
            access={},
            channels=[],
            api_readiness={"active": False},
        )
        ch = next(i for i in items if i["id"] == "channel.configured")
        self.assertEqual(ch["state"], ITEM_NOT_CONFIGURED)

    def test_17_truthful_complete_item(self):
        items = build_checklist(
            identity=_id(),
            foundation=_ready_f(),
            access={},
            channels=[self._channel()],
            api_readiness={"active": True},
        )
        ch = next(i for i in items if i["id"] == "channel.configured")
        self.assertEqual(ch["state"], ITEM_COMPLETE)

    def test_18_unknown_item(self):
        items = build_checklist(
            identity=_id(account_state="UNKNOWN", production_access=False, auth_state="AUTH_ERROR"),
            foundation=_ready_f(),
            access={},
            channels=[],
            api_readiness=None,
        )
        acct = next(i for i in items if i["id"] == "account.active")
        self.assertEqual(acct["state"], ITEM_UNKNOWN)

    def test_19_blocking_item(self):
        items = build_checklist(
            identity=_id(),
            foundation=_ready_f(),
            access={},
            channels=[],
            api_readiness={"active": False},
        )
        ch = next(i for i in items if i["id"] == "channel.configured")
        self.assertTrue(ch["blocking"])

    def test_20_non_blocking_item(self):
        items = build_checklist(
            identity=_id(),
            foundation=_ready_f(),
            access={},
            channels=[self._channel()],
            api_readiness={"active": True},
        )
        lang = next(i for i in items if i["id"] == "language.configured")
        self.assertFalse(lang["blocking"])

    def test_21_no_hardcoded_completion(self):
        src = Path(__file__).resolve().parents[1] / "app" / "customer_onboarding.py"
        text = src.read_text(encoding="utf-8")
        self.assertNotIn('state=ITEM_COMPLETE,\n                blocking=True,\n                message="hard', text)
        # Empty setup never yields COMPLETED without record + checks
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": False},
            foundation=_ready_f(),
            channels=[],
            api_readiness={"active": False},
            active_jobs=[],
            recent_jobs=[],
        )
        self.assertNotEqual(dash["onboarding"]["state"], COMPLETED)


class C03ReadinessTests(C03Base):
    def test_22_application_projection(self):
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": True},
            foundation=_ready_f(),
            channels=[self._channel()],
            api_readiness={"active": True},
            active_jobs=[],
            recent_jobs=[],
        )
        self.assertEqual(dash["readiness"]["application"], "READY")

    def test_23_media_projection(self):
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": True},
            foundation=_ready_f(),
            channels=[self._channel()],
            api_readiness={"active": True},
            active_jobs=[],
            recent_jobs=[],
        )
        self.assertEqual(dash["readiness"]["media"], "AVAILABLE")

    def test_24_production_projection(self):
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": True},
            foundation=_ready_f(),
            channels=[self._channel()],
            api_readiness={"active": True},
            active_jobs=[],
            recent_jobs=[],
        )
        self.assertEqual(dash["readiness"]["production"], "READY")

    def test_25_job_projection(self):
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": True},
            foundation={**_ready_f(), "active_job": {"state": "GENERATING"}},
            channels=[self._channel()],
            api_readiness={"active": True},
            active_jobs=[{"job_id": 1, "state": "GENERATING"}],
            recent_jobs=[],
        )
        self.assertEqual(dash["readiness"]["job"], "GENERATING")

    def test_26_unknown_remains_unknown(self):
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": True},
            foundation=_unknown_media_f(),
            channels=[self._channel()],
            api_readiness={"active": True},
            active_jobs=[],
            recent_jobs=[],
        )
        self.assertEqual(dash["readiness"]["media"], "UNKNOWN")
        self.assertEqual(dash["onboarding"]["state"], UNKNOWN)

    def test_27_blocked_remains_blocked(self):
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": True},
            foundation=_blocked_f(),
            channels=[self._channel()],
            api_readiness={"active": True},
            active_jobs=[],
            recent_jobs=[],
        )
        self.assertEqual(dash["readiness"]["production"], "BLOCKED")
        self.assertEqual(dash["onboarding"]["state"], BLOCKED)

    def test_28_c02_authorization_authoritative(self):
        from app.main import dashboard as dash_ep

        src = inspect.getsource(dash_ep)
        self.assertIn("can_customer_produce", src)
        self.assertNotIn("ALWAYS_ALLOW", src)
        # Projection reflects access denial
        dash = build_dashboard(
            identity=_id(production_access=False, entitlement_state="EXPIRED", auth_state="ENTITLEMENT_REQUIRED"),
            access={"allowed": False, "message": "Production access is not currently available for this account."},
            foundation=_ready_f(),
            channels=[self._channel()],
            api_readiness={"active": True},
            active_jobs=[],
            recent_jobs=[],
        )
        self.assertFalse(dash["access"]["production_allowed"])
        self.assertEqual(dash["onboarding"]["state"], BLOCKED)


class C03DashboardTests(C03Base):
    def test_29_authenticated_dashboard(self):
        from app.customer_auth import persist_session
        from app.main import dashboard

        persist_session(
            login_id="alice",
            token="local-dev-token",
            customer={"id": 1, "name": "Alice", "status": "active", "plan": "dev", "entitlement": "active"},
            api_base="local",
            auth_mode="local_dev",
        )
        with patch("pipeline.compose.probe_media_tool_capability", return_value={
            "FFMPEG_AVAILABLE": True,
            "FFPROBE_AVAILABLE": True,
        }), patch(
            "app.config.validate_production_operational",
            return_value={"status": "READY", "production_ready": True, "issues": []},
        ):
            out = dashboard()
        self.assertTrue(out.get("ok"))
        self.assertIn("checklist", out)
        self.assertIn("onboarding", out)

    def test_30_protected_dashboard(self):
        from app.main import dashboard

        out = dashboard()
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "login_required")

    def test_31_customer_scoped_job_summary(self):
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": True},
            foundation=_ready_f(),
            channels=[],
            api_readiness={"active": False},
            active_jobs=[{"job_id": 9, "state": "GENERATING"}],
            recent_jobs=[{"job_id": 8, "state": "READY_FOR_REVIEW"}],
        )
        self.assertEqual(dash["jobs"]["active_count"], 1)
        self.assertEqual(dash["jobs"]["ready_for_review_count"], 1)
        self.assertEqual(dash["jobs"]["latest_state"], "GENERATING")

    def test_32_active_recent_job_projection(self):
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": True},
            foundation=_ready_f(),
            channels=[],
            api_readiness={"active": False},
            active_jobs=[{"job_id": 1, "state": "QUEUED"}],
            recent_jobs=[{"job_id": 2, "state": "FAILED"}],
        )
        self.assertEqual(len(dash["jobs"]["active_jobs"]), 1)
        self.assertEqual(dash["jobs"]["failed_count"], 1)

    def test_33_workspace_navigation(self):
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": True},
            foundation=_ready_f(),
            channels=[self._channel()],
            api_readiness={"active": True},
            active_jobs=[],
            recent_jobs=[],
        )
        self.assertEqual(dash["workspace_href"], "#workspace")
        html = (Path(__file__).resolve().parents[1] / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="workspace"', html)
        self.assertIn("dashOpenWorkspace", html)

    def test_34_safe_error_projection(self):
        from app.main import dashboard

        with patch("app.main._require_session", return_value=None):
            out = dashboard()
        blob = json.dumps(out)
        self.assertNotIn("traceback", blob.lower())
        self.assertNotIn("password", blob.lower())

    def test_35_no_secrets_in_dashboard_output(self):
        dash = build_dashboard(
            identity=_id(),
            access={"allowed": True},
            foundation=_ready_f(),
            channels=[self._channel()],
            api_readiness={"active": True},
            active_jobs=[],
            recent_jobs=[],
        )
        blob = json.dumps(dash)
        self.assertNotIn("token", blob.lower().replace("entitlement", ""))
        self.assertNotIn("password", blob)
        self.assertNotIn("api_key", blob)
        self.assertNotIn("sk-", blob)


class C03SecurityIsolationTests(C03Base):
    def test_36_cross_customer_scope_denied(self):
        self.assertEqual(assert_customer_scope("bob", "alice"), "customer_scope_denied")
        self.assertIsNone(assert_customer_scope("", "alice"))
        self.assertIsNone(assert_customer_scope("alice", "alice"))

    def test_37_dashboard_rejects_forged_login_id(self):
        from app.customer_auth import persist_session
        from app.main import dashboard

        persist_session(
            login_id="alice",
            token="local-dev-token",
            customer={"id": 1, "name": "Alice", "status": "active", "plan": "dev", "entitlement": "active"},
            api_base="local",
            auth_mode="local_dev",
        )
        out = dashboard(login_id="bob")
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "customer_scope_denied")

    def test_38_onboarding_records_isolated_by_login(self):
        start_onboarding("alice")
        start_onboarding("bob")
        upsert_onboarding_record("alice", completed_at="done-a")
        self.assertTrue(get_onboarding_record("alice")["completed_at"])
        self.assertIsNone(get_onboarding_record("bob")["completed_at"])

    def test_39_complete_requires_ready(self):
        res = complete_onboarding("alice", state=IN_PROGRESS)
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("error"), "onboarding_not_ready")

    def test_40_no_second_auth_or_readiness_engine(self):
        text = (Path(__file__).resolve().parents[1] / "app" / "customer_onboarding.py").read_text(encoding="utf-8")
        self.assertNotIn("def can_customer_produce", text)
        self.assertNotIn("def build_foundation_snapshot", text)
        main_src = inspect.getsource(__import__("app.main", fromlist=["dashboard"]).dashboard)
        self.assertIn("can_customer_produce", main_src)
        self.assertIn("build_foundation_snapshot", main_src)


if __name__ == "__main__":
    unittest.main()
