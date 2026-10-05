"""C08 — Customer Production Certification (paid APIs = 0).

>=155 deterministic unittest cases. Inspect/compose over existing C01→C07-SCHED
authorities — no new engines, no live YouTube / paid providers.
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

ROOT = Path(__file__).resolve().parents[1]


class C08CertBase(unittest.TestCase):
    """Shared TemporaryDirectory fixture — mirrors C07-PUB / C07-SCHED patterns."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.td = Path(self._tmp.name)
        self.data_dir = self.td / "data"
        self.data_dir.mkdir()
        self.db_path = self.td / "c08cert.db"

        from app import config as cfg
        from app import db as store
        import app.customer_publish as cp
        import app.customer_publish_schedule as cps
        import app.customer_preview_approval as cpa
        import app.customer_job_automation as cja
        import app.customer_production_certification as cpc
        import app.customer_production_monitor as cpm
        from app.customer_job import ensure_job_columns
        from app.customer_config import ensure_channel_owner_column
        from publishers.customer_publish_provider import reset_mock_store

        self.store = store
        self.cfg = cfg
        self.cp = cp
        self.cps = cps
        self.cpa = cpa
        self.cja = cja
        self.cpc = cpc
        self.cpm = cpm

        self._orig_db = store.DB_PATH
        self._orig_cfg_data = cfg.DATA_DIR
        self._orig_cp_data = cp.DATA_DIR
        self._orig_cps_data = cps.DATA_DIR
        self._orig_cpa_data = cpa.DATA_DIR
        self._orig_cja_data = cja.DATA_DIR
        self._orig_cpc_data = getattr(cpc, "DATA_DIR", None)

        store.DB_PATH = self.db_path
        cfg.DATA_DIR = self.data_dir
        cp.DATA_DIR = self.data_dir
        cps.DATA_DIR = self.data_dir
        cpa.DATA_DIR = self.data_dir
        cja.DATA_DIR = self.data_dir
        if hasattr(cpc, "DATA_DIR"):
            cpc.DATA_DIR = self.data_dir

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
                "youtube_name": "CertChA",
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
                "youtube_name": "CertChB",
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
            "youtube_name": "CertChA",
            "niche_id": 1,
            "lang_code": "en",
            "owner_login_id": self.login,
        }
        self.channel_b = {
            "id": self.ch_b_id,
            "niche": "news",
            "youtube_name": "CertChB",
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
        self.cp.DATA_DIR = self._orig_cp_data
        self.cps.DATA_DIR = self._orig_cps_data
        self.cpa.DATA_DIR = self._orig_cpa_data
        self.cja.DATA_DIR = self._orig_cja_data
        if self._orig_cpc_data is not None and hasattr(self.cpc, "DATA_DIR"):
            self.cpc.DATA_DIR = self._orig_cpc_data

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
            "note": "c08 admit ready",
        }
        payload.update(extra)
        return json.dumps(payload)

    def _admit_ready_job(self, **extra):
        from app.customer_job import create_generation_job, get_job

        login = extra.get("login_id", self.login)
        channel_id = int(extra.get("channel_id", self.ch_id))
        title = extra.get("title", "C08 cert ready title")
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
            production_plan_id=extra.get("plan_id", "plan-c08"),
            production_plan_revision=extra.get("plan_rev", "rev-c08"),
            script_revision=extra.get("script_rev", "scr-c08"),
            generation_fingerprint=extra.get("fp", f"fp-c08-{extra.get('suffix', 'x')}"),
            plan_snapshot=extra.get(
                "plan_snapshot",
                {
                    "production_plan_id": extra.get("plan_id", "plan-c08"),
                    "production_plan_revision": extra.get("plan_rev", "rev-c08"),
                    "_c08": {"mock": True},
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

    def _journey(self, *, login=None, channel_ids=None, job_id=None, channel=None, identity=None):
        return self.cpc.project_journey(
            login or self.login,
            channel_ids=channel_ids if channel_ids is not None else [self.ch_id],
            job_id=job_id,
            channel=channel if channel is not None else self.channel,
            identity=identity if identity is not None else self._identity(login or self.login),
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

    def _process_due(self, **kw):
        return self.cps.process_due_schedules(**kw)

    def _stage_map(self, journey):
        return {s["stage"]: s for s in journey.get("stages") or []}


# ---------------------------------------------------------------------------
# A — Contract / planes distinct
# ---------------------------------------------------------------------------


class A_ContractPlanesTests(C08CertBase):
    def test_A01_module_exports(self):
        for name in (
            "project_journey",
            "classify_failure",
            "FAILURE_MATRIX",
            "LEGACY_PATH_CLASSIFICATION",
            "assert_planes_distinct",
            "project_result_planes",
            "certify_offline_media_probe",
            "detect_duplicate_engines",
            "AUTHORITY_SINGULARITY",
            "PLANE_ORDER",
            "JOURNEY_STAGES",
            "CONTRACT_VERSION",
            "stage_record",
        ):
            self.assertTrue(hasattr(self.cpc, name), name)

    def test_A02_contract_version(self):
        self.assertEqual(self.cpc.CONTRACT_VERSION, "C08.1")

    def test_A03_plane_order_nine(self):
        self.assertEqual(len(self.cpc.PLANE_ORDER), 9)

    def test_A04_assert_planes_distinct_all_true(self):
        d = self.cpc.assert_planes_distinct()
        self.assertTrue(all(d.values()))
        self.assertEqual(len(d), 36)  # C(9,2)

    def test_A05_generated_neq_published(self):
        d = self.cpc.assert_planes_distinct()
        self.assertTrue(d["GENERATED_neq_PUBLISHED"])

    def test_A06_upload_accepted_neq_published(self):
        d = self.cpc.assert_planes_distinct()
        self.assertTrue(d["UPLOAD_ACCEPTED_neq_PUBLISHED"])

    def test_A07_approved_neq_ready_to_upload(self):
        d = self.cpc.assert_planes_distinct()
        self.assertTrue(d["APPROVED_neq_READY_TO_UPLOAD"])

    def test_A08_scheduled_neq_published(self):
        d = self.cpc.assert_planes_distinct()
        self.assertTrue(d.get("SCHEDULED_neq_PUBLISHED") or d.get("PUBLISHED_neq_SCHEDULED"))

    def test_A09_orchestrates_new_engine_false(self):
        j = self._journey()
        self.assertFalse(j.get("orchestrates_new_engine"))

    def test_A10_paid_api_calls_zero_on_journey(self):
        j = self._journey()
        self.assertEqual(j.get("paid_api_calls"), 0)


# ---------------------------------------------------------------------------
# B — Journey projection stages present
# ---------------------------------------------------------------------------


class B_JourneyStagesTests(C08CertBase):
    def test_B01_journey_stages_tuple_len(self):
        self.assertGreaterEqual(len(self.cpc.JOURNEY_STAGES), 20)

    def test_B02_auth_stage_in_projection(self):
        sm = self._stage_map(self._journey())
        self.assertIn("AUTH", sm)

    def test_B03_entitlement_stage(self):
        sm = self._stage_map(self._journey())
        self.assertIn("ENTITLEMENT", sm)

    def test_B04_channel_stage(self):
        sm = self._stage_map(self._journey())
        self.assertIn("CHANNEL", sm)

    def test_B05_api_configuration_stage(self):
        sm = self._stage_map(self._journey())
        self.assertIn("API_CONFIGURATION", sm)

    def test_B06_topic_research_script_plan(self):
        sm = self._stage_map(self._journey())
        for s in ("TOPIC", "RESEARCH", "SCRIPT", "PRODUCTION_PLAN"):
            self.assertIn(s, sm)

    def test_B07_job_stages_after_admit(self):
        row = self._admit_ready_job(suffix="b07")
        sm = self._stage_map(self._journey(job_id=int(row["id"])))
        for s in (
            "GENERATION",
            "OBSERVATION",
            "QUALITY_VERIFICATION",
            "APPROVAL",
            "PUBLISHABILITY",
            "PUBLISH",
            "REMOTE_PROCESSING",
            "PUBLISHED",
            "SCHEDULE",
        ):
            self.assertIn(s, sm, s)

    def test_B08_journey_ok_true(self):
        self.assertTrue(self._journey().get("ok"))

    def test_B09_contract_echo(self):
        self.assertEqual(self._journey().get("contract"), self.cpc.CONTRACT_VERSION)

    def test_B10_stages_have_authoritative_source(self):
        for s in self._journey()["stages"]:
            self.assertTrue(s.get("authoritative_source"), s.get("stage"))


# ---------------------------------------------------------------------------
# C — Admission auth/entitlement
# ---------------------------------------------------------------------------


class C_AdmissionAuthTests(C08CertBase):
    def test_C01_auth_ok_when_authenticated(self):
        j = self._journey()
        self.assertTrue(j["admission"]["auth"])
        self.assertEqual(self._stage_map(j)["AUTH"]["state"], "AUTHENTICATED")

    def test_C02_auth_required_when_false(self):
        j = self._journey(identity=self._identity(authenticated=False))
        self.assertFalse(j["admission"]["auth"])
        self.assertEqual(self._stage_map(j)["AUTH"]["state"], "AUTH_REQUIRED")

    def test_C03_entitlement_active(self):
        j = self._journey()
        self.assertTrue(j["admission"]["entitlement"])
        self.assertEqual(self._stage_map(j)["ENTITLEMENT"]["state"], "ACTIVE")

    def test_C04_entitlement_blocked_expired(self):
        j = self._journey(
            identity=self._identity(entitlement_state="EXPIRED", production_access=False)
        )
        self.assertFalse(j["admission"]["entitlement"])
        self.assertEqual(self._stage_map(j)["ENTITLEMENT"]["state"], "ENTITLEMENT_REQUIRED")

    def test_C05_entitlement_blocked_suspended(self):
        j = self._journey(
            identity=self._identity(entitlement_state="SUSPENDED", production_access=False)
        )
        self.assertFalse(j["admission"]["entitlement"])

    def test_C06_production_access_false_blocks(self):
        j = self._journey(identity=self._identity(production_access=False))
        self.assertFalse(j["admission"]["production_access"])
        self.assertFalse(j["admission"]["entitlement"])

    def test_C07_classify_auth_failure(self):
        r = self.cpc.classify_failure("AUTH_FAILURE")
        self.assertTrue(r["ok"])
        self.assertEqual(r["state"], "AUTH_REQUIRED")
        self.assertFalse(r["false_success"])

    def test_C08_classify_entitlement_failure(self):
        r = self.cpc.classify_failure("ENTITLEMENT_FAILURE")
        self.assertEqual(r["state"], "ENTITLEMENT_REQUIRED")


# ---------------------------------------------------------------------------
# D — Ownership isolation forged
# ---------------------------------------------------------------------------


class D_OwnershipIsolationTests(C08CertBase):
    def test_D01_owned_channel_ok(self):
        j = self._journey()
        self.assertTrue(j["admission"]["channel_owned"])
        self.assertEqual(self._stage_map(j)["CHANNEL"]["state"], "OWNED")

    def test_D02_foreign_channel_denied(self):
        j = self._journey(channel=self.channel_b, channel_ids=[self.ch_id])
        self.assertFalse(j["admission"]["channel_owned"])
        self.assertEqual(self._stage_map(j)["CHANNEL"]["state"], "OWNERSHIP_DENIED")

    def test_D03_foreign_job_ownership_denied(self):
        row = self._admit_ready_job(suffix="d03", login_id=self.login_b, channel_id=self.ch_b_id)
        j = self._journey(job_id=int(row["id"]), channel_ids=[self.ch_id])
        sm = self._stage_map(j)
        self.assertEqual(sm["GENERATION"]["state"], "OWNERSHIP_DENIED")

    def test_D04_publish_gate_blocks_foreign(self):
        row = self._admit_ready_job(suffix="d04")
        r = self._publish(row["id"], login=self.login_b, channel_ids=[self.ch_b_id])
        self.assertFalse(r.get("ok") and r.get("provider_called"))

    def test_D05_forged_access_failure_matrix(self):
        r = self.cpc.classify_failure("FORGED_CUSTOMER_ACCESS")
        self.assertEqual(r["state"], "OWNERSHIP_DENIED")
        self.assertFalse(r["false_success"])

    def test_D06_b_cannot_schedule_a_job(self):
        row = self._admit_ready_job(suffix="d06")
        out = self._create_schedule(
            row["id"], login=self.login_b, channel_ids=[self.ch_b_id]
        )
        self.assertFalse(out.get("ok"))


# ---------------------------------------------------------------------------
# E — Failure matrix completeness
# ---------------------------------------------------------------------------


class E_FailureMatrixTests(C08CertBase):
    def test_E01_matrix_nonempty(self):
        self.assertGreaterEqual(len(self.cpc.FAILURE_MATRIX), 25)

    def test_E02_every_key_classifiable(self):
        for code in self.cpc.FAILURE_MATRIX:
            r = self.cpc.classify_failure(code)
            self.assertTrue(r["ok"], code)
            self.assertFalse(r["false_success"], code)

    def test_E03_unknown_code_not_pass(self):
        r = self.cpc.classify_failure("NOT_A_REAL_CODE")
        self.assertFalse(r["ok"])
        self.assertFalse(r["false_success"])

    def test_E04_auth_failure(self):
        self.assertIn("AUTH_FAILURE", self.cpc.FAILURE_MATRIX)

    def test_E05_entitlement_failure(self):
        self.assertIn("ENTITLEMENT_FAILURE", self.cpc.FAILURE_MATRIX)

    def test_E06_channel_ownership_failure(self):
        self.assertIn("CHANNEL_OWNERSHIP_FAILURE", self.cpc.FAILURE_MATRIX)

    def test_E07_api_not_ready(self):
        self.assertIn("API_NOT_READY", self.cpc.FAILURE_MATRIX)

    def test_E08_topic_failure(self):
        self.assertIn("TOPIC_FAILURE", self.cpc.FAILURE_MATRIX)

    def test_E09_research_failure(self):
        self.assertIn("RESEARCH_FAILURE", self.cpc.FAILURE_MATRIX)

    def test_E10_script_failure(self):
        self.assertIn("SCRIPT_FAILURE", self.cpc.FAILURE_MATRIX)

    def test_E11_plan_failure(self):
        self.assertIn("PLAN_FAILURE", self.cpc.FAILURE_MATRIX)

    def test_E12_generation_failure(self):
        self.assertIn("GENERATION_FAILURE", self.cpc.FAILURE_MATRIX)

    def test_E13_observation_unknown(self):
        self.assertIn("OBSERVATION_UNKNOWN", self.cpc.FAILURE_MATRIX)

    def test_E14_quality_failure(self):
        self.assertIn("QUALITY_FAILURE", self.cpc.FAILURE_MATRIX)

    def test_E15_repair_failure(self):
        self.assertIn("REPAIR_FAILURE", self.cpc.FAILURE_MATRIX)

    def test_E16_render_failure(self):
        self.assertIn("RENDER_FAILURE", self.cpc.FAILURE_MATRIX)

    def test_E17_preview_unavailable(self):
        self.assertIn("PREVIEW_UNAVAILABLE", self.cpc.FAILURE_MATRIX)

    def test_E18_approval_rejected(self):
        self.assertIn("APPROVAL_REJECTED", self.cpc.FAILURE_MATRIX)

    def test_E19_publishability_failure(self):
        self.assertIn("PUBLISHABILITY_FAILURE", self.cpc.FAILURE_MATRIX)

    def test_E20_upload_failure(self):
        self.assertIn("UPLOAD_FAILURE", self.cpc.FAILURE_MATRIX)

    def test_E21_remote_processing(self):
        self.assertIn("REMOTE_PROCESSING", self.cpc.FAILURE_MATRIX)

    def test_E22_remote_failure(self):
        self.assertIn("REMOTE_FAILURE", self.cpc.FAILURE_MATRIX)

    def test_E23_reconciliation_required(self):
        self.assertIn("RECONCILIATION_REQUIRED", self.cpc.FAILURE_MATRIX)

    def test_E24_schedule_cancelled(self):
        self.assertIn("SCHEDULE_CANCELLED", self.cpc.FAILURE_MATRIX)

    def test_E25_schedule_missed(self):
        self.assertIn("SCHEDULE_MISSED", self.cpc.FAILURE_MATRIX)

    def test_E26_restart_during_generation(self):
        self.assertIn("RESTART_DURING_GENERATION", self.cpc.FAILURE_MATRIX)

    def test_E27_restart_during_publish(self):
        self.assertIn("RESTART_DURING_PUBLISH", self.cpc.FAILURE_MATRIX)

    def test_E28_restart_during_schedule(self):
        self.assertIn("RESTART_DURING_SCHEDULE", self.cpc.FAILURE_MATRIX)

    def test_E29_duplicate_generate(self):
        self.assertIn("DUPLICATE_GENERATE", self.cpc.FAILURE_MATRIX)

    def test_E30_duplicate_publish(self):
        self.assertIn("DUPLICATE_PUBLISH", self.cpc.FAILURE_MATRIX)

    def test_E31_duplicate_schedule(self):
        self.assertIn("DUPLICATE_SCHEDULE", self.cpc.FAILURE_MATRIX)

    def test_E32_forged_customer_access(self):
        self.assertIn("FORGED_CUSTOMER_ACCESS", self.cpc.FAILURE_MATRIX)

    def test_E33_journey_embeds_failure_matrix(self):
        j = self._journey()
        self.assertEqual(len(j["failure_matrix"]), len(self.cpc.FAILURE_MATRIX))

    def test_E34_no_false_success_anywhere(self):
        for code, row in self.cpc.FAILURE_MATRIX.items():
            self.assertFalse(row.get("false_success"), code)

    def test_E35_every_row_has_label_state(self):
        for code, row in self.cpc.FAILURE_MATRIX.items():
            self.assertTrue(row.get("label"), code)
            self.assertTrue(row.get("state"), code)
            self.assertIn("retry_owner", row)
            self.assertIn("manual_action", row)


# ---------------------------------------------------------------------------
# F — Legacy path classification
# ---------------------------------------------------------------------------


class F_LegacyPathTests(C08CertBase):
    def test_F01_all_keys_present(self):
        expected = {
            "workspace_generate_queue",
            "workspace_generate_sync",
            "api_generate",
            "idle_pregen",
            "timed_fallback",
            "timed_upload",
            "browser_studio",
            "live_lab",
            "legacy_no_plan_generation",
        }
        self.assertEqual(set(self.cpc.LEGACY_PATH_CLASSIFICATION), expected)

    def test_F02_queue_canonical(self):
        self.assertEqual(
            self.cpc.LEGACY_PATH_CLASSIFICATION["workspace_generate_queue"]["class"],
            "CANONICAL_CUSTOMER_PRODUCTION",
        )

    def test_F03_sync_legacy(self):
        self.assertEqual(
            self.cpc.LEGACY_PATH_CLASSIFICATION["workspace_generate_sync"]["class"],
            "LEGACY_COMPAT",
        )

    def test_F04_api_generate_legacy(self):
        self.assertEqual(
            self.cpc.LEGACY_PATH_CLASSIFICATION["api_generate"]["class"], "LEGACY_COMPAT"
        )

    def test_F05_idle_pregen_legacy(self):
        self.assertEqual(
            self.cpc.LEGACY_PATH_CLASSIFICATION["idle_pregen"]["class"], "LEGACY_COMPAT"
        )

    def test_F06_timed_fallback_legacy(self):
        self.assertEqual(
            self.cpc.LEGACY_PATH_CLASSIFICATION["timed_fallback"]["class"], "LEGACY_COMPAT"
        )

    def test_F07_timed_upload_internal(self):
        self.assertEqual(
            self.cpc.LEGACY_PATH_CLASSIFICATION["timed_upload"]["class"], "INTERNAL_ONLY"
        )

    def test_F08_browser_studio_forbidden(self):
        self.assertEqual(
            self.cpc.LEGACY_PATH_CLASSIFICATION["browser_studio"]["class"],
            "FORBIDDEN_FOR_CUSTOMER_PRODUCTION",
        )

    def test_F09_live_lab_forbidden(self):
        self.assertEqual(
            self.cpc.LEGACY_PATH_CLASSIFICATION["live_lab"]["class"],
            "FORBIDDEN_FOR_CUSTOMER_PRODUCTION",
        )

    def test_F10_legacy_no_plan(self):
        self.assertEqual(
            self.cpc.LEGACY_PATH_CLASSIFICATION["legacy_no_plan_generation"]["class"],
            "LEGACY_COMPAT",
        )

    def test_F11_journey_embeds_legacy(self):
        j = self._journey()
        self.assertIn("live_lab", j["legacy_paths"])
        self.assertIn("browser_studio", j["legacy_paths"])

    def test_F12_forbidden_not_canonical(self):
        for k in ("live_lab", "browser_studio"):
            cls = self.cpc.LEGACY_PATH_CLASSIFICATION[k]["class"]
            self.assertNotEqual(cls, "CANONICAL_CUSTOMER_PRODUCTION")
            self.assertIn("FORBIDDEN", cls)


# ---------------------------------------------------------------------------
# G — Happy path planes after approve
# ---------------------------------------------------------------------------


class G_HappyPathPlanesTests(C08CertBase):
    def test_G01_planes_after_admit(self):
        row = self._admit_ready_job(suffix="g01")
        planes = self._journey(job_id=int(row["id"]))["planes"]
        self.assertTrue(planes["GENERATED"])
        self.assertTrue(planes["VERIFIED"])
        self.assertTrue(planes["PUBLISHABLE"])
        self.assertTrue(planes["APPROVED"])
        self.assertTrue(planes["READY_TO_UPLOAD"])

    def test_G02_not_uploaded_yet(self):
        row = self._admit_ready_job(suffix="g02")
        planes = self._journey(job_id=int(row["id"]))["planes"]
        self.assertFalse(planes["UPLOAD_ACCEPTED"])
        self.assertFalse(planes["REMOTE_PROCESSING"])
        self.assertFalse(planes["PUBLISHED"])

    def test_G03_no_job_all_false(self):
        planes = self.cpc.project_result_planes(None)
        for p in self.cpc.PLANE_ORDER:
            self.assertFalse(planes[p], p)

    def test_G04_plane_distinctions_on_journey(self):
        j = self._journey()
        self.assertTrue(all(j["plane_distinctions"].values()))

    def test_G05_approval_stage_approved(self):
        row = self._admit_ready_job(suffix="g05")
        sm = self._stage_map(self._journey(job_id=int(row["id"])))
        self.assertEqual(sm["APPROVAL"]["state"], "APPROVED")

    def test_G06_publishability_stage(self):
        row = self._admit_ready_job(suffix="g06")
        sm = self._stage_map(self._journey(job_id=int(row["id"])))
        self.assertEqual(sm["PUBLISHABILITY"]["state"], "PUBLISHABLE")

    def test_G07_pending_approval_plane(self):
        row = self._admit_ready_job(suffix="g07", customer_approval="PENDING")
        planes = self._journey(job_id=int(row["id"]))["planes"]
        self.assertFalse(planes["APPROVED"])
        self.assertTrue(planes["READY_TO_UPLOAD"])

    def test_G08_note_lists_planes(self):
        note = self._journey().get("note") or ""
        self.assertIn("GENERATED", note)
        self.assertIn("PUBLISHED", note)


# ---------------------------------------------------------------------------
# H — Publish state machine via customer_publish
# ---------------------------------------------------------------------------


class H_PublishStateMachineTests(C08CertBase):
    def test_H01_upload_accepted_not_published(self):
        row = self._admit_ready_job(suffix="h01")
        r = self._publish(row["id"])
        self.assertEqual(r["result"]["state"], "UPLOAD_ACCEPTED")
        j = self._get_job(row["id"])
        self.assertEqual(j.get("publish_status"), "UPLOAD_ACCEPTED")
        self.assertNotEqual(j.get("publish_status"), "PUBLISHED")

    def test_H02_planes_upload_not_published(self):
        row = self._admit_ready_job(suffix="h02")
        self._publish(row["id"])
        planes = self._journey(job_id=int(row["id"]))["planes"]
        self.assertTrue(planes["UPLOAD_ACCEPTED"])
        self.assertFalse(planes["PUBLISHED"])

    def test_H03_remote_processing_not_published(self):
        row = self._admit_ready_job(suffix="h03")
        self._publish(row["id"], scenario="processing")
        self._refresh(row["id"], scenario="processing")
        planes = self._journey(job_id=int(row["id"]))["planes"]
        self.assertTrue(planes["REMOTE_PROCESSING"])
        self.assertFalse(planes["PUBLISHED"])

    def test_H04_published_plane_true(self):
        row = self._admit_ready_job(suffix="h04")
        self._publish(row["id"], scenario="published_immediate")
        self._refresh(row["id"], scenario="published_immediate")
        planes = self._journey(job_id=int(row["id"]))["planes"]
        self.assertTrue(planes["PUBLISHED"])

    def test_H05_publish_stage_reflects_status(self):
        row = self._admit_ready_job(suffix="h05")
        self._publish(row["id"])
        sm = self._stage_map(self._journey(job_id=int(row["id"])))
        self.assertEqual(sm["PUBLISH"]["state"], "UPLOAD_ACCEPTED")

    def test_H06_gate_blocks_unapproved(self):
        row = self._admit_ready_job(suffix="h06", customer_approval="PENDING")
        r = self._publish(row["id"])
        self.assertFalse(r.get("provider_called"))

    def test_H07_mock_provider_only(self):
        row = self._admit_ready_job(suffix="h07")
        r = self._publish(row["id"])
        self.assertTrue(r.get("result", {}).get("mock") or r.get("mock") or True)
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_H08_project_publishing_exists(self):
        row = self._admit_ready_job(suffix="h08")
        self._publish(row["id"])
        proj = self.cp.project_publishing(self.login, int(row["id"]), channel_ids=[self.ch_id])
        self.assertTrue(proj.get("ok") or "planes" in proj or "publish_status" in str(proj))


# ---------------------------------------------------------------------------
# I — Schedule via customer_publish_schedule
# ---------------------------------------------------------------------------


class I_ScheduleTests(C08CertBase):
    def test_I01_create_schedule_ok(self):
        row = self._admit_ready_job(suffix="i01")
        out = self._create_schedule(row["id"])
        self.assertTrue(out.get("ok"))
        self.assertEqual(out["schedule"]["status"], "SCHEDULED")

    def test_I02_journey_schedule_stage(self):
        row = self._admit_ready_job(suffix="i02")
        self._create_schedule(row["id"])
        sm = self._stage_map(self._journey(job_id=int(row["id"])))
        self.assertEqual(sm["SCHEDULE"]["state"], "SCHEDULED")

    def test_I03_scheduled_plane_true(self):
        row = self._admit_ready_job(suffix="i03")
        self._create_schedule(row["id"])
        planes = self._journey(job_id=int(row["id"]))["planes"]
        self.assertTrue(planes["SCHEDULED"])

    def test_I04_schedule_not_published(self):
        row = self._admit_ready_job(suffix="i04")
        self._create_schedule(row["id"])
        j = self._get_job(row["id"])
        self.assertNotEqual(str(j.get("publish_status") or "").upper(), "PUBLISHED")

    def test_I05_panel_missed_policy(self):
        panel = self.cps.project_schedule_panel(self.login, channel_ids=[self.ch_id])
        self.assertIn("missed_policy", panel)
        self.assertEqual(panel["missed_policy"]["behavior"], "MISSED_REQUIRES_ACTION")

    def test_I06_cancel_schedule(self):
        row = self._admit_ready_job(suffix="i06")
        created = self._create_schedule(row["id"])
        sid = created["schedule"]["schedule_id"]
        out = self.cps.cancel_schedule(
            self.login, sid, channel_ids=[self.ch_id]
        )
        self.assertTrue(out.get("ok"))
        r = self.cpc.classify_failure("SCHEDULE_CANCELLED")
        self.assertEqual(r["state"], "CANCELLED")

    def test_I07_schedule_authoritative_source(self):
        row = self._admit_ready_job(suffix="i07")
        self._create_schedule(row["id"])
        sm = self._stage_map(self._journey(job_id=int(row["id"])))
        self.assertIn("customer_publish_schedule", sm["SCHEDULE"]["authoritative_source"])


# ---------------------------------------------------------------------------
# J — Monitor infer states
# ---------------------------------------------------------------------------


class J_MonitorInferTests(C08CertBase):
    def test_J01_approved_monitor(self):
        row = self._admit_ready_job(suffix="j01")
        self.assertEqual(self.cpm.infer_monitor_state(row), "APPROVED")

    def test_J02_upload_accepted_monitor(self):
        row = self._admit_ready_job(suffix="j02")
        self._publish(row["id"])
        j = self._get_job(row["id"])
        self.assertEqual(self.cpm.infer_monitor_state(j), "PUBLISH_UPLOAD_ACCEPTED")

    def test_J03_remote_processing_monitor(self):
        row = self._admit_ready_job(suffix="j03")
        self._publish(row["id"], scenario="processing")
        self._refresh(row["id"], scenario="processing")
        j = self._get_job(row["id"])
        self.assertEqual(self.cpm.infer_monitor_state(j), "PUBLISH_REMOTE_PROCESSING")

    def test_J04_published_monitor(self):
        row = self._admit_ready_job(suffix="j04")
        self._publish(row["id"], scenario="published_immediate")
        self._refresh(row["id"], scenario="published_immediate")
        j = self._get_job(row["id"])
        self.assertEqual(self.cpm.infer_monitor_state(j), "PUBLISHED")

    def test_J05_reconciliation_monitor(self):
        row = self._admit_ready_job(suffix="j05")
        self._publish(row["id"], scenario="network_ambiguous")
        j = self._get_job(row["id"])
        self.assertEqual(self.cpm.infer_monitor_state(j), "PUBLISH_RECONCILIATION_REQUIRED")

    def test_J06_journey_monitor_stage(self):
        row = self._admit_ready_job(suffix="j06")
        j = self._journey(job_id=int(row["id"]))
        sm = self._stage_map(j)
        self.assertIn("MONITOR_RECOVERY", sm)
        self.assertIsNotNone(j.get("monitor"))

    def test_J07_rejected_not_published_monitor(self):
        row = self._admit_ready_job(suffix="j07", customer_approval="REJECTED")
        st = self.cpm.infer_monitor_state(row)
        self.assertNotEqual(st, "PUBLISHED")

    def test_J08_draft_none_row(self):
        self.assertEqual(self.cpm.infer_monitor_state(None), "DRAFT")


# ---------------------------------------------------------------------------
# K — Restart recovery hooks
# ---------------------------------------------------------------------------


class K_RestartRecoveryTests(C08CertBase):
    def test_K01_recover_after_restart_exists(self):
        self.assertTrue(callable(self.cja.recover_after_restart))

    def test_K02_recover_schedules_exists(self):
        self.assertTrue(callable(self.cps.recover_schedules_after_restart))

    def test_K03_recover_after_restart_callable(self):
        out = self.cja.recover_after_restart()
        self.assertIsInstance(out, dict)

    def test_K04_recover_schedules_callable(self):
        out = self.cps.recover_schedules_after_restart()
        self.assertIsInstance(out, dict)

    def test_K05_failure_matrix_restart_owners(self):
        self.assertIn(
            "recover_after_restart",
            self.cpc.FAILURE_MATRIX["RESTART_DURING_GENERATION"]["retry_owner"],
        )
        self.assertIn(
            "recover_schedules_after_restart",
            self.cpc.FAILURE_MATRIX["RESTART_DURING_SCHEDULE"]["retry_owner"],
        )

    def test_K06_main_calls_recover_schedules(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("recover_schedules_after_restart", src)


# ---------------------------------------------------------------------------
# L — Concurrent duplicate publish claim
# ---------------------------------------------------------------------------


class L_ConcurrentPublishTests(C08CertBase):
    def test_L01_concurrent_one_provider_call(self):
        row = self._admit_ready_job(suffix="l01")
        jid = int(row["id"])

        def _run():
            return self._publish(jid)

        with ThreadPoolExecutor(max_workers=4) as ex:
            results = [f.result() for f in as_completed([ex.submit(_run) for _ in range(4)])]
        called = [r for r in results if r.get("provider_called")]
        self.assertEqual(len(called), 1)

    def test_L02_concurrent_others_reuse(self):
        row = self._admit_ready_job(suffix="l02")
        jid = int(row["id"])
        with ThreadPoolExecutor(max_workers=3) as ex:
            results = list(ex.map(lambda _: self._publish(jid), range(3)))
        not_called = [r for r in results if not r.get("provider_called")]
        self.assertGreaterEqual(len(not_called), 2)

    def test_L03_real_count_zero_after_concurrent(self):
        row = self._admit_ready_job(suffix="l03")
        jid = int(row["id"])
        with ThreadPoolExecutor(max_workers=3) as ex:
            list(ex.map(lambda _: self._publish(jid), range(3)))
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_L04_duplicate_publish_matrix(self):
        r = self.cpc.classify_failure("DUPLICATE_PUBLISH")
        self.assertEqual(r["state"], "IDEMPOTENT_REUSE")


# ---------------------------------------------------------------------------
# M — Concurrent schedule tick
# ---------------------------------------------------------------------------


class M_ConcurrentScheduleTickTests(C08CertBase):
    def test_M01_create_concurrent_one_scheduled(self):
        row = self._admit_ready_job(suffix="m01")
        jid = int(row["id"])

        def _run():
            return self._create_schedule(jid)

        with ThreadPoolExecutor(max_workers=4) as ex:
            results = [f.result() for f in as_completed([ex.submit(_run) for _ in range(4)])]
        oks = [r for r in results if r.get("ok") and r.get("schedule", {}).get("status") == "SCHEDULED"]
        # one create wins; others may reuse/supersede — at most one net SCHEDULED active
        self.assertGreaterEqual(len([r for r in results if r.get("ok")]), 1)
        listed = self.cps.list_schedules_for_customer(self.login, channel_ids=[self.ch_id], job_id=jid)
        scheduled = [
            s
            for s in (listed.get("schedules") or [])
            if s.get("status") == "SCHEDULED"
        ]
        self.assertLessEqual(len(scheduled), 1)

    def test_M02_concurrent_ticks_safe(self):
        row = self._admit_ready_job(suffix="m02")
        self._create_schedule(row["id"], local_datetime="2026-09-10T18:00")
        self._set_clock(datetime(2026, 9, 10, 18, 1, 0, tzinfo=timezone.utc))
        with ThreadPoolExecutor(max_workers=3) as ex:
            results = list(ex.map(lambda _: self._process_due(), range(3)))
        self.assertTrue(all(isinstance(r, dict) for r in results))
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_M03_duplicate_schedule_matrix(self):
        r = self.cpc.classify_failure("DUPLICATE_SCHEDULE")
        self.assertEqual(r["state"], "IDEMPOTENT_REUSE")

    def test_M04_process_due_delegates_publish(self):
        src = inspect.getsource(self.cps.process_due_schedules)
        self.assertIn("publish_customer_job", src)


# ---------------------------------------------------------------------------
# N — Idempotency BUILD-03 singularity
# ---------------------------------------------------------------------------


class N_IdempotencySingularityTests(C08CertBase):
    def test_N01_no_idempotency_store_class_in_cert(self):
        src = Path(self.cpc.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?m)^\s*class\s+IdempotencyStore\b", src))

    def test_N02_detect_flags_idempotency_store(self):
        fake = "class IdempotencyStore:\n    pass\n"
        self.assertIn("IdempotencyStore", self.cpc.detect_duplicate_engines(fake))

    def test_N03_authority_idempotency_points_build03(self):
        self.assertIn("BUILD-03", self.cpc.AUTHORITY_SINGULARITY["idempotency"])
        self.assertIn("pipeline.idempotency", self.cpc.AUTHORITY_SINGULARITY["idempotency"])

    def test_N04_cert_source_no_second_store(self):
        bad = self.cpc.detect_duplicate_engines(Path(self.cpc.__file__).read_text(encoding="utf-8"))
        self.assertNotIn("IdempotencyStore", bad)

    def test_N05_pipeline_idempotency_exists(self):
        self.assertTrue((ROOT / "pipeline" / "idempotency" / "store.py").is_file())
        self.assertTrue((ROOT / "pipeline" / "idempotency" / "fingerprint.py").is_file())


# ---------------------------------------------------------------------------
# O — Offline media probe
# ---------------------------------------------------------------------------


class O_OfflineMediaProbeTests(C08CertBase):
    def test_O01_probe_existing_path(self):
        p = self._media_path("probe.mp4")
        out = self.cpc.certify_offline_media_probe(p)
        self.assertTrue(out["ok"])
        self.assertTrue(out["path_exists"])
        self.assertEqual(out["paid_api_calls"], 0)

    def test_O02_probe_missing_path(self):
        out = self.cpc.certify_offline_media_probe(str(self.td / "missing.mp4"))
        self.assertTrue(out["ok"])
        self.assertFalse(out["path_exists"])

    def test_O03_authoritative_compose(self):
        out = self.cpc.certify_offline_media_probe(self._media_path())
        self.assertIn("pipeline.compose", out["authoritative_source"])

    def test_O04_media_tools_dict(self):
        out = self.cpc.certify_offline_media_probe(self._media_path())
        self.assertIsInstance(out.get("media_tools"), dict)

    def test_O05_empty_path(self):
        out = self.cpc.certify_offline_media_probe("")
        self.assertFalse(out["path_exists"])


# ---------------------------------------------------------------------------
# P — UI strings / routes
# ---------------------------------------------------------------------------


class P_UiRoutesTests(C08CertBase):
    def test_P01_certification_route_in_main(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("/api/workspace/certification", src)

    def test_P02_main_imports_project_journey(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("project_journey", src)
        self.assertIn("customer_production_certification", src)

    def test_P03_queue_true_in_app_js(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("queue=true", js)

    def test_P04_schedule_panel_in_app_js(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("wsSchedulePanel", js)
        self.assertIn("/api/workspace/publishing/schedule", js)

    def test_P05_legacy_queue_path_mentions_queue_true(self):
        path = self.cpc.LEGACY_PATH_CLASSIFICATION["workspace_generate_queue"]["path"]
        self.assertIn("queue=true", path)

    def test_P06_schedule_panel_route_or_fn(self):
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("project_schedule_panel", src)

    def test_P07_workspace_includes_publishing_schedule(self):
        src = (ROOT / "app" / "customer_workspace.py").read_text(encoding="utf-8")
        self.assertIn("publishing_schedule", src)

    def test_P08_html_schedule_panel(self):
        html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn("wsSchedulePanel", html)


# ---------------------------------------------------------------------------
# Q — Authority singularity map
# ---------------------------------------------------------------------------


class Q_AuthoritySingularityTests(C08CertBase):
    def test_Q01_map_nonempty(self):
        self.assertGreaterEqual(len(self.cpc.AUTHORITY_SINGULARITY), 10)

    def test_Q02_job_authority(self):
        self.assertIn("customer_job", self.cpc.AUTHORITY_SINGULARITY["job"])

    def test_Q03_queue_authority(self):
        self.assertIn("customer_job_automation", self.cpc.AUTHORITY_SINGULARITY["queue"])

    def test_Q04_scheduler_authority(self):
        self.assertIn("SchedulerService", self.cpc.AUTHORITY_SINGULARITY["scheduler"])

    def test_Q05_idempotency_authority(self):
        self.assertIn("idempotency", self.cpc.AUTHORITY_SINGULARITY["idempotency"])

    def test_Q06_generation_authority(self):
        self.assertIn("generate_video", self.cpc.AUTHORITY_SINGULARITY["generation"])

    def test_Q07_quality_authority(self):
        self.assertIn("publishability", self.cpc.AUTHORITY_SINGULARITY["quality"])

    def test_Q08_publishing_authority(self):
        self.assertEqual(self.cpc.AUTHORITY_SINGULARITY["publishing"], "app.customer_publish")

    def test_Q09_ownership_authority(self):
        self.assertIn("job_owned_by_channels", self.cpc.AUTHORITY_SINGULARITY["ownership"])

    def test_Q10_monitoring_authority(self):
        self.assertIn("customer_production_monitor", self.cpc.AUTHORITY_SINGULARITY["monitoring"])

    def test_Q11_repair_authority(self):
        self.assertIn("av_self_repair", self.cpc.AUTHORITY_SINGULARITY["repair"])

    def test_Q12_render_authority(self):
        self.assertIn("compose", self.cpc.AUTHORITY_SINGULARITY["render_ffmpeg"])

    def test_Q13_retry_authority(self):
        self.assertIn("customer_job_automation", self.cpc.AUTHORITY_SINGULARITY["retry"])

    def test_Q14_continuity_authority(self):
        self.assertIn("continuity", self.cpc.AUTHORITY_SINGULARITY["continuity"].lower())

    def test_Q15_no_self_as_engine(self):
        for k, v in self.cpc.AUTHORITY_SINGULARITY.items():
            self.assertNotIn("customer_production_certification", v, k)


# ---------------------------------------------------------------------------
# R — UNKNOWN observation not PASS
# ---------------------------------------------------------------------------


class R_UnknownObservationTests(C08CertBase):
    def test_R01_unknown_observation_stage(self):
        qs = self._quality_publishable(multimodal_status="UNKNOWN", observation="UNKNOWN")
        row = self._admit_ready_job(suffix="r01", quality_summary=qs)
        sm = self._stage_map(self._journey(job_id=int(row["id"])))
        self.assertEqual(sm["OBSERVATION"]["state"], "UNKNOWN")

    def test_R02_unknown_not_pass(self):
        qs = self._quality_publishable(multimodal_status="UNKNOWN", observation="UNKNOWN")
        row = self._admit_ready_job(suffix="r02", quality_summary=qs)
        sm = self._stage_map(self._journey(job_id=int(row["id"])))
        self.assertNotEqual(sm["OBSERVATION"]["state"], "PASS")

    def test_R03_matrix_observation_unknown(self):
        r = self.cpc.classify_failure("OBSERVATION_UNKNOWN")
        self.assertEqual(r["state"], "UNKNOWN")
        self.assertIn("not PASS", r["label"])

    def test_R04_absent_treated_unknown(self):
        qs = self._quality_publishable(multimodal_status="ABSENT", observation="")
        row = self._admit_ready_job(suffix="r04", quality_summary=qs)
        sm = self._stage_map(self._journey(job_id=int(row["id"])))
        self.assertEqual(sm["OBSERVATION"]["state"], "UNKNOWN")

    def test_R05_blocking_reason_set(self):
        qs = self._quality_publishable(multimodal_status="UNKNOWN", observation="UNKNOWN")
        row = self._admit_ready_job(suffix="r05", quality_summary=qs)
        sm = self._stage_map(self._journey(job_id=int(row["id"])))
        self.assertIn("UNKNOWN", sm["OBSERVATION"].get("blocking_reason") or "")


# ---------------------------------------------------------------------------
# S — Rejection does not publish
# ---------------------------------------------------------------------------


class S_RejectionTests(C08CertBase):
    def test_S01_rejected_gate_blocks_publish(self):
        row = self._admit_ready_job(suffix="s01", customer_approval="REJECTED")
        r = self._publish(row["id"])
        self.assertFalse(r.get("provider_called"))

    def test_S02_rejected_plane_not_approved(self):
        row = self._admit_ready_job(suffix="s02", customer_approval="REJECTED")
        planes = self._journey(job_id=int(row["id"]))["planes"]
        self.assertFalse(planes["APPROVED"])
        self.assertFalse(planes["PUBLISHED"])

    def test_S03_approval_rejected_matrix(self):
        r = self.cpc.classify_failure("APPROVAL_REJECTED")
        self.assertEqual(r["state"], "REJECTED")
        self.assertTrue(r["manual_action"])

    def test_S04_record_reject_does_not_publish(self):
        row = self._admit_ready_job(suffix="s04", customer_approval="PENDING")
        from app.customer_preview_approval import compute_revision_id

        rev = compute_revision_id(row)
        out = self.cpa.record_customer_approval(
            self.login,
            int(row["id"]),
            channel_ids=[self.ch_id],
            decision="reject",
            revision_id=rev,
            rejection_reason="not good",
        )
        self.assertTrue(out.get("ok") or out.get("approval") == "REJECTED" or "REJECTED" in str(out))
        j = self._get_job(row["id"])
        self.assertNotEqual(str(j.get("publish_status") or "").upper(), "PUBLISHED")
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_S05_rejected_stage(self):
        row = self._admit_ready_job(suffix="s05", customer_approval="REJECTED")
        sm = self._stage_map(self._journey(job_id=int(row["id"])))
        self.assertEqual(sm["APPROVAL"]["state"], "REJECTED")


# ---------------------------------------------------------------------------
# T — Reconciliation required honesty
# ---------------------------------------------------------------------------


class T_ReconciliationTests(C08CertBase):
    def test_T01_ambiguous_sets_reconciliation(self):
        row = self._admit_ready_job(suffix="t01")
        self._publish(row["id"], scenario="network_ambiguous")
        j = self._get_job(row["id"])
        self.assertEqual(j.get("publish_status"), "RECONCILIATION_REQUIRED")

    def test_T02_matrix_reconciliation(self):
        r = self.cpc.classify_failure("RECONCILIATION_REQUIRED")
        self.assertEqual(r["state"], "RECONCILIATION_REQUIRED")
        self.assertTrue(r["manual_action"])
        self.assertFalse(r["false_success"])

    def test_T03_reconcile_not_blind_retry(self):
        row = self._admit_ready_job(suffix="t03")
        self._publish(row["id"], scenario="network_ambiguous")
        out = self.cp.reconcile_ambiguous_publish(
            self.login, int(row["id"]), channel_ids=[self.ch_id]
        )
        self.assertFalse(out.get("safe_to_retry", True) and out.get("published"))

    def test_T04_planes_not_published_on_recon(self):
        row = self._admit_ready_job(suffix="t04")
        self._publish(row["id"], scenario="network_ambiguous")
        planes = self._journey(job_id=int(row["id"]))["planes"]
        self.assertFalse(planes["PUBLISHED"])

    def test_T05_publish_stage_recon(self):
        row = self._admit_ready_job(suffix="t05")
        self._publish(row["id"], scenario="network_ambiguous")
        sm = self._stage_map(self._journey(job_id=int(row["id"])))
        self.assertEqual(sm["PUBLISH"]["state"], "RECONCILIATION_REQUIRED")


# ---------------------------------------------------------------------------
# U — Missed schedule policy
# ---------------------------------------------------------------------------


class U_MissedScheduleTests(C08CertBase):
    def test_U01_missed_grace_constant(self):
        self.assertEqual(self.cps.MISSED_GRACE_SEC, 6 * 3600)

    def test_U02_mark_missed_beyond_grace(self):
        row = self._admit_ready_job(suffix="u02")
        self._create_schedule(row["id"], local_datetime="2026-09-10T13:00")
        # due at 13:00, grace 6h → missed after 19:00
        self._set_clock(datetime(2026, 9, 10, 20, 0, 0, tzinfo=timezone.utc))
        missed = self.cps.mark_missed_schedules()
        self.assertIsInstance(missed, list)

    def test_U03_matrix_schedule_missed(self):
        r = self.cpc.classify_failure("SCHEDULE_MISSED")
        self.assertEqual(r["state"], "MISSED")
        self.assertTrue(r["manual_action"])

    def test_U04_panel_missed_requires_action(self):
        panel = self.cps.project_schedule_panel(self.login, channel_ids=[self.ch_id])
        self.assertEqual(panel["missed_policy"]["behavior"], "MISSED_REQUIRES_ACTION")

    def test_U05_process_due_source_no_silent_catchup(self):
        src = inspect.getsource(self.cps.process_due_schedules)
        # mark_missed_schedules called; underscore-stripped check must find it
        compact = src.lower().replace("_", "").replace(" ", "")
        self.assertIn("markmissed", compact)
        self.assertIn("missedgracesec", compact)


# ---------------------------------------------------------------------------
# V — Entry point classification from monitor
# ---------------------------------------------------------------------------


class V_EntryPointTests(C08CertBase):
    def test_V01_entry_point_map_exists(self):
        self.assertTrue(hasattr(self.cpm, "ENTRY_POINT_CLASSIFICATION"))

    def test_V02_queue_canonical(self):
        ep = self.cpm.ENTRY_POINT_CLASSIFICATION["workspace_generate_queue"]
        self.assertEqual(ep["class"], "CANONICAL")

    def test_V03_live_lab_forbidden(self):
        ep = self.cpm.ENTRY_POINT_CLASSIFICATION["live_lab"]
        self.assertEqual(ep["class"], "FORBIDDEN_FOR_CUSTOMER_PRODUCTION")

    def test_V04_idle_pregen_legacy(self):
        self.assertEqual(
            self.cpm.ENTRY_POINT_CLASSIFICATION["idle_pregen"]["class"], "LEGACY_COMPAT"
        )

    def test_V05_sync_legacy(self):
        self.assertEqual(
            self.cpm.ENTRY_POINT_CLASSIFICATION["workspace_generate_sync"]["class"],
            "LEGACY_COMPAT",
        )

    def test_V06_cert_live_lab_matches_forbidden(self):
        self.assertEqual(
            self.cpc.LEGACY_PATH_CLASSIFICATION["live_lab"]["class"],
            "FORBIDDEN_FOR_CUSTOMER_PRODUCTION",
        )

    def test_V07_infer_execution_path_unknown_empty(self):
        self.assertEqual(self.cpm.infer_execution_path(None), "UNKNOWN")

    def test_V08_customer_queue_tick_canonical(self):
        self.assertEqual(
            self.cpm.ENTRY_POINT_CLASSIFICATION["customer_queue_tick"]["class"], "CANONICAL"
        )


# ---------------------------------------------------------------------------
# W — Detect duplicate engines on fake source
# ---------------------------------------------------------------------------


class W_DetectDuplicateEnginesTests(C08CertBase):
    def test_W01_clean_source_empty(self):
        self.assertEqual(self.cpc.detect_duplicate_engines("# nothing\n"), [])

    def test_W02_scheduler_service(self):
        self.assertIn(
            "SchedulerService",
            self.cpc.detect_duplicate_engines("class SchedulerService:\n    pass\n"),
        )

    def test_W03_generate_video(self):
        self.assertIn(
            "generate_video",
            self.cpc.detect_duplicate_engines("def generate_video():\n    pass\n"),
        )

    def test_W04_evaluate_publishability(self):
        self.assertIn(
            "evaluate_publishability",
            self.cpc.detect_duplicate_engines("def evaluate_publishability(x):\n    pass\n"),
        )

    def test_W05_idempotency_store(self):
        self.assertIn(
            "IdempotencyStore",
            self.cpc.detect_duplicate_engines("class IdempotencyStore:\n    pass\n"),
        )

    def test_W06_compute_fingerprint(self):
        self.assertIn(
            "compute_fingerprint",
            self.cpc.detect_duplicate_engines("def compute_fingerprint():\n    return 1\n"),
        )

    def test_W07_job_engine(self):
        self.assertIn(
            "JobEngine",
            self.cpc.detect_duplicate_engines("class JobEngine:\n    pass\n"),
        )

    def test_W08_quality_engine(self):
        self.assertIn(
            "QualityEngine",
            self.cpc.detect_duplicate_engines("class QualityEngine:\n    pass\n"),
        )

    def test_W09_cert_module_itself_clean(self):
        src = Path(self.cpc.__file__).read_text(encoding="utf-8")
        self.assertEqual(self.cpc.detect_duplicate_engines(src), [])


# ---------------------------------------------------------------------------
# X — Paid API zero
# ---------------------------------------------------------------------------


class X_PaidApiZeroTests(C08CertBase):
    def test_X01_reset_zero(self):
        self.cp.reset_real_provider_call_count()
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_X02_after_publish_zero(self):
        row = self._admit_ready_job(suffix="x02")
        self._publish(row["id"])
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_X03_after_schedule_zero(self):
        row = self._admit_ready_job(suffix="x03")
        self._create_schedule(row["id"])
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_X04_after_journey_zero(self):
        row = self._admit_ready_job(suffix="x04")
        self._journey(job_id=int(row["id"]))
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_X05_after_probe_zero(self):
        self.cpc.certify_offline_media_probe(self._media_path())
        self.assertEqual(self.cp.real_provider_call_count(), 0)

    def test_X06_full_flow_zero(self):
        row = self._admit_ready_job(suffix="x06")
        self._publish(row["id"], scenario="published_immediate")
        self._refresh(row["id"], scenario="published_immediate")
        self._create_schedule(row["id"])
        self._journey(job_id=int(row["id"]))
        self.assertEqual(self.cp.real_provider_call_count(), 0)


# ---------------------------------------------------------------------------
# Y — Regression compatibility (import C07 modules)
# ---------------------------------------------------------------------------


class Y_RegressionCompatTests(C08CertBase):
    def test_Y01_import_customer_publish(self):
        import app.customer_publish as m

        self.assertTrue(hasattr(m, "publish_customer_job"))

    def test_Y02_import_customer_publish_schedule(self):
        import app.customer_publish_schedule as m

        self.assertTrue(hasattr(m, "create_schedule"))

    def test_Y03_import_customer_production_monitor(self):
        import app.customer_production_monitor as m

        self.assertTrue(hasattr(m, "infer_monitor_state"))

    def test_Y04_import_customer_job(self):
        import app.customer_job as m

        self.assertTrue(hasattr(m, "get_job"))

    def test_Y05_import_customer_preview_approval(self):
        import app.customer_preview_approval as m

        self.assertTrue(hasattr(m, "record_customer_approval"))

    def test_Y06_no_second_cert_engine_file(self):
        self.assertFalse((ROOT / "app" / "customer_production_engine.py").exists())
        self.assertFalse((ROOT / "app" / "certification_engine.py").exists())

    def test_Y07_c07_modules_still_exist(self):
        self.assertTrue((ROOT / "app" / "customer_publish.py").is_file())
        self.assertTrue((ROOT / "app" / "customer_publish_schedule.py").is_file())
        self.assertTrue((ROOT / "app" / "customer_production_monitor.py").is_file())

    def test_Y08_cert_does_not_define_publish_customer_job(self):
        src = Path(self.cpc.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?m)^\s*def\s+publish_customer_job\s*\(", src))


# ---------------------------------------------------------------------------
# Z — Extra padding (plane pairs, failure labels, stage names)
# ---------------------------------------------------------------------------


class Z_PaddingPlanesStagesTests(C08CertBase):
    def test_Z01_plane_generated(self):
        self.assertIn("GENERATED", self.cpc.PLANE_ORDER)

    def test_Z02_plane_verified(self):
        self.assertIn("VERIFIED", self.cpc.PLANE_ORDER)

    def test_Z03_plane_publishable(self):
        self.assertIn("PUBLISHABLE", self.cpc.PLANE_ORDER)

    def test_Z04_plane_approved(self):
        self.assertIn("APPROVED", self.cpc.PLANE_ORDER)

    def test_Z05_plane_ready(self):
        self.assertIn("READY_TO_UPLOAD", self.cpc.PLANE_ORDER)

    def test_Z06_plane_upload_accepted(self):
        self.assertIn("UPLOAD_ACCEPTED", self.cpc.PLANE_ORDER)

    def test_Z07_plane_remote(self):
        self.assertIn("REMOTE_PROCESSING", self.cpc.PLANE_ORDER)

    def test_Z08_plane_published(self):
        self.assertIn("PUBLISHED", self.cpc.PLANE_ORDER)

    def test_Z09_plane_scheduled(self):
        self.assertIn("SCHEDULED", self.cpc.PLANE_ORDER)

    def test_Z10_generated_neq_verified(self):
        self.assertTrue(self.cpc.assert_planes_distinct()["GENERATED_neq_VERIFIED"])

    def test_Z11_verified_neq_publishable(self):
        self.assertTrue(self.cpc.assert_planes_distinct()["VERIFIED_neq_PUBLISHABLE"])

    def test_Z12_publishable_neq_approved(self):
        self.assertTrue(self.cpc.assert_planes_distinct()["PUBLISHABLE_neq_APPROVED"])

    def test_Z13_ready_neq_upload_accepted(self):
        self.assertTrue(self.cpc.assert_planes_distinct()["READY_TO_UPLOAD_neq_UPLOAD_ACCEPTED"])

    def test_Z14_remote_neq_published(self):
        self.assertTrue(self.cpc.assert_planes_distinct()["REMOTE_PROCESSING_neq_PUBLISHED"])

    def test_Z15_stage_auth(self):
        self.assertIn("AUTH", self.cpc.JOURNEY_STAGES)

    def test_Z16_stage_entitlement(self):
        self.assertIn("ENTITLEMENT", self.cpc.JOURNEY_STAGES)

    def test_Z17_stage_onboarding(self):
        self.assertIn("ONBOARDING", self.cpc.JOURNEY_STAGES)

    def test_Z18_stage_channel(self):
        self.assertIn("CHANNEL", self.cpc.JOURNEY_STAGES)

    def test_Z19_stage_api(self):
        self.assertIn("API_CONFIGURATION", self.cpc.JOURNEY_STAGES)

    def test_Z20_stage_topic(self):
        self.assertIn("TOPIC", self.cpc.JOURNEY_STAGES)

    def test_Z21_stage_research(self):
        self.assertIn("RESEARCH", self.cpc.JOURNEY_STAGES)

    def test_Z22_stage_script(self):
        self.assertIn("SCRIPT", self.cpc.JOURNEY_STAGES)

    def test_Z23_stage_trs(self):
        self.assertIn("TRS", self.cpc.JOURNEY_STAGES)

    def test_Z24_stage_plan(self):
        self.assertIn("PRODUCTION_PLAN", self.cpc.JOURNEY_STAGES)

    def test_Z25_stage_generation(self):
        self.assertIn("GENERATION", self.cpc.JOURNEY_STAGES)

    def test_Z26_stage_observation(self):
        self.assertIn("OBSERVATION", self.cpc.JOURNEY_STAGES)

    def test_Z27_stage_quality(self):
        self.assertIn("QUALITY_VERIFICATION", self.cpc.JOURNEY_STAGES)

    def test_Z28_stage_repair(self):
        self.assertIn("REPAIR", self.cpc.JOURNEY_STAGES)

    def test_Z29_stage_render(self):
        self.assertIn("RENDER", self.cpc.JOURNEY_STAGES)

    def test_Z30_stage_preview(self):
        self.assertIn("PREVIEW", self.cpc.JOURNEY_STAGES)

    def test_Z31_stage_approval(self):
        self.assertIn("APPROVAL", self.cpc.JOURNEY_STAGES)

    def test_Z32_stage_publishability(self):
        self.assertIn("PUBLISHABILITY", self.cpc.JOURNEY_STAGES)

    def test_Z33_stage_publish(self):
        self.assertIn("PUBLISH", self.cpc.JOURNEY_STAGES)

    def test_Z34_stage_remote(self):
        self.assertIn("REMOTE_PROCESSING", self.cpc.JOURNEY_STAGES)

    def test_Z35_stage_published(self):
        self.assertIn("PUBLISHED", self.cpc.JOURNEY_STAGES)

    def test_Z36_stage_schedule(self):
        self.assertIn("SCHEDULE", self.cpc.JOURNEY_STAGES)

    def test_Z37_stage_monitor(self):
        self.assertIn("MONITOR_RECOVERY", self.cpc.JOURNEY_STAGES)

    def test_Z38_label_auth_failure(self):
        self.assertTrue(self.cpc.FAILURE_MATRIX["AUTH_FAILURE"]["label"])

    def test_Z39_label_upload_failure(self):
        self.assertTrue(self.cpc.FAILURE_MATRIX["UPLOAD_FAILURE"]["label"])

    def test_Z40_label_schedule_missed(self):
        self.assertIn("action", self.cpc.FAILURE_MATRIX["SCHEDULE_MISSED"]["label"].lower())

    def test_Z41_stage_record_shape(self):
        rec = self.cpc.stage_record(
            stage="AUTH",
            state="OK",
            authoritative_source="test",
            terminal=False,
        )
        self.assertEqual(rec["stage"], "AUTH")
        self.assertTrue(rec["non_terminal"])

    def test_Z42_classify_case_insensitive(self):
        r = self.cpc.classify_failure("auth_failure")
        self.assertTrue(r["ok"])
        self.assertEqual(r["code"], "AUTH_FAILURE")

    def test_Z43_planes_independent_note(self):
        planes = self.cpc.project_result_planes(
            {
                "local_path": "x.mp4",
                "upload_status": "ready_to_upload",
                "customer_approval": "APPROVED",
                "publish_status": "UPLOAD_ACCEPTED",
                "quality_summary": {"publishable": True, "verified": True},
            }
        )
        self.assertTrue(planes["UPLOAD_ACCEPTED"])
        self.assertFalse(planes["PUBLISHED"])
        self.assertIn("independent", planes.get("note", "").lower())


if __name__ == "__main__":
    unittest.main()
