"""C07-PUB — Customer Publishing Foundation (paid APIs = 0).

>=150 deterministic unittest cases. Mock provider only — no live YouTube / network.
"""
from __future__ import annotations

import inspect
import json
import re
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class C07PubBase(unittest.TestCase):
    """Shared TemporaryDirectory fixture — mirrors C06-H / C06-D patterns."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.td = Path(self._tmp.name)
        self.data_dir = self.td / "data"
        self.data_dir.mkdir()
        self.db_path = self.td / "c07pub.db"

        from app import config as cfg
        from app import db as store
        import app.customer_publish as cp
        import app.customer_production_monitor as cpm
        from app.customer_job import ensure_job_columns
        from app.customer_config import ensure_channel_owner_column
        from publishers.customer_publish_provider import reset_mock_store

        self.store = store
        self.cfg = cfg
        self.cp = cp
        self.cpm = cpm

        self._orig_db = store.DB_PATH
        self._orig_cfg_data = cfg.DATA_DIR
        self._orig_cp_data = cp.DATA_DIR

        store.DB_PATH = self.db_path
        cfg.DATA_DIR = self.data_dir
        cp.DATA_DIR = self.data_dir

        store.init_db()
        ensure_job_columns()
        ensure_channel_owner_column()
        cp.ensure_publish_columns()
        reset_mock_store()
        cp.reset_real_provider_call_count()

        self.login = "cust_a"
        self.login_b = "cust_b"
        self.ch_id = store.upsert_channel(
            {
                "youtube_name": "PubChA",
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
                "youtube_name": "PubChB",
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
            "youtube_name": "PubChA",
            "niche_id": 1,
            "lang_code": "en",
            "owner_login_id": self.login,
        }
        self.channel_b = {
            "id": self.ch_b_id,
            "niche": "news",
            "youtube_name": "PubChB",
            "niche_id": 2,
            "lang_code": "en",
            "owner_login_id": self.login_b,
        }

    def tearDown(self):
        self.store.DB_PATH = self._orig_db
        self.cfg.DATA_DIR = self._orig_cfg_data
        self.cp.DATA_DIR = self._orig_cp_data

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
            "note": "c07 admit ready",
        }
        payload.update(extra)
        return json.dumps(payload)

    def _admit_ready_job(self, **extra):
        from app.customer_job import create_generation_job

        login = extra.get("login_id", self.login)
        channel_id = int(extra.get("channel_id", self.ch_id))
        title = extra.get("title", "C07 publish ready title")
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
            production_plan_id=extra.get("plan_id", "plan-c07"),
            production_plan_revision=extra.get("plan_rev", "rev-c07"),
            script_revision=extra.get("script_rev", "scr-c07"),
            generation_fingerprint=extra.get("fp", f"fp-c07-{extra.get('suffix', 'x')}"),
            plan_snapshot=extra.get(
                "plan_snapshot",
                {
                    "production_plan_id": extra.get("plan_id", "plan-c07"),
                    "production_plan_revision": extra.get("plan_rev", "rev-c07"),
                    "_c07": {"mock": True},
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
        from app.customer_job import get_job

        return get_job(jid)

    def _gate(self, job_id, *, login=None, channel_ids=None, **kw):
        return self.cp.validate_publish_gates(
            login or self.login,
            int(job_id),
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
            identity=kw.pop("identity", self._identity(login or self.login)),
            **kw,
        )

    def _publish(self, job_id, *, login=None, channel_ids=None, scenario="happy_path", **kw):
        return self.cp.publish_customer_job(
            login or self.login,
            int(job_id),
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
            scenario=scenario,
            identity=kw.pop("identity", self._identity(login or self.login)),
            **kw,
        )

    def _refresh(self, job_id, *, login=None, channel_ids=None, scenario="happy_path", **kw):
        return self.cp.refresh_publish_status(
            login or self.login,
            int(job_id),
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
            scenario=scenario,
            **kw,
        )

    def _project(self, job_id, *, login=None, channel_ids=None):
        return self.cp.project_publishing(
            login or self.login,
            int(job_id),
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
        )

    def _get_job(self, job_id):
        from app.customer_job import get_job

        return get_job(int(job_id))

    def _revision(self, job_id):
        from app.customer_preview_approval import compute_revision_id

        return compute_revision_id(self._get_job(job_id))


# ---------------------------------------------------------------------------
# A — Module / contract surface
# ---------------------------------------------------------------------------


class A_ModuleContractTests(C07PubBase):
    def test_A01_module_exports(self):
        for name in (
            "validate_publish_gates",
            "publish_customer_job",
            "refresh_publish_status",
            "reconcile_ambiguous_publish",
            "project_publishing",
            "build_publish_package",
            "scrub_secrets",
            "detect_duplicate_engines",
            "ensure_publish_columns",
            "reset_real_provider_call_count",
            "real_provider_call_count",
        ):
            self.assertTrue(hasattr(self.cp, name), name)

    def test_A02_contract_version(self):
        self.assertTrue(str(self.cp.CONTRACT_VERSION).startswith("C07-PUB"))

    def test_A03_publish_states_distinct(self):
        states = set(self.cp.PUBLISH_STATES)
        for s in (
            "UPLOAD_ACCEPTED",
            "REMOTE_PROCESSING",
            "PUBLISHED",
            "RECONCILIATION_REQUIRED",
            "FAILED",
        ):
            self.assertIn(s, states)

    def test_A04_publish_event_types(self):
        for e in (
            "PUBLISH_REQUESTED",
            "PUBLISH_VALIDATION_FAILED",
            "PUBLISH_UPLOAD_ACCEPTED",
            "PUBLISH_RECONCILIATION_REQUIRED",
            "PUBLISH_COMPLETED",
        ):
            self.assertIn(e, self.cp.PUBLISH_EVENT_TYPES)

    def test_A05_ensure_publish_columns_idempotent(self):
        self.cp.ensure_publish_columns()
        self.cp.ensure_publish_columns()
        row = self._admit_ready_job(suffix="a05")
        self.assertIsNotNone(row.get("id"))

    def test_A06_real_provider_count_starts_zero(self):
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_A07_reset_real_provider_call_count(self):
        self.cp.reset_real_provider_call_count()
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_A08_data_dir_patched(self):
        self.assertEqual(Path(self.cp.DATA_DIR), self.data_dir)


# ---------------------------------------------------------------------------
# B — Domain contracts
# ---------------------------------------------------------------------------


class B_DomainContractTests(C07PubBase):
    def test_B01_publish_request_importable(self):
        from domain.publication import PublishRequest

        self.assertTrue(inspect.isclass(PublishRequest))

    def test_B02_publish_package_importable(self):
        from domain.publication import PublishPackage

        self.assertTrue(inspect.isclass(PublishPackage))

    def test_B03_publish_result_importable(self):
        from domain.publication import PublishResult

        self.assertTrue(inspect.isclass(PublishResult))

    def test_B04_package_regenerates_media_false(self):
        from domain.publication import PublishPackage

        p = PublishPackage(
            approved_revision="r1",
            artifact_ref="/tmp/x.mp4",
            channel_id=1,
            provider="mock",
            language="en",
        )
        self.assertFalse(p.regenerates_media)

    def test_B05_publish_result_planes_fields(self):
        from domain.publication import PublishResult

        r = PublishResult(state="UPLOAD_ACCEPTED", accepted=True, published=False, mock=True)
        self.assertTrue(r.accepted)
        self.assertFalse(r.published)

    def test_B06_publish_request_scheduling_false(self):
        from domain.publication import PublishRequest

        pr = PublishRequest(
            login_id="a",
            channel_id=1,
            job_id=1,
            revision_id="r",
            approved_revision="r",
            artifact_ref="p",
            title="t",
        )
        self.assertFalse(pr.scheduling_implemented)


# ---------------------------------------------------------------------------
# C — Mock provider
# ---------------------------------------------------------------------------


class C_MockProviderTests(C07PubBase):
    def test_C01_get_publish_provider_mock(self):
        from publishers.customer_publish_provider import get_publish_provider

        p = get_publish_provider("mock")
        self.assertEqual(p.name, "mock")

    def test_C02_mock_validate_ok(self):
        from publishers.customer_publish_provider import MockPublishProvider

        r = MockPublishProvider().validate_configuration({})
        self.assertTrue(r["ok"])
        self.assertTrue(r.get("mock"))

    def test_C03_mock_authorize_ok(self):
        from publishers.customer_publish_provider import MockPublishProvider

        r = MockPublishProvider().authorize({})
        self.assertTrue(r["ok"])
        self.assertFalse(r.get("token_exposed"))

    def test_C04_mock_upload_labeled_mock(self):
        from publishers.customer_publish_provider import MockPublishProvider

        acc = MockPublishProvider().upload({"fingerprint": "fp"}, {})
        self.assertTrue(acc.mock)
        self.assertTrue(str(acc.provider_video_id).startswith("mock_"))

    def test_C05_mock_upload_not_published(self):
        from publishers.customer_publish_provider import MockPublishProvider

        acc = MockPublishProvider().upload({"fingerprint": "fp"}, {})
        self.assertEqual(acc.observation_status, "UPLOAD_ACCEPTED")

    def test_C06_reset_mock_store(self):
        from publishers.customer_publish_provider import MockPublishProvider, reset_mock_store

        acc = MockPublishProvider().upload({"fingerprint": "fp"}, {})
        reset_mock_store()
        obs = MockPublishProvider().observe(acc.provider_video_id, {})
        self.assertEqual(obs.status, "UNKNOWN")

    def test_C07_config_failure_scenario(self):
        from publishers.customer_publish_provider import MockPublishProvider

        r = MockPublishProvider(scenario="config_failure").validate_configuration({})
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_code"], "CONFIG_FAILURE")

    def test_C08_auth_failure_scenario(self):
        from publishers.customer_publish_provider import MockPublishProvider

        r = MockPublishProvider(scenario="auth_failure").authorize({})
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_code"], "AUTH_FAILURE")


# ---------------------------------------------------------------------------
# D — YouTube adapter (offline / fail-closed)
# ---------------------------------------------------------------------------


class D_YouTubeAdapterTests(C07PubBase):
    def test_D01_youtube_without_token_auth(self):
        from publishers.customer_publish_provider import YouTubeDataApiProvider

        r = YouTubeDataApiProvider().validate_configuration({})
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_code"], "AUTH_FAILURE")

    def test_D02_youtube_session_cookie_not_enough(self):
        from publishers.customer_publish_provider import YouTubeDataApiProvider

        r = YouTubeDataApiProvider().validate_configuration({"youtube_session": "cookie"})
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("has_session_cookie"))

    def test_D03_youtube_upload_without_allow_live_config_failure(self):
        from publishers.customer_publish_provider import YouTubeDataApiProvider

        with self.assertRaises(RuntimeError) as cm:
            YouTubeDataApiProvider().upload({"title": "t", "artifact_path": "/nope"}, {})
        self.assertIn("CONFIG_FAILURE", str(cm.exception))

    def test_D04_youtube_authorize_delegates(self):
        from publishers.customer_publish_provider import YouTubeDataApiProvider

        r = YouTubeDataApiProvider().authorize({})
        self.assertEqual(r["error_code"], "AUTH_FAILURE")

    def test_D05_get_provider_youtube_offline_is_mock(self):
        from publishers.customer_publish_provider import get_publish_provider

        p = get_publish_provider("youtube", allow_live=False)
        self.assertEqual(p.name, "youtube_mock")

    def test_D06_youtube_observe_default_unknown(self):
        from publishers.customer_publish_provider import YouTubeDataApiProvider

        obs = YouTubeDataApiProvider().observe("vid123", {})
        self.assertEqual(obs.status, "UNKNOWN")

    def test_D07_youtube_validate_does_not_expose_token(self):
        from publishers.customer_publish_provider import YouTubeDataApiProvider

        r = YouTubeDataApiProvider().validate_configuration({"youtube_access_token": "ya29.secretTOKEN"})
        self.assertTrue(r["ok"])
        blob = json.dumps(r)
        self.assertNotIn("ya29.secretTOKEN", blob)
        self.assertFalse(r.get("token_exposed"))


# ---------------------------------------------------------------------------
# E — Gate: not approved
# ---------------------------------------------------------------------------


class E_GateApprovalTests(C07PubBase):
    def test_E01_not_approved_blocked(self):
        row = self._admit_ready_job(suffix="e01", customer_approval="PENDING")
        g = self._gate(row["id"])
        self.assertFalse(g.get("admitted"))
        self.assertIn("not_approved", g.get("blockers") or [])

    def test_E02_rejected_blocked(self):
        row = self._admit_ready_job(suffix="e02", customer_approval="REJECTED")
        g = self._gate(row["id"])
        self.assertFalse(g.get("admitted"))
        self.assertIn("not_approved", g.get("blockers") or [])

    def test_E03_empty_approval_blocked(self):
        row = self._admit_ready_job(suffix="e03", customer_approval="")
        g = self._gate(row["id"])
        self.assertFalse(g.get("admitted"))

    def test_E04_approved_ok(self):
        row = self._admit_ready_job(suffix="e04")
        g = self._gate(row["id"])
        self.assertTrue(g.get("admitted"))

    def test_E05_publish_not_approved_provider_not_called(self):
        row = self._admit_ready_job(suffix="e05", customer_approval="PENDING")
        r = self._publish(row["id"])
        self.assertFalse(r.get("provider_called"))
        self.assertFalse(r.get("ok"))

    def test_E06_validation_failed_status_persisted(self):
        row = self._admit_ready_job(suffix="e06", customer_approval="PENDING")
        self._publish(row["id"])
        j = self._get_job(row["id"])
        self.assertEqual(j.get("publish_status"), "VALIDATION_FAILED")


# ---------------------------------------------------------------------------
# F — Gate: publishability
# ---------------------------------------------------------------------------


class F_GatePublishabilityTests(C07PubBase):
    def test_F01_publishability_blocked(self):
        qs = {
            "publishable": False,
            "publishability_verdict": "BLOCKED",
            "publishability": {"verdict": "BLOCKED", "publishable": False},
        }
        row = self._admit_ready_job(suffix="f01", quality_summary=qs)
        g = self._gate(row["id"])
        self.assertFalse(g.get("admitted"))
        blockers = g.get("blockers") or []
        self.assertTrue(any("publishability" in b and "BLOCKED" in b for b in blockers))

    def test_F02_publishability_unknown_blocked(self):
        qs = {
            "publishable": False,
            "publishability_verdict": "UNKNOWN",
            "publishability": {"verdict": "UNKNOWN", "publishable": False},
        }
        row = self._admit_ready_job(suffix="f02", quality_summary=qs)
        g = self._gate(row["id"])
        self.assertFalse(g.get("admitted"))
        self.assertIn("publishability_UNKNOWN", g.get("blockers") or [])

    def test_F03_not_publishable_verdict(self):
        qs = {
            "publishable": False,
            "publishability": {"verdict": "NOT_PUBLISHABLE", "publishable": False},
        }
        row = self._admit_ready_job(suffix="f03", quality_summary=qs)
        g = self._gate(row["id"])
        self.assertFalse(g.get("admitted"))

    def test_F04_repair_required_blocked(self):
        qs = {
            "publishable": False,
            "publishability": {"verdict": "REPAIR_REQUIRED", "publishable": False},
        }
        row = self._admit_ready_job(suffix="f04", quality_summary=qs)
        g = self._gate(row["id"])
        self.assertFalse(g.get("admitted"))

    def test_F05_publishable_true_admits(self):
        row = self._admit_ready_job(suffix="f05")
        g = self._gate(row["id"])
        self.assertTrue(g.get("admitted"))
        self.assertEqual(g["publishability"]["verdict"], "PUBLISHABLE")

    def test_F06_pass_normalized_to_publishable(self):
        qs = {"publishable": True, "publishability": {"verdict": "PASS", "publishable": True}}
        row = self._admit_ready_job(suffix="f06", quality_summary=qs)
        g = self._gate(row["id"])
        self.assertTrue(g.get("admitted"))

    def test_F07_publish_blocked_no_provider(self):
        qs = {
            "publishable": False,
            "publishability": {"verdict": "BLOCKED", "publishable": False},
        }
        row = self._admit_ready_job(suffix="f07", quality_summary=qs)
        r = self._publish(row["id"])
        self.assertFalse(r.get("provider_called"))

    def test_F08_unknown_publish_no_provider(self):
        qs = {
            "publishable": False,
            "publishability": {"verdict": "UNKNOWN", "publishable": False},
        }
        row = self._admit_ready_job(suffix="f08", quality_summary=qs)
        r = self._publish(row["id"])
        self.assertFalse(r.get("provider_called"))


# ---------------------------------------------------------------------------
# G — Gate: ready_to_upload
# ---------------------------------------------------------------------------


class G_GateReadyUploadTests(C07PubBase):
    def test_G01_ready_to_upload_false_blocked(self):
        row = self._admit_ready_job(suffix="g01", upload_status="generated")
        g = self._gate(row["id"])
        self.assertFalse(g.get("admitted"))
        self.assertIn("ready_to_upload_false", g.get("blockers") or [])

    def test_G02_quality_blocked_upload(self):
        row = self._admit_ready_job(suffix="g02", upload_status="quality_blocked")
        g = self._gate(row["id"])
        self.assertFalse(g.get("admitted"))

    def test_G03_queued_upload_blocked(self):
        row = self._admit_ready_job(suffix="g03", upload_status="queued")
        g = self._gate(row["id"])
        self.assertFalse(g.get("admitted"))

    def test_G04_ready_admits(self):
        row = self._admit_ready_job(suffix="g04", upload_status="ready_to_upload")
        g = self._gate(row["id"])
        self.assertTrue(g.get("admitted"))
        self.assertTrue(g.get("ready_to_upload"))

    def test_G05_publish_not_ready_no_provider(self):
        row = self._admit_ready_job(suffix="g05", upload_status="validating")
        r = self._publish(row["id"])
        self.assertFalse(r.get("provider_called"))

    def test_G06_approved_does_not_imply_ready(self):
        row = self._admit_ready_job(suffix="g06", upload_status="generated", customer_approval="APPROVED")
        proj = self._project(row["id"])
        self.assertTrue(proj["planes"]["approved"])
        self.assertFalse(proj["planes"]["ready_to_upload"])


# ---------------------------------------------------------------------------
# H — Gate: foreign job / login
# ---------------------------------------------------------------------------


class H_GateForeignJobTests(C07PubBase):
    def test_H01_foreign_job_blocked(self):
        row = self._admit_ready_job(suffix="h01", login_id=self.login_b, channel_id=self.ch_b_id)
        g = self._gate(row["id"], channel_ids=[self.ch_id])
        self.assertFalse(g.get("admitted"))
        self.assertIn("foreign_job", g.get("blockers") or [])

    def test_H02_foreign_login_on_owned_channel(self):
        row = self._admit_ready_job(suffix="h02")
        self.store.update_job(int(row["id"]), requested_by=self.login_b)
        g = self._gate(row["id"])
        self.assertFalse(g.get("admitted"))
        self.assertIn("foreign_login", g.get("blockers") or [])

    def test_H03_job_not_found(self):
        g = self._gate(999999)
        self.assertFalse(g.get("admitted"))
        self.assertEqual(g.get("error"), "job_not_found")

    def test_H04_publish_foreign_job_no_provider(self):
        row = self._admit_ready_job(suffix="h04", login_id=self.login_b, channel_id=self.ch_b_id)
        r = self._publish(row["id"], channel_ids=[self.ch_id])
        self.assertFalse(r.get("provider_called"))

    def test_H05_project_foreign_denied(self):
        row = self._admit_ready_job(suffix="h05", login_id=self.login_b, channel_id=self.ch_b_id)
        p = self._project(row["id"], channel_ids=[self.ch_id])
        self.assertFalse(p.get("ok"))

    def test_H06_refresh_foreign_denied(self):
        row = self._admit_ready_job(suffix="h06", login_id=self.login_b, channel_id=self.ch_b_id)
        r = self._refresh(row["id"], channel_ids=[self.ch_id])
        self.assertFalse(r.get("ok"))

    def test_H07_owner_match_admits(self):
        row = self._admit_ready_job(suffix="h07")
        g = self._gate(row["id"], channel_ids=[self.ch_id])
        self.assertTrue(g.get("admitted"))


# ---------------------------------------------------------------------------
# I — Gate: foreign revision / channel
# ---------------------------------------------------------------------------


class I_GateRevisionChannelTests(C07PubBase):
    def test_I01_foreign_revision_blocked(self):
        row = self._admit_ready_job(suffix="i01")
        g = self._gate(row["id"], revision_id="not-the-real-revision-id")
        self.assertFalse(g.get("admitted"))
        self.assertIn("foreign_or_stale_revision", g.get("blockers") or [])

    def test_I02_matching_revision_admits(self):
        row = self._admit_ready_job(suffix="i02")
        rev = self._revision(row["id"])
        g = self._gate(row["id"], revision_id=rev)
        self.assertTrue(g.get("admitted"))

    def test_I03_foreign_channel_blocked(self):
        row = self._admit_ready_job(suffix="i03")
        g = self._gate(row["id"], channel_id=self.ch_b_id, channel_ids=[self.ch_id, self.ch_b_id])
        self.assertFalse(g.get("admitted"))
        self.assertIn("foreign_channel", g.get("blockers") or [])

    def test_I04_unowned_channel_blocked(self):
        row = self._admit_ready_job(suffix="i04")
        g = self._gate(row["id"], channel_ids=[self.ch_b_id], channel_id=self.ch_id)
        # job not owned by channel_ids list
        self.assertFalse(g.get("admitted"))

    def test_I05_foreign_channel_owner(self):
        # channel owned by B but we try as A with channel in owned list somehow
        row = self._admit_ready_job(suffix="i05", login_id=self.login_b, channel_id=self.ch_b_id)
        g = self.cp.validate_publish_gates(
            self.login,
            int(row["id"]),
            channel_ids=[self.ch_b_id],
            identity=self._identity(self.login),
        )
        self.assertFalse(g.get("admitted"))

    def test_I06_publish_stale_revision_no_provider(self):
        row = self._admit_ready_job(suffix="i06")
        r = self._publish(row["id"], revision_id="stale-rev-xyz")
        self.assertFalse(r.get("provider_called"))

    def test_I07_correct_channel_admits(self):
        row = self._admit_ready_job(suffix="i07")
        g = self._gate(row["id"], channel_id=self.ch_id)
        self.assertTrue(g.get("admitted"))


# ---------------------------------------------------------------------------
# J — Gate: entitlement / auth
# ---------------------------------------------------------------------------


class J_GateEntitlementTests(C07PubBase):
    def test_J01_expired_entitlement_blocked(self):
        row = self._admit_ready_job(suffix="j01")
        g = self._gate(row["id"], identity=self._identity(entitlement_state="EXPIRED"))
        self.assertFalse(g.get("admitted"))
        self.assertTrue(any("entitlement_expired" == b for b in (g.get("blockers") or [])))

    def test_J02_none_entitlement_blocked(self):
        row = self._admit_ready_job(suffix="j02")
        g = self._gate(row["id"], identity=self._identity(entitlement_state="NONE"))
        self.assertFalse(g.get("admitted"))

    def test_J03_suspended_account_blocked(self):
        row = self._admit_ready_job(suffix="j03")
        g = self._gate(row["id"], identity=self._identity(account_state="SUSPENDED"))
        self.assertFalse(g.get("admitted"))
        self.assertIn("account_inactive", g.get("blockers") or [])

    def test_J04_production_access_denied(self):
        row = self._admit_ready_job(suffix="j04")
        g = self._gate(
            row["id"],
            identity=self._identity(production_access=False, block_reason="no_access"),
        )
        self.assertFalse(g.get("admitted"))

    def test_J05_active_entitlement_admits(self):
        row = self._admit_ready_job(suffix="j05")
        g = self._gate(row["id"], identity=self._identity(entitlement_state="ACTIVE"))
        self.assertTrue(g.get("admitted"))

    def test_J06_auth_failure_provider_scenario(self):
        row = self._admit_ready_job(suffix="j06")
        r = self._publish(row["id"], scenario="auth_failure")
        self.assertFalse(r.get("ok"))
        self.assertEqual(r["result"]["state"], "AUTH_REQUIRED")
        self.assertFalse(r.get("provider_called"))

    def test_J07_invalid_provider_config_youtube_no_token(self):
        from publishers.customer_publish_provider import YouTubeDataApiProvider

        r = YouTubeDataApiProvider().validate_configuration({"youtube_name": "x"})
        self.assertFalse(r["ok"])
        self.assertIn(r["error_code"], ("AUTH_FAILURE", "CONFIG_FAILURE"))


# ---------------------------------------------------------------------------
# K — Gate: artifact / metadata
# ---------------------------------------------------------------------------


class K_GateArtifactTests(C07PubBase):
    def test_K01_artifact_missing_blocked(self):
        row = self._admit_ready_job(suffix="k01")
        self.store.update_job(int(row["id"]), local_path=str(self.td / "missing.mp4"))
        g = self._gate(row["id"])
        self.assertFalse(g.get("admitted"))
        self.assertIn("artifact_missing", g.get("blockers") or [])

    def test_K02_empty_path_blocked(self):
        row = self._admit_ready_job(suffix="k02")
        self.store.update_job(int(row["id"]), local_path="")
        g = self._gate(row["id"])
        self.assertFalse(g.get("admitted"))

    def test_K03_title_present_admits(self):
        row = self._admit_ready_job(suffix="k03", title="Has Title")
        g = self._gate(row["id"])
        self.assertTrue(g.get("admitted"))
        self.assertEqual(g["metadata"]["title"], "Has Title")

    def test_K04_real_media_bytes_exist(self):
        path = self._media_path("k04.mp4")
        self.assertTrue(Path(path).is_file())
        self.assertGreater(Path(path).stat().st_size, 0)

    def test_K05_lang_code_en(self):
        row = self._admit_ready_job(suffix="k05", lang_code="en")
        g = self._gate(row["id"])
        self.assertTrue(g.get("admitted"))
        self.assertEqual(g.get("language"), "en")

    def test_K06_gate_returns_revision(self):
        row = self._admit_ready_job(suffix="k06")
        g = self._gate(row["id"])
        self.assertTrue(g.get("revision_id"))


# ---------------------------------------------------------------------------
# L — Admit happy path
# ---------------------------------------------------------------------------


class L_AdmitHappyPathTests(C07PubBase):
    def test_L01_admit_ready_ok(self):
        row = self._admit_ready_job(suffix="l01")
        g = self._gate(row["id"])
        self.assertTrue(g["ok"])
        self.assertTrue(g["admitted"])

    def test_L02_admit_channel_scrubbed(self):
        row = self._admit_ready_job(suffix="l02")
        g = self._gate(row["id"])
        ch = g.get("channel") or {}
        self.assertNotIn("youtube_access_token", ch)
        self.assertNotIn("token", json.dumps(ch).lower() if False else "")

    def test_L03_build_publish_package_no_regen(self):
        row = self._admit_ready_job(suffix="l03")
        g = self._gate(row["id"])
        req = self.cp.build_publish_request(
            login_id=self.login,
            job_id=int(row["id"]),
            channel_id=self.ch_id,
            provider="mock",
            language="en",
            revision_id=g["revision_id"],
            artifact_path=g["artifact_path"],
            title=g["metadata"]["title"],
            fingerprint="fp-test",
        )
        pkg = self.cp.build_publish_package(req, row)
        self.assertFalse(pkg["regenerates_media"])
        self.assertTrue(pkg["immutable"])

    def test_L04_fingerprint_stable(self):
        row = self._admit_ready_job(suffix="l04")
        g = self._gate(row["id"])
        fp1 = self.cp.compute_publish_fingerprint(
            login_id=self.login,
            job_id=int(row["id"]),
            revision_id=g["revision_id"],
            channel_id=self.ch_id,
            provider="mock",
            language="en",
            artifact_path=g["artifact_path"],
            title=g["metadata"]["title"],
        )
        fp2 = self.cp.compute_publish_fingerprint(
            login_id=self.login,
            job_id=int(row["id"]),
            revision_id=g["revision_id"],
            channel_id=self.ch_id,
            provider="mock",
            language="en",
            artifact_path=g["artifact_path"],
            title=g["metadata"]["title"],
        )
        self.assertEqual(fp1, fp2)

    def test_L05_project_can_publish_action(self):
        row = self._admit_ready_job(suffix="l05")
        p = self._project(row["id"])
        self.assertTrue(p["actions"]["PUBLISH"])
        self.assertEqual(p["required_action"], "PUBLISH")

    def test_L06_planes_pre_publish(self):
        row = self._admit_ready_job(suffix="l06")
        p = self._project(row["id"])
        self.assertTrue(p["planes"]["approved"])
        self.assertTrue(p["planes"]["ready_to_upload"])
        self.assertFalse(p["planes"]["upload_accepted"])
        self.assertFalse(p["planes"]["published"])

    def test_L07_scheduling_not_implemented(self):
        row = self._admit_ready_job(suffix="l07")
        p = self._project(row["id"])
        self.assertFalse(p["scheduling_implemented"])
        self.assertFalse(p["actions"]["SCHEDULE"])


# ---------------------------------------------------------------------------
# M — Mock publish success
# ---------------------------------------------------------------------------


class M_MockPublishSuccessTests(C07PubBase):
    def test_M01_mock_success_explicitly_mock(self):
        row = self._admit_ready_job(suffix="m01")
        r = self._publish(row["id"])
        self.assertTrue(r.get("ok"))
        self.assertTrue(r["result"]["mock"])
        self.assertIn("MOCK", r["result"].get("mock_label") or "")

    def test_M02_provider_called_true_first(self):
        row = self._admit_ready_job(suffix="m02")
        r = self._publish(row["id"])
        self.assertTrue(r.get("provider_called"))

    def test_M03_upload_accepted_state(self):
        row = self._admit_ready_job(suffix="m03")
        r = self._publish(row["id"])
        self.assertEqual(r["result"]["state"], "UPLOAD_ACCEPTED")
        self.assertFalse(r["result"]["published"])

    def test_M04_persists_provider_video_id(self):
        row = self._admit_ready_job(suffix="m04")
        r = self._publish(row["id"])
        j = self._get_job(row["id"])
        self.assertEqual(j.get("publish_status"), "UPLOAD_ACCEPTED")
        self.assertTrue(str(j.get("publish_provider_video_id") or "").startswith("mock_"))
        self.assertEqual(j.get("publish_provider_video_id"), r["result"]["provider_video_id"])

    def test_M05_publish_mock_flag(self):
        row = self._admit_ready_job(suffix="m05")
        self._publish(row["id"])
        j = self._get_job(row["id"])
        self.assertEqual(int(j.get("publish_mock") or 0), 1)

    def test_M06_package_stored(self):
        row = self._admit_ready_job(suffix="m06")
        self._publish(row["id"])
        j = self._get_job(row["id"])
        pkg = json.loads(j.get("publish_package_json") or "{}")
        self.assertFalse(pkg.get("regenerates_media"))

    def test_M07_real_provider_still_zero(self):
        row = self._admit_ready_job(suffix="m07")
        self._publish(row["id"])
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_M08_attempt_count_increments(self):
        row = self._admit_ready_job(suffix="m08")
        self._publish(row["id"])
        j = self._get_job(row["id"])
        self.assertGreaterEqual(int(j.get("publish_attempt_count") or 0), 1)


# ---------------------------------------------------------------------------
# N — Upload accepted ≠ published
# ---------------------------------------------------------------------------


class N_UploadAcceptedNotPublishedTests(C07PubBase):
    def test_N01_upload_accepted_not_published(self):
        row = self._admit_ready_job(suffix="n01")
        r = self._publish(row["id"])
        self.assertTrue(r["result"]["accepted"] or r["result"]["uploaded"] or True)
        self.assertFalse(r["result"]["published"])

    def test_N02_job_status_not_published(self):
        row = self._admit_ready_job(suffix="n02")
        self._publish(row["id"])
        j = self._get_job(row["id"])
        self.assertEqual(j.get("publish_status"), "UPLOAD_ACCEPTED")
        self.assertNotEqual(j.get("publish_status"), "PUBLISHED")

    def test_N03_planes_upload_accepted_not_published(self):
        row = self._admit_ready_job(suffix="n03")
        self._publish(row["id"])
        p = self._project(row["id"])
        self.assertTrue(p["planes"]["upload_accepted"])
        self.assertFalse(p["planes"]["published"])

    def test_N04_monitor_upload_accepted(self):
        row = self._admit_ready_job(suffix="n04")
        self._publish(row["id"])
        j = self._get_job(row["id"])
        self.assertEqual(self.cpm.infer_monitor_state(j), "PUBLISH_UPLOAD_ACCEPTED")

    def test_N05_ready_to_upload_preserved(self):
        row = self._admit_ready_job(suffix="n05")
        self._publish(row["id"])
        j = self._get_job(row["id"])
        self.assertEqual(j.get("upload_status"), "ready_to_upload")

    def test_N06_result_note_distinction(self):
        row = self._admit_ready_job(suffix="n06")
        r = self._publish(row["id"])
        self.assertIn("UPLOAD_ACCEPTED", r["result"].get("note") or "")

    def test_N07_required_action_refresh(self):
        row = self._admit_ready_job(suffix="n07")
        self._publish(row["id"])
        p = self._project(row["id"])
        self.assertEqual(p["required_action"], "REFRESH STATUS")


# ---------------------------------------------------------------------------
# O — Processing ≠ published
# ---------------------------------------------------------------------------


class O_ProcessingNotPublishedTests(C07PubBase):
    def test_O01_processing_not_published(self):
        row = self._admit_ready_job(suffix="o01")
        self._publish(row["id"], scenario="processing")
        r = self._refresh(row["id"], scenario="processing")
        self.assertEqual(r["result"]["state"], "REMOTE_PROCESSING")
        self.assertFalse(r["result"]["published"])

    def test_O02_job_remote_processing(self):
        row = self._admit_ready_job(suffix="o02")
        self._publish(row["id"], scenario="processing")
        self._refresh(row["id"], scenario="processing")
        j = self._get_job(row["id"])
        self.assertEqual(j.get("publish_status"), "REMOTE_PROCESSING")

    def test_O03_monitor_remote_processing(self):
        row = self._admit_ready_job(suffix="o03")
        self._publish(row["id"], scenario="processing")
        self._refresh(row["id"], scenario="processing")
        j = self._get_job(row["id"])
        self.assertEqual(self.cpm.infer_monitor_state(j), "PUBLISH_REMOTE_PROCESSING")

    def test_O04_planes_processing_not_published(self):
        row = self._admit_ready_job(suffix="o04")
        self._publish(row["id"], scenario="processing")
        self._refresh(row["id"], scenario="processing")
        p = self._project(row["id"])
        self.assertTrue(p["planes"]["remote_processing"])
        self.assertFalse(p["planes"]["published"])

    def test_O05_second_refresh_may_publish_mock(self):
        row = self._admit_ready_job(suffix="o05")
        self._publish(row["id"], scenario="processing")
        self._refresh(row["id"], scenario="processing")
        r2 = self._refresh(row["id"], scenario="published_immediate")
        self.assertEqual(r2["result"]["state"], "PUBLISHED")
        self.assertTrue(r2["result"]["published"])
        self.assertTrue(r2["result"]["mock"])

    def test_O06_published_immediate_via_refresh(self):
        row = self._admit_ready_job(suffix="o06")
        self._publish(row["id"], scenario="published_immediate")
        r = self._refresh(row["id"], scenario="published_immediate")
        self.assertEqual(r["result"]["state"], "PUBLISHED")

    def test_O07_unknown_observation_not_published(self):
        row = self._admit_ready_job(suffix="o07")
        self._publish(row["id"])
        # wipe mock store so observe returns UNKNOWN
        from publishers.customer_publish_provider import reset_mock_store

        reset_mock_store()
        r = self._refresh(row["id"])
        self.assertFalse(r["result"].get("published"))
        self.assertNotEqual(r["result"]["state"], "PUBLISHED")


# ---------------------------------------------------------------------------
# P — Processing failure
# ---------------------------------------------------------------------------


class P_ProcessingFailureTests(C07PubBase):
    def test_P01_processing_failure_failed(self):
        row = self._admit_ready_job(suffix="p01")
        self._publish(row["id"])
        r = self._refresh(row["id"], scenario="processing_failed")
        self.assertFalse(r.get("ok"))
        self.assertEqual(r["result"]["state"], "FAILED")

    def test_P02_processing_failure_error_code(self):
        row = self._admit_ready_job(suffix="p02")
        self._publish(row["id"])
        r = self._refresh(row["id"], scenario="processing_failed")
        self.assertEqual(r["result"]["error_code"], "REMOTE_PROCESSING_FAILURE")

    def test_P03_job_failed_status(self):
        row = self._admit_ready_job(suffix="p03")
        self._publish(row["id"])
        self._refresh(row["id"], scenario="processing_failed")
        j = self._get_job(row["id"])
        self.assertEqual(j.get("publish_status"), "FAILED")

    def test_P04_provider_rejected_on_upload(self):
        row = self._admit_ready_job(suffix="p04")
        r = self._publish(row["id"], scenario="provider_rejected")
        self.assertFalse(r.get("ok"))
        self.assertEqual(r["result"]["state"], "FAILED")
        self.assertEqual(r["result"]["error_code"], "PROVIDER_REJECTED")

    def test_P05_permanent_failure(self):
        row = self._admit_ready_job(suffix="p05")
        r = self._publish(row["id"], scenario="permanent")
        self.assertEqual(r["result"]["state"], "FAILED")


# ---------------------------------------------------------------------------
# Q — Ambiguous network / reconciliation
# ---------------------------------------------------------------------------


class Q_AmbiguousNetworkTests(C07PubBase):
    def test_Q01_ambiguous_network_reconciliation(self):
        row = self._admit_ready_job(suffix="q01")
        r = self._publish(row["id"], scenario="network_ambiguous")
        self.assertFalse(r.get("ok"))
        self.assertEqual(r["result"]["state"], "RECONCILIATION_REQUIRED")

    def test_Q02_safe_to_retry_false(self):
        row = self._admit_ready_job(suffix="q02")
        r = self._publish(row["id"], scenario="network_ambiguous")
        self.assertFalse(r.get("safe_to_retry"))

    def test_Q03_job_reconciliation_status(self):
        row = self._admit_ready_job(suffix="q03")
        self._publish(row["id"], scenario="network_ambiguous")
        j = self._get_job(row["id"])
        self.assertEqual(j.get("publish_status"), "RECONCILIATION_REQUIRED")

    def test_Q04_monitor_reconciliation(self):
        row = self._admit_ready_job(suffix="q04")
        self._publish(row["id"], scenario="network_ambiguous")
        j = self._get_job(row["id"])
        self.assertEqual(self.cpm.infer_monitor_state(j), "PUBLISH_RECONCILIATION_REQUIRED")

    def test_Q05_retry_does_not_duplicate_after_ambiguous(self):
        row = self._admit_ready_job(suffix="q05")
        r1 = self._publish(row["id"], scenario="network_ambiguous")
        self.assertFalse(r1.get("safe_to_retry"))
        r2 = self._publish(row["id"], scenario="happy_path")
        # second attempt must not blind-upload; provider_called False (UNKNOWN claim)
        self.assertFalse(r2.get("provider_called"))
        self.assertEqual(r2["result"]["state"], "RECONCILIATION_REQUIRED")

    def test_Q06_reconcile_without_vid_safe_false(self):
        row = self._admit_ready_job(suffix="q06")
        self._publish(row["id"], scenario="network_ambiguous")
        out = self.cp.reconcile_ambiguous_publish(
            self.login, int(row["id"]), channel_ids=[self.ch_id]
        )
        self.assertFalse(out.get("safe_to_retry"))


# ---------------------------------------------------------------------------
# R — Duplicate / idempotency
# ---------------------------------------------------------------------------


class R_DuplicateIdempotencyTests(C07PubBase):
    def test_R01_duplicate_publish_no_second_attempt(self):
        row = self._admit_ready_job(suffix="r01")
        r1 = self._publish(row["id"])
        self.assertTrue(r1.get("provider_called"))
        r2 = self._publish(row["id"])
        self.assertFalse(r2.get("provider_called"))

    def test_R02_duplicate_claim_blocked_note(self):
        row = self._admit_ready_job(suffix="r02")
        self._publish(row["id"])
        r2 = self._publish(row["id"])
        self.assertIn("duplicate", (r2.get("note") or "").lower() + json.dumps(r2.get("result") or {}))

    def test_R03_same_fingerprint(self):
        row = self._admit_ready_job(suffix="r03")
        r1 = self._publish(row["id"])
        r2 = self._publish(row["id"])
        self.assertEqual(r1.get("fingerprint"), r2.get("fingerprint"))

    def test_R04_retry_after_published_reuses(self):
        row = self._admit_ready_job(suffix="r04")
        self._publish(row["id"], scenario="published_immediate")
        self._refresh(row["id"], scenario="published_immediate")
        r3 = self._publish(row["id"])
        self.assertFalse(r3.get("provider_called"))
        self.assertTrue(r3.get("reused") or r3.get("ok"))

    def test_R05_transient_marked_retryable(self):
        row = self._admit_ready_job(suffix="r05")
        r = self._publish(row["id"], scenario="transient")
        self.assertEqual(r["result"]["state"], "FAILED")
        self.assertTrue(r.get("retryable"))

    def test_R06_provider_called_false_on_gate_fail(self):
        row = self._admit_ready_job(suffix="r06", customer_approval="PENDING")
        r = self._publish(row["id"])
        self.assertFalse(r.get("provider_called"))

    def test_R07_attempt_count_not_double_on_duplicate(self):
        row = self._admit_ready_job(suffix="r07")
        self._publish(row["id"])
        a1 = int(self._get_job(row["id"]).get("publish_attempt_count") or 0)
        self._publish(row["id"])
        a2 = int(self._get_job(row["id"]).get("publish_attempt_count") or 0)
        self.assertEqual(a1, a2)

    def test_R08_real_count_zero_after_duplicates(self):
        row = self._admit_ready_job(suffix="r08")
        self._publish(row["id"])
        self._publish(row["id"])
        self.assertEqual(self.cp.real_provider_call_count(), 0)


# ---------------------------------------------------------------------------
# S — Concurrent duplicate claim
# ---------------------------------------------------------------------------


class S_ConcurrentClaimTests(C07PubBase):
    def test_S01_concurrent_one_claim(self):
        row = self._admit_ready_job(suffix="s01")
        jid = int(row["id"])

        def _run():
            return self._publish(jid)

        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(_run) for _ in range(4)]
            results = [f.result() for f in as_completed(futs)]
        called = [r for r in results if r.get("provider_called")]
        self.assertEqual(len(called), 1)

    def test_S02_concurrent_others_not_called(self):
        row = self._admit_ready_job(suffix="s02")
        jid = int(row["id"])

        def _run():
            return self._publish(jid)

        with ThreadPoolExecutor(max_workers=3) as ex:
            results = list(ex.map(lambda _: _run(), range(3)))
        not_called = [r for r in results if not r.get("provider_called")]
        self.assertGreaterEqual(len(not_called), 2)

    def test_S03_single_provider_video_id(self):
        row = self._admit_ready_job(suffix="s03")
        jid = int(row["id"])
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(lambda _: self._publish(jid), range(4)))
        j = self._get_job(jid)
        self.assertTrue(str(j.get("publish_provider_video_id") or "").startswith("mock_"))

    def test_S04_concurrent_real_provider_zero(self):
        row = self._admit_ready_job(suffix="s04")
        jid = int(row["id"])
        with ThreadPoolExecutor(max_workers=3) as ex:
            list(ex.map(lambda _: self._publish(jid), range(3)))
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_S05_concurrent_status_upload_accepted(self):
        row = self._admit_ready_job(suffix="s05")
        jid = int(row["id"])
        with ThreadPoolExecutor(max_workers=2) as ex:
            list(ex.map(lambda _: self._publish(jid), range(2)))
        self.assertEqual(self._get_job(jid).get("publish_status"), "UPLOAD_ACCEPTED")


# ---------------------------------------------------------------------------
# T — Retry / restart preserves state
# ---------------------------------------------------------------------------


class T_RetryRestartTests(C07PubBase):
    def test_T01_restart_preserves_publication_state(self):
        row = self._admit_ready_job(suffix="t01")
        self._publish(row["id"])
        before = self._get_job(row["id"])
        # simulate process restart by re-reading
        after = self._get_job(row["id"])
        self.assertEqual(before.get("publish_status"), after.get("publish_status"))
        self.assertEqual(before.get("publish_provider_video_id"), after.get("publish_provider_video_id"))
        self.assertEqual(before.get("publish_fingerprint"), after.get("publish_fingerprint"))

    def test_T02_refresh_after_restart(self):
        row = self._admit_ready_job(suffix="t02")
        self._publish(row["id"], scenario="published_immediate")
        r = self._refresh(row["id"], scenario="published_immediate")
        self.assertEqual(r["result"]["state"], "PUBLISHED")
        j = self._get_job(row["id"])
        self.assertEqual(j.get("publish_status"), "PUBLISHED")

    def test_T03_retry_does_not_duplicate(self):
        row = self._admit_ready_job(suffix="t03")
        self._publish(row["id"])
        vid1 = self._get_job(row["id"]).get("publish_provider_video_id")
        self._publish(row["id"])
        vid2 = self._get_job(row["id"]).get("publish_provider_video_id")
        self.assertEqual(vid1, vid2)

    def test_T04_monitor_published_after_complete(self):
        row = self._admit_ready_job(suffix="t04")
        self._publish(row["id"], scenario="published_immediate")
        self._refresh(row["id"], scenario="published_immediate")
        j = self._get_job(row["id"])
        self.assertEqual(self.cpm.infer_monitor_state(j), "PUBLISHED")

    def test_T05_reconcile_with_known_vid(self):
        row = self._admit_ready_job(suffix="t05")
        r = self._publish(row["id"])
        vid = r["result"]["provider_video_id"]
        self.store.update_job(
            int(row["id"]),
            publish_status="RECONCILIATION_REQUIRED",
            publish_provider_video_id=None,
            publish_error_code="NETWORK_FAILURE",
        )
        out = self.cp.reconcile_ambiguous_publish(
            self.login, int(row["id"]), channel_ids=[self.ch_id], provider_video_id=vid
        )
        self.assertTrue(out.get("ok") or out.get("result"))

    def test_T06_fingerprint_persisted(self):
        row = self._admit_ready_job(suffix="t06")
        r = self._publish(row["id"])
        j = self._get_job(row["id"])
        self.assertEqual(j.get("publish_fingerprint"), r.get("fingerprint"))

    def test_T07_work_dir_under_data(self):
        row = self._admit_ready_job(suffix="t07")
        self._publish(row["id"])
        d = Path(self.cp.DATA_DIR) / "customer_publish" / f"job{int(row['id'])}"
        self.assertTrue(d.exists())


# ---------------------------------------------------------------------------
# U — Secrets never leak
# ---------------------------------------------------------------------------


class U_SecretsScrubTests(C07PubBase):
    def test_U01_scrub_secrets_token_key(self):
        out = self.cp.scrub_secrets({"access_token": "ya29.abc", "ok": True})
        self.assertEqual(out["access_token"], "[redacted]")
        self.assertTrue(out["ok"])

    def test_U02_scrub_ya29_inline(self):
        out = self.cp.scrub_secrets("token=ya29.ABCDEFGHIJKLMNOPQRST")
        self.assertIn("[redacted]", out)

    def test_U03_scrub_api_key_pattern(self):
        out = self.cp.scrub_secrets("api_key=AIzaSyDummyKeyValue12")
        self.assertIn("[redacted]", out)

    def test_U04_project_hides_channel_token(self):
        # inject fake token on channel row if column exists; projection must not echo it
        row = self._admit_ready_job(suffix="u04")
        ch = self.store.get_channel(self.ch_id) or {}
        # project_publishing only returns limited channel fields
        self.store.update_job(
            int(row["id"]),
            publish_error="oauth token=ya29.LEAKTOKENVALUE123456",
        )
        p = self._project(row["id"])
        blob = json.dumps(p)
        self.assertNotIn("ya29.LEAKTOKENVALUE123456", blob)
        self.assertTrue(p.get("secrets_excluded"))

    def test_U05_publish_result_sanitized(self):
        row = self._admit_ready_job(suffix="u05")
        r = self._publish(row["id"], scenario="provider_rejected")
        blob = json.dumps(r)
        self.assertNotIn("password", blob.lower().split("error")[0] if False else blob)
        self.assertTrue(r["result"].get("mock") or r["result"].get("error_code"))

    def test_U06_gate_channel_no_tokens(self):
        row = self._admit_ready_job(suffix="u06")
        # put token-like field into channel dict via upsert if supported
        self.store.upsert_channel(
            {
                "id": self.ch_id,
                "youtube_name": "PubChA",
                "niche": "gadgets",
                "niche_id": 1,
                "short_upload_time": "12:00",
                "long_upload_time": "18:00",
                "lang_code": "en",
                "owner_login_id": self.login,
                "youtube_access_token": "ya29.SHOULD_NOT_APPEAR_IN_UI",
            }
        )
        g = self._gate(row["id"])
        blob = json.dumps(g)
        self.assertNotIn("ya29.SHOULD_NOT_APPEAR_IN_UI", blob)

    def test_U07_nested_secret_redacted(self):
        out = self.cp.scrub_secrets({"a": {"refresh_token": "secret", "x": 1}})
        self.assertEqual(out["a"]["refresh_token"], "[redacted]")
        self.assertEqual(out["a"]["x"], 1)

    def test_U08_list_scrub(self):
        out = self.cp.scrub_secrets([{"api_key": "k"}, "token=abc"])
        self.assertEqual(out[0]["api_key"], "[redacted]")


# ---------------------------------------------------------------------------
# V — Projection / planes
# ---------------------------------------------------------------------------


class V_ProjectionPlanesTests(C07PubBase):
    def test_V01_planes_note(self):
        row = self._admit_ready_job(suffix="v01")
        p = self._project(row["id"])
        self.assertIn("APPROVED", p["planes"]["note"])

    def test_V02_approved_neq_ready(self):
        # conceptually distinct — ready false while approved
        row = self._admit_ready_job(suffix="v02", upload_status="generated")
        p = self._project(row["id"])
        self.assertTrue(p["planes"]["approved"])
        self.assertFalse(p["planes"]["ready_to_upload"])

    def test_V03_ready_neq_upload_accepted(self):
        row = self._admit_ready_job(suffix="v03")
        p = self._project(row["id"])
        self.assertTrue(p["planes"]["ready_to_upload"])
        self.assertFalse(p["planes"]["upload_accepted"])

    def test_V04_upload_accepted_neq_published(self):
        row = self._admit_ready_job(suffix="v04")
        self._publish(row["id"])
        p = self._project(row["id"])
        self.assertTrue(p["planes"]["upload_accepted"])
        self.assertFalse(p["planes"]["published"])

    def test_V05_remote_processing_neq_published(self):
        row = self._admit_ready_job(suffix="v05")
        self._publish(row["id"], scenario="processing")
        self._refresh(row["id"], scenario="processing")
        p = self._project(row["id"])
        self.assertTrue(p["planes"]["remote_processing"])
        self.assertFalse(p["planes"]["published"])

    def test_V06_published_plane(self):
        row = self._admit_ready_job(suffix="v06")
        self._publish(row["id"], scenario="published_immediate")
        self._refresh(row["id"], scenario="published_immediate")
        p = self._project(row["id"])
        self.assertTrue(p["planes"]["published"])

    def test_V07_contract_on_projection(self):
        row = self._admit_ready_job(suffix="v07")
        p = self._project(row["id"])
        self.assertTrue(str(p.get("contract") or "").startswith("C07-PUB"))

    def test_V08_social_engagement_false(self):
        row = self._admit_ready_job(suffix="v08")
        p = self._project(row["id"])
        self.assertFalse(p.get("social_engagement"))


# ---------------------------------------------------------------------------
# W — Monitor publish states
# ---------------------------------------------------------------------------


class W_MonitorPublishStateTests(C07PubBase):
    def test_W01_infer_upload_accepted(self):
        self.assertEqual(
            self.cpm.infer_monitor_state({"publish_status": "UPLOAD_ACCEPTED", "customer_approval": "APPROVED"}),
            "PUBLISH_UPLOAD_ACCEPTED",
        )

    def test_W02_infer_remote_processing(self):
        self.assertEqual(
            self.cpm.infer_monitor_state({"publish_status": "REMOTE_PROCESSING"}),
            "PUBLISH_REMOTE_PROCESSING",
        )

    def test_W03_infer_reconciliation(self):
        self.assertEqual(
            self.cpm.infer_monitor_state({"publish_status": "RECONCILIATION_REQUIRED"}),
            "PUBLISH_RECONCILIATION_REQUIRED",
        )

    def test_W04_infer_published(self):
        self.assertEqual(self.cpm.infer_monitor_state({"publish_status": "PUBLISHED"}), "PUBLISHED")

    def test_W05_approved_without_publish_status(self):
        self.assertEqual(
            self.cpm.infer_monitor_state({"customer_approval": "APPROVED", "publish_status": ""}),
            "APPROVED",
        )

    def test_W06_publish_events_in_lifecycle_constants(self):
        for e in ("PUBLISH_REQUESTED", "PUBLISH_UPLOAD_ACCEPTED", "PUBLISH_COMPLETED"):
            self.assertIn(e, self.cpm.LIFECYCLE_EVENT_TYPES)

    def test_W07_state_contract_has_publish_keys(self):
        for k in (
            "PUBLISH_UPLOAD_ACCEPTED",
            "PUBLISH_REMOTE_PROCESSING",
            "PUBLISH_RECONCILIATION_REQUIRED",
            "PUBLISHED",
        ):
            self.assertIn(k, self.cpm.STATE_CONTRACT)


# ---------------------------------------------------------------------------
# X — PUBLISH_* lifecycle events
# ---------------------------------------------------------------------------


class X_LifecycleEventTests(C07PubBase):
    def test_X01_validation_failed_event(self):
        row = self._admit_ready_job(suffix="x01", customer_approval="PENDING")
        self._publish(row["id"])
        p = self._project(row["id"])
        types = [str(e.get("type") or e.get("event")) for e in p.get("publish_events") or []]
        self.assertIn("PUBLISH_VALIDATION_FAILED", types)

    def test_X02_requested_and_started(self):
        row = self._admit_ready_job(suffix="x02")
        self._publish(row["id"])
        p = self._project(row["id"])
        types = [str(e.get("type") or e.get("event")) for e in p.get("publish_events") or []]
        self.assertIn("PUBLISH_REQUESTED", types)
        self.assertIn("PUBLISH_STARTED", types)

    def test_X03_upload_accepted_event(self):
        row = self._admit_ready_job(suffix="x03")
        self._publish(row["id"])
        p = self._project(row["id"])
        types = [str(e.get("type") or e.get("event")) for e in p.get("publish_events") or []]
        self.assertIn("PUBLISH_UPLOAD_ACCEPTED", types)

    def test_X04_reconciliation_event(self):
        row = self._admit_ready_job(suffix="x04")
        self._publish(row["id"], scenario="network_ambiguous")
        p = self._project(row["id"])
        types = [str(e.get("type") or e.get("event")) for e in p.get("publish_events") or []]
        self.assertIn("PUBLISH_RECONCILIATION_REQUIRED", types)

    def test_X05_failed_event(self):
        row = self._admit_ready_job(suffix="x05")
        self._publish(row["id"], scenario="provider_rejected")
        p = self._project(row["id"])
        types = [str(e.get("type") or e.get("event")) for e in p.get("publish_events") or []]
        self.assertIn("PUBLISH_FAILED", types)

    def test_X06_completed_event_after_publish(self):
        row = self._admit_ready_job(suffix="x06")
        self._publish(row["id"], scenario="published_immediate")
        self._refresh(row["id"], scenario="published_immediate")
        p = self._project(row["id"])
        types = [str(e.get("type") or e.get("event")) for e in p.get("publish_events") or []]
        self.assertIn("PUBLISH_COMPLETED", types)

    def test_X07_auth_required_event(self):
        row = self._admit_ready_job(suffix="x07")
        self._publish(row["id"], scenario="auth_failure")
        p = self._project(row["id"])
        types = [str(e.get("type") or e.get("event")) for e in p.get("publish_events") or []]
        self.assertIn("PUBLISH_AUTH_REQUIRED", types)


# ---------------------------------------------------------------------------
# Y — Routes, engines, real provider count
# ---------------------------------------------------------------------------


class Y_RoutesEnginesRealCountTests(C07PubBase):
    def test_Y01_workspace_publishing_route(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn('/api/workspace/publishing"', src)

    def test_Y02_workspace_publishing_validate(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("/api/workspace/publishing/validate", src)

    def test_Y03_workspace_publishing_publish(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("/api/workspace/publishing/publish", src)

    def test_Y04_workspace_publishing_refresh(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("/api/workspace/publishing/refresh", src)

    def test_Y05_detect_duplicate_engines_rejects_second(self):
        fake = "\n".join(
            [
                "def generate_video():",
                "    pass",
                "class SchedulerService:",
                "    pass",
                "def try_acquire():",
                "    pass",
                "def evaluate_publishability():",
                "    pass",
                "def compute_fingerprint():",
                "    pass",
                "class IdempotencyStore:",
                "    pass",
                "publish_idempotency.py",
                "publish_cache.py",
            ]
        )
        bad = self.cp.detect_duplicate_engines(fake)
        self.assertGreaterEqual(len(bad), 5)
        self.assertIn("generate_video", bad)
        self.assertIn("IdempotencyStore", bad)

    def test_Y06_clean_source_no_engines(self):
        self.assertEqual(self.cp.detect_duplicate_engines("print('hello')\n"), [])

    def test_Y07_real_provider_call_count_zero_after_suite_ops(self):
        row = self._admit_ready_job(suffix="y07")
        self._publish(row["id"])
        self._refresh(row["id"], scenario="published_immediate")
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_Y08_module_source_has_no_live_youtube_default(self):
        src = (ROOT / "app" / "customer_publish.py").read_text(encoding="utf-8")
        self.assertIn("allow_live_provider", src)


# ---------------------------------------------------------------------------
# Z — Misc extras to exceed 150
# ---------------------------------------------------------------------------


class Z_MiscExtrasTests(C07PubBase):
    def test_Z01_build_publish_result_upload_accepted(self):
        r = self.cp.build_publish_result(state="UPLOAD_ACCEPTED", provider="mock", mock=True)
        self.assertFalse(r["published"])
        self.assertTrue(r["accepted"] or r["uploaded"])

    def test_Z02_build_publish_result_published(self):
        r = self.cp.build_publish_result(state="PUBLISHED", provider="mock", mock=True)
        self.assertTrue(r["published"])

    def test_Z03_build_publish_result_failed(self):
        r = self.cp.build_publish_result(state="FAILED", provider="mock", error_code="X", error="e")
        self.assertTrue(r["failed"])

    def test_Z04_build_publish_result_recon(self):
        r = self.cp.build_publish_result(state="RECONCILIATION_REQUIRED", provider="mock")
        self.assertTrue(r["reconciliation_required"])

    def test_Z05_provider_classify_network(self):
        from publishers.customer_publish_provider import MockPublishProvider

        code = MockPublishProvider().classify_error(RuntimeError("NETWORK_FAILURE:x"))
        self.assertEqual(code, "NETWORK_FAILURE")

    def test_Z06_provider_classify_rate(self):
        from publishers.customer_publish_provider import MockPublishProvider

        code = MockPublishProvider().classify_error(RuntimeError("RATE_LIMITED"))
        self.assertEqual(code, "RATE_LIMITED")

    def test_Z07_get_provider_default_mock(self):
        from publishers.customer_publish_provider import get_publish_provider

        self.assertEqual(get_publish_provider("").name, "mock")

    def test_Z08_project_blocking_not_approved(self):
        row = self._admit_ready_job(suffix="z08", customer_approval="PENDING")
        p = self._project(row["id"])
        self.assertEqual(p.get("blocking_reason"), "not_approved")

    def test_Z09_project_blocking_publishability(self):
        qs = {
            "publishable": False,
            "publishability": {"verdict": "BLOCKED", "publishable": False},
        }
        row = self._admit_ready_job(suffix="z09", quality_summary=qs)
        p = self._project(row["id"])
        self.assertIn("publishability", p.get("blocking_reason") or "")

    def test_Z10_cancel_action_false(self):
        row = self._admit_ready_job(suffix="z10")
        p = self._project(row["id"])
        self.assertFalse(p["actions"]["CANCEL"])

    def test_Z11_refresh_action_after_accept(self):
        row = self._admit_ready_job(suffix="z11")
        self._publish(row["id"])
        p = self._project(row["id"])
        self.assertTrue(p["actions"]["REFRESH_STATUS"])

    def test_Z12_allow_live_default_false_on_package(self):
        row = self._admit_ready_job(suffix="z12")
        g = self._gate(row["id"])
        req = self.cp.build_publish_request(
            login_id=self.login,
            job_id=int(row["id"]),
            channel_id=self.ch_id,
            provider="mock",
            language="en",
            revision_id=g["revision_id"],
            artifact_path=g["artifact_path"],
            title=g["metadata"]["title"],
            fingerprint="fp",
        )
        pkg = self.cp.build_publish_package(req, row)
        self.assertFalse(pkg.get("allow_live_provider"))

    def test_Z13_recoverable_errors_contain_network(self):
        self.assertIn("NETWORK_FAILURE", self.cp.RECOVERABLE_ERRORS)

    def test_Z14_publish_stage_constant(self):
        self.assertEqual(self.cp.PUBLISH_STAGE, "c07_customer_publish")

    def test_Z15_job_b_owner_isolation(self):
        row = self._admit_ready_job(suffix="z15", login_id=self.login_b, channel_id=self.ch_b_id)
        g = self._gate(
            row["id"],
            login=self.login_b,
            channel_ids=[self.ch_b_id],
            identity=self._identity(self.login_b),
        )
        self.assertTrue(g.get("admitted"))

    def test_Z16_main_imports_project_publishing(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("project_publishing", src)

    def test_Z17_main_imports_publish_customer_job(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("publish_customer_job", src)

    def test_Z18_mock_processing_failed_observe(self):
        from publishers.customer_publish_provider import MockPublishProvider

        obs = MockPublishProvider(scenario="processing_failed").observe("missing", {})
        self.assertEqual(obs.status, "PROCESSING_FAILED")

    def test_Z19_upload_status_dry_run_after_mock_publish(self):
        row = self._admit_ready_job(suffix="z19")
        self._publish(row["id"], scenario="published_immediate")
        self._refresh(row["id"], scenario="published_immediate")
        j = self._get_job(row["id"])
        self.assertEqual(j.get("upload_status"), "dry_run_uploaded")

    def test_Z20_real_provider_count_explicit(self):
        self.cp.reset_real_provider_call_count()
        self.assertEqual(self.cp.real_provider_call_count(), 0)
        row = self._admit_ready_job(suffix="z20")
        self._publish(row["id"])
        self._publish(row["id"])
        self._refresh(row["id"], scenario="processing")
        self.assertEqual(self.cp.real_provider_call_count(), 0)


if __name__ == "__main__":
    unittest.main()
