"""C10 — Marathon Observability & Forensic Harness (paid APIs = 0).

>=150 deterministic unittest cases. Observation/evidence only.
Does NOT execute the real Marathon Test. Does NOT call paid providers.
"""
from __future__ import annotations

import inspect
import json
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class C10Base(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.td = Path(self._tmp.name)
        self.data_dir = self.td / "data"
        self.data_dir.mkdir()
        self.docs_root = self.td / "docs_runs"
        self.docs_root.mkdir()

        import app.customer_marathon_observability as mo
        from app import config as cfg

        self.mo = mo
        self.cfg = cfg
        self._orig_data = mo.DATA_DIR
        self._orig_cfg = cfg.DATA_DIR
        mo.DATA_DIR = self.data_dir
        cfg.DATA_DIR = self.data_dir
        # clear in-memory bindings
        mo._JOB_BINDINGS.clear()
        mo._WORKDIR_BINDINGS.clear()
        mo._ACTIVE_SESSIONS.clear()

    def tearDown(self):
        self.mo.DATA_DIR = self._orig_data
        self.cfg.DATA_DIR = self._orig_cfg
        self.mo._JOB_BINDINGS.clear()
        self.mo._WORKDIR_BINDINGS.clear()
        self.mo._ACTIVE_SESSIONS.clear()

    def _sess(self, *, login="cust_a", case="MARATHON_SHORT", vtype="SHORT", niche="synthetic"):
        return self.mo.create_marathon_session(
            login_id=login,
            test_case_id=case,
            video_type=vtype,
            niche=niche,
            data_dir=self.data_dir,
        )


# ---- A: run identity / test cases ----
class A_RunIdentityTests(C10Base):
    def test_A01_create_short_session(self):
        s = self._sess()
        self.assertTrue(s.get("ok"))
        self.assertTrue(str(s["marathon_session_id"]).startswith("ms_"))
        self.assertEqual(s["video_type"], "SHORT")
        self.assertEqual(s["status"], "CREATED")
        self.assertFalse(s.get("owns_production"))

    def test_A02_create_long_session(self):
        s = self._sess(case="MARATHON_LONG", vtype="LONG")
        self.assertEqual(s["video_type"], "LONG")
        self.assertEqual(s["test_case_id"], "MARATHON_LONG")

    def test_A03_invalid_video_type(self):
        out = self.mo.create_marathon_session(
            login_id="x", test_case_id="MARATHON_SHORT", video_type="MEDIUM", data_dir=self.data_dir
        )
        self.assertFalse(out.get("ok"))

    def test_A04_unknown_test_case(self):
        out = self.mo.get_test_case("NOPE")
        self.assertFalse(out.get("ok"))

    def test_A05_test_case_long_fields(self):
        tc = self.mo.get_test_case("MARATHON_LONG")["test_case"]
        self.assertEqual(tc["watchdog_interval_sec"], 600)
        self.assertGreater(tc["target_duration_sec"], 60)

    def test_A06_test_case_short_fields(self):
        tc = self.mo.get_test_case("MARATHON_SHORT")["test_case"]
        self.assertLess(tc["target_duration_sec"], 120)

    def test_A07_no_secrets_in_identity(self):
        s = self._sess()
        blob = json.dumps(s).lower()
        self.assertNotIn("api_key", blob)
        self.assertNotIn("password", blob)

    def test_A08_manifest_written(self):
        s = self._sess()
        m = self.mo.load_manifest(s["marathon_session_id"], data_dir=self.data_dir)
        self.assertEqual(m["identity"]["run_id"], s["run_id"])

    def test_A09_run_json_written(self):
        s = self._sess()
        r = self.mo.load_run(s["marathon_session_id"], data_dir=self.data_dir)
        self.assertEqual(r["login_id"], "cust_a")

    def test_A10_finish_session(self):
        s = self._sess()
        out = self.mo.finish_session(s["marathon_session_id"], status="COMPLETED", data_dir=self.data_dir)
        self.assertTrue(out["ok"])
        self.assertEqual(out["run"]["status"], "COMPLETED")
        self.assertIsNotNone(out["run"]["end_time"])

    def test_A11_application_version_present(self):
        s = self._sess()
        self.assertTrue(s.get("application_version"))

    def test_A12_bind_job(self):
        s = self._sess()
        out = self.mo.bind_job(s["marathon_session_id"], 42, login_id="cust_a", data_dir=self.data_dir)
        self.assertTrue(out["ok"])
        self.assertEqual(self.mo._JOB_BINDINGS[42], s["marathon_session_id"])

    def test_A13_bind_job_wrong_owner(self):
        s = self._sess()
        out = self.mo.bind_job(s["marathon_session_id"], 42, login_id="other", data_dir=self.data_dir)
        self.assertEqual(out.get("error_code"), "OWNERSHIP_FAILURE")


# ---- B: evidence schema / append ----
class B_EvidenceSchemaTests(C10Base):
    def test_B01_record_evidence_fields(self):
        s = self._sess()
        out = self.mo.record_evidence(
            s["marathon_session_id"],
            ledger="timeline",
            stage="TEST",
            component="unit",
            operation="op",
            event_type="EVT",
            status="OK",
            data_dir=self.data_dir,
        )
        rec = out["record"]
        for k in ("event_id", "marathon_session_id", "timestamp", "schema_version", "record_hash", "prev_hash"):
            self.assertIn(k, rec)

    def test_B02_unknown_ledger_rejected(self):
        s = self._sess()
        out = self.mo.record_evidence(
            s["marathon_session_id"],
            ledger="not_a_ledger",
            stage="X",
            component="c",
            operation="o",
            event_type="E",
            data_dir=self.data_dir,
        )
        self.assertFalse(out.get("ok"))

    def test_B03_append_only_grows(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        self.mo.record_evidence(sid, ledger="timeline", stage="A", component="c", operation="o", event_type="E1", data_dir=self.data_dir)
        self.mo.record_evidence(sid, ledger="timeline", stage="A", component="c", operation="o", event_type="E2", data_dir=self.data_dir)
        rows = self.mo.read_ledger(sid, "timeline", data_dir=self.data_dir)
        # includes SESSION_CREATED + 2
        self.assertGreaterEqual(len(rows), 3)

    def test_B04_chain_integrity(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        for i in range(5):
            self.mo.record_evidence(sid, ledger="api", stage="P", component="c", operation=f"o{i}", event_type="API", data_dir=self.data_dir)
        self.assertTrue(self.mo.verify_ledger_integrity(sid, "api", data_dir=self.data_dir)["ok"])

    def test_B05_chain_detects_tamper(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        self.mo.record_evidence(sid, ledger="api", stage="P", component="c", operation="o", event_type="API", data_dir=self.data_dir)
        path = self.mo.session_dir(sid, data_dir=self.data_dir) / "api" / "events.jsonl"
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        row = json.loads(lines[0])
        row["status"] = "TAMPERED"
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        self.assertFalse(self.mo.verify_ledger_integrity(sid, "api", data_dir=self.data_dir)["ok"])

    def test_B06_all_ledger_dirs_created(self):
        s = self._sess()
        d = self.mo.session_dir(s["marathon_session_id"], data_dir=self.data_dir)
        for name in self.mo.LEDGER_DIRS:
            self.assertTrue((d / name).is_dir())

    def test_B07_secret_redaction_keys(self):
        out = self.mo.redact({"api_key": "sk-abc", "ok": True})
        self.assertEqual(out["api_key"], "[redacted]")
        self.assertTrue(out["ok"])

    def test_B08_secret_redaction_bearer(self):
        out = self.mo.redact("Authorization: Bearer abcdefghijklmnop")
        self.assertEqual(out, "[redacted]")

    def test_B09_concurrent_append(self):
        s = self._sess()
        sid = s["marathon_session_id"]

        def _w(i):
            return self.mo.record_evidence(
                sid, ledger="timeline", stage="C", component="c", operation=f"o{i}", event_type="E", data_dir=self.data_dir
            )

        with ThreadPoolExecutor(max_workers=8) as ex:
            list(as_completed([ex.submit(_w, i) for i in range(20)]))
        self.assertTrue(self.mo.verify_ledger_integrity(sid, "timeline", data_dir=self.data_dir)["ok"])


# ---- C: API telemetry ----
class C_ApiTelemetryTests(C10Base):
    def test_C01_record_api_call(self):
        s = self._sess()
        out = self.mo.record_api_call(
            s["marathon_session_id"],
            provider="mock",
            operation="visual.generate",
            status="OK",
            latency_ms=12.5,
            scene_id="s1",
            beat_id="b1",
            data_dir=self.data_dir,
        )
        self.assertTrue(out["ok"])
        rows = self.mo.read_ledger(s["marathon_session_id"], "api", data_dir=self.data_dir)
        self.assertEqual(rows[0]["provider"], "mock")

    def test_C02_api_retry_metadata(self):
        s = self._sess()
        self.mo.record_api_call(
            s["marathon_session_id"], provider="mock", operation="tts", status="FAIL", latency_ms=1, retry_count=3, data_dir=self.data_dir
        )
        row = self.mo.read_ledger(s["marathon_session_id"], "api", data_dir=self.data_dir)[0]
        self.assertEqual(row["metadata"]["retry_count"], 3)

    def test_C03_api_no_secrets(self):
        s = self._sess()
        self.mo.record_api_call(
            s["marathon_session_id"],
            provider="mock",
            operation="x",
            status="OK",
            latency_ms=1,
            data_dir=self.data_dir,
        )
        blob = json.dumps(self.mo.read_ledger(s["marathon_session_id"], "api", data_dir=self.data_dir))
        self.assertNotIn("sk-", blob.lower())

    def test_C04_usage_fanout_when_bound(self):
        s = self._sess()
        wd = self.td / "work"
        wd.mkdir()
        self.mo.bind_work_dir(s["marathon_session_id"], wd, data_dir=self.data_dir)
        from pipeline.idempotency.metrics import UsageEvent, record_usage_event

        record_usage_event(wd, UsageEvent(operation="tts", provider="mock", model="m", call_count=1, retry_count=0, cache_hit=False, latency_sec=0.01, detail=""))
        rows = self.mo.read_ledger(s["marathon_session_id"], "api", data_dir=self.data_dir)
        self.assertGreaterEqual(len(rows), 1)

    def test_C05_usage_no_fanout_unbound(self):
        s = self._sess()
        wd = self.td / "work2"
        wd.mkdir()
        from pipeline.idempotency.metrics import UsageEvent, record_usage_event

        before = len(self.mo.read_ledger(s["marathon_session_id"], "api", data_dir=self.data_dir))
        record_usage_event(wd, UsageEvent(operation="tts", provider="mock", model="m", call_count=1, retry_count=0, cache_hit=True, latency_sec=0.01, detail=""))
        after = len(self.mo.read_ledger(s["marathon_session_id"], "api", data_dir=self.data_dir))
        self.assertEqual(before, after)


# ---- D: prompt / beats ----
class D_PromptBeatTests(C10Base):
    def test_D01_prompt_hash(self):
        s = self._sess()
        out = self.mo.record_prompt(
            s["marathon_session_id"], provider="mock", operation="visual", prompt_text="hello world", scene_id="s1", beat_id="b1", data_dir=self.data_dir
        )
        meta = out["record"]["metadata"]
        self.assertTrue(meta["prompt_id"].startswith("pr_"))
        self.assertEqual(len(meta["prompt_hash"]), 32)

    def test_D02_prompt_fields(self):
        s = self._sess()
        out = self.mo.record_prompt(
            s["marathon_session_id"],
            provider="mock",
            operation="visual",
            prompt_text="desk",
            character_identity="host",
            location="studio",
            camera="wide",
            lighting="soft",
            emotion="calm",
            data_dir=self.data_dir,
        )
        meta = out["record"]["metadata"]
        self.assertEqual(meta["character_identity"], "host")
        self.assertEqual(meta["camera"], "wide")

    def test_D03_script_beats(self):
        s = self._sess()
        self.mo.record_script_beats(
            s["marathon_session_id"],
            topic="t",
            research_id="r",
            script_id="sc",
            dialogues=[{"dialogue_id": "d1"}],
            visual_beats=[{"beat_id": "b1", "scene_id": "s1"}],
            scenes=[{"scene_id": "s1"}],
            data_dir=self.data_dir,
        )
        self.assertEqual(len(self.mo.read_ledger(s["marathon_session_id"], "scripts", data_dir=self.data_dir)), 1)
        self.assertEqual(len(self.mo.read_ledger(s["marathon_session_id"], "beats", data_dir=self.data_dir)), 1)
        self.assertEqual(len(self.mo.read_ledger(s["marathon_session_id"], "scenes", data_dir=self.data_dir)), 1)

    def test_D04_pre_transform_prompt(self):
        s = self._sess()
        out = self.mo.record_prompt(
            s["marathon_session_id"],
            provider="mock",
            operation="visual",
            prompt_text="final",
            pre_transform_prompt="draft",
            data_dir=self.data_dir,
        )
        self.assertEqual(out["record"]["metadata"]["pre_transform_prompt"], "draft")


# ---- E: visual/audio/subtitle ledgers ----
class E_ArtifactLedgerTests(C10Base):
    def test_E01_visual_unknown_preserved(self):
        s = self._sess()
        self.mo.record_visual_artifact(
            s["marathon_session_id"],
            {"asset_id": "a1", "verification_status": "UNKNOWN", "quality_status": "UNKNOWN", "actual_artifact_type": "image"},
            data_dir=self.data_dir,
        )
        row = self.mo.read_ledger(s["marathon_session_id"], "visual", data_dir=self.data_dir)[0]
        self.assertEqual(row["status"], "UNKNOWN")

    def test_E02_audio_ledger(self):
        s = self._sess()
        self.mo.record_audio_artifact(
            s["marathon_session_id"],
            {"audio_id": "au1", "dialogue_id": "d1", "provider": "tts", "sample_rate": 24000, "verification_state": "OK"},
            data_dir=self.data_dir,
        )
        self.assertEqual(len(self.mo.read_ledger(s["marathon_session_id"], "audio", data_dir=self.data_dir)), 1)

    def test_E03_subtitle_ledger(self):
        s = self._sess()
        self.mo.record_subtitle(
            s["marathon_session_id"],
            {"dialogue_id": "d1", "locale": "en", "validation_status": "OK"},
            data_dir=self.data_dir,
        )
        self.assertEqual(len(self.mo.read_ledger(s["marathon_session_id"], "subtitles", data_dir=self.data_dir)), 1)

    def test_E04_visual_reuse_flag(self):
        s = self._sess()
        self.mo.record_visual_artifact(
            s["marathon_session_id"],
            {"asset_id": "a2", "reuse": True, "lineage": "fp1", "status": "OK"},
            data_dir=self.data_dir,
        )
        meta = self.mo.read_ledger(s["marathon_session_id"], "visual", data_dir=self.data_dir)[0]["metadata"]
        self.assertTrue(meta["reuse"])


# ---- F: state / failure / repair / render / publish / schedule ----
class F_LifecycleLedgerTests(C10Base):
    def test_F01_state_transition(self):
        s = self._sess()
        self.mo.record_state_transition(s["marathon_session_id"], from_state="QUEUED", to_state="CLAIMED", job_id=1, data_dir=self.data_dir)
        rows = [r for r in self.mo.read_ledger(s["marathon_session_id"], "timeline", data_dir=self.data_dir) if r["event_type"] == "STATE_TRANSITION"]
        self.assertEqual(rows[-1]["metadata"]["to_state"], "CLAIMED")

    def test_F02_failure_ledger(self):
        s = self._sess()
        self.mo.record_failure(
            s["marathon_session_id"],
            failure_code="TIMEOUT",
            stage="GENERATE",
            component="visual",
            retry_count=1,
            recovery_action="backoff",
            data_dir=self.data_dir,
        )
        self.assertEqual(len(self.mo.read_ledger(s["marathon_session_id"], "failures", data_dir=self.data_dir)), 1)

    def test_F03_repair_ledger(self):
        s = self._sess()
        self.mo.record_repair(s["marathon_session_id"], {"repair_id": "r1", "post_repair_status": "OK"}, data_dir=self.data_dir)
        self.assertEqual(self.mo.read_ledger(s["marathon_session_id"], "repair", data_dir=self.data_dir)[0]["status"], "OK")

    def test_F04_render_command_hashed(self):
        s = self._sess()
        self.mo.record_render(
            s["marathon_session_id"],
            {"render_request_id": "rr", "command": "ffmpeg -i in.mp4 out.mp4", "status": "OK"},
            data_dir=self.data_dir,
        )
        meta = self.mo.read_ledger(s["marathon_session_id"], "render", data_dir=self.data_dir)[0]["metadata"]
        self.assertIn("command_hash", meta)
        self.assertNotIn("command", meta)

    def test_F05_publish_ledger(self):
        s = self._sess()
        self.mo.record_publish(s["marathon_session_id"], {"status": "REMOTE_PROCESSING", "job_id": 1}, data_dir=self.data_dir)
        self.assertEqual(self.mo.read_ledger(s["marathon_session_id"], "publish", data_dir=self.data_dir)[0]["status"], "REMOTE_PROCESSING")

    def test_F06_schedule_ledger(self):
        s = self._sess()
        self.mo.record_schedule(s["marathon_session_id"], {"status": "SCHEDULED", "timezone": "UTC"}, data_dir=self.data_dir)
        self.assertEqual(self.mo.read_ledger(s["marathon_session_id"], "schedule", data_dir=self.data_dir)[0]["status"], "SCHEDULED")

    def test_F07_quality_ledger(self):
        s = self._sess()
        self.mo.record_quality(s["marathon_session_id"], {"status": "UNKNOWN"}, data_dir=self.data_dir)
        self.assertEqual(self.mo.read_ledger(s["marathon_session_id"], "quality", data_dir=self.data_dir)[0]["status"], "UNKNOWN")

    def test_F08_lifecycle_fanout_bound(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        self.mo.bind_job(sid, 99, login_id="cust_a", data_dir=self.data_dir)
        self.mo._ACTIVE_SESSIONS[sid] = {"login_id": "cust_a", "run_id": s["run_id"], "data_dir": str(self.data_dir)}
        before = len(self.mo.read_ledger(sid, "timeline", data_dir=self.data_dir))
        self.mo.on_lifecycle_event(99, {"type": "JOB_STARTED", "status": "OK"})
        after = len(self.mo.read_ledger(sid, "timeline", data_dir=self.data_dir))
        self.assertGreater(after, before)

    def test_F09_lifecycle_fanout_unbound_noop(self):
        s = self._sess()
        before = len(self.mo.read_ledger(s["marathon_session_id"], "timeline", data_dir=self.data_dir))
        self.mo.on_lifecycle_event(12345, {"type": "JOB_STARTED"})
        after = len(self.mo.read_ledger(s["marathon_session_id"], "timeline", data_dir=self.data_dir))
        self.assertEqual(before, after)


# ---- G: watchdog ----
class G_WatchdogTests(C10Base):
    def test_G01_waiting_for_remote_processing(self):
        clf = self.mo.classify_watchdog(current_state="REMOTE_PROCESSING", last_event_age_sec=900, interval_sec=600)
        self.assertEqual(clf["classification"], "WAITING")

    def test_G02_stuck_on_silence(self):
        clf = self.mo.classify_watchdog(current_state="RUNNING", last_event_age_sec=1300, interval_sec=600, progress_seen=False)
        self.assertEqual(clf["classification"], "STUCK")

    def test_G03_progressing(self):
        clf = self.mo.classify_watchdog(current_state="RUNNING", last_event_age_sec=10, interval_sec=600, progress_seen=True)
        self.assertEqual(clf["classification"], "PROGRESSING")

    def test_G04_completed(self):
        clf = self.mo.classify_watchdog(current_state="PUBLISHED", last_event_age_sec=9999, completed=True)
        self.assertEqual(clf["classification"], "COMPLETED")

    def test_G05_failed(self):
        clf = self.mo.classify_watchdog(current_state="FAILED", last_event_age_sec=10, failed=True)
        self.assertEqual(clf["classification"], "FAILED")

    def test_G06_unknown(self):
        clf = self.mo.classify_watchdog(current_state="UNKNOWN", last_event_age_sec=None)
        self.assertEqual(clf["classification"], "UNKNOWN")

    def test_G07_scheduled_waiting(self):
        clf = self.mo.classify_watchdog(current_state="GENERATING", last_event_age_sec=900, scheduler_waiting=True)
        self.assertEqual(clf["classification"], "WAITING")

    def test_G08_run_watchdog_persists(self):
        s = self._sess()
        out = self.mo.run_watchdog_check(s["marathon_session_id"], data_dir=self.data_dir)
        self.assertTrue(out["ok"])
        self.assertIn(out["alert"]["classification"], self.mo.WATCHDOG_STATES)
        self.assertFalse(out["alert"]["modifies_production"])
        self.assertEqual(len(self.mo.read_ledger(s["marathon_session_id"], "watchdog", data_dir=self.data_dir)), 1)

    def test_G09_alert_fields(self):
        s = self._sess()
        alert = self.mo.run_watchdog_check(s["marathon_session_id"], data_dir=self.data_dir)["alert"]
        for k in ("run_id", "classification", "confidence", "recommended_diagnostic_action"):
            self.assertIn(k, alert)

    def test_G10_silence_not_always_stuck(self):
        clf = self.mo.classify_watchdog(current_state="APPROVAL_PENDING", last_event_age_sec=2000, interval_sec=600)
        self.assertEqual(clf["classification"], "WAITING")


# ---- H: anomalies ----
class H_AnomalyTests(C10Base):
    def test_H01_duplicate_calls(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        # force same mono second by patching
        with patch.object(self.mo, "_mono", return_value=100.0):
            self.mo.record_api_call(sid, provider="m", operation="v", status="OK", latency_ms=1, scene_id="s", beat_id="b", data_dir=self.data_dir)
            self.mo.record_api_call(sid, provider="m", operation="v", status="OK", latency_ms=1, scene_id="s", beat_id="b", data_dir=self.data_dir)
        findings = self.mo.detect_anomalies(sid, data_dir=self.data_dir)
        self.assertTrue(any(f["rule"] == "unexpected_duplicate_provider_calls" for f in findings))

    def test_H02_long_latency(self):
        s = self._sess()
        self.mo.record_api_call(s["marathon_session_id"], provider="m", operation="v", status="OK", latency_ms=130000, data_dir=self.data_dir)
        self.assertTrue(any(f["rule"] == "unusually_long_provider_latency" for f in self.mo.detect_anomalies(s["marathon_session_id"], data_dir=self.data_dir)))

    def test_H03_repeated_retries(self):
        s = self._sess()
        self.mo.record_api_call(s["marathon_session_id"], provider="m", operation="v", status="FAIL", latency_ms=1, retry_count=4, data_dir=self.data_dir)
        self.assertTrue(any(f["rule"] == "repeated_retries" for f in self.mo.detect_anomalies(s["marathon_session_id"], data_dir=self.data_dir)))

    def test_H04_unknown_promoted(self):
        s = self._sess()
        self.mo.record_state_transition(s["marathon_session_id"], from_state="UNKNOWN", to_state="PUBLISHED", data_dir=self.data_dir)
        self.assertTrue(any(f["rule"] == "unknown_promoted_to_success" for f in self.mo.detect_anomalies(s["marathon_session_id"], data_dir=self.data_dir)))

    def test_H05_cross_customer(self):
        s = self._sess()
        self.mo.record_evidence(
            s["marathon_session_id"],
            ledger="timeline",
            stage="X",
            component="c",
            operation="o",
            event_type="E",
            metadata={"login_id": "other_customer"},
            data_dir=self.data_dir,
        )
        self.assertTrue(any(f["rule"] == "cross_customer_reference" for f in self.mo.detect_anomalies(s["marathon_session_id"], data_dir=self.data_dir)))

    def test_H06_duration_mismatch(self):
        s = self._sess()
        self.mo.record_visual_artifact(
            s["marathon_session_id"],
            {"asset_id": "a", "expected_duration": 10, "actual_duration": 40},
            data_dir=self.data_dir,
        )
        self.assertTrue(any(f["rule"] == "artifact_duration_mismatch" for f in self.mo.detect_anomalies(s["marathon_session_id"], data_dir=self.data_dir)))

    def test_H07_published_without_confirmation(self):
        s = self._sess()
        self.mo.record_publish(
            s["marathon_session_id"],
            {"status": "PUBLISHED", "authoritative_confirmation": False},
            data_dir=self.data_dir,
        )
        self.assertTrue(
            any(f["rule"] == "published_without_authoritative_confirmation" for f in self.mo.detect_anomalies(s["marathon_session_id"], data_dir=self.data_dir))
        )

    def test_H08_terminal_then_execution(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        self.mo.record_state_transition(sid, from_state="RUNNING", to_state="PUBLISHED", data_dir=self.data_dir)
        self.mo.record_state_transition(sid, from_state="PUBLISHED", to_state="GENERATING", data_dir=self.data_dir)
        findings = self.mo.detect_anomalies(sid, data_dir=self.data_dir)
        self.assertTrue(any(f["rule"] in ("terminal_state_followed_by_execution", "state_regression") for f in findings))


# ---- I: isolation / intervention ----
class I_IsolationInterventionTests(C10Base):
    def test_I01_owner_ok(self):
        s = self._sess()
        self.assertTrue(self.mo.assert_session_owner(s["marathon_session_id"], "cust_a", data_dir=self.data_dir)["ok"])

    def test_I02_owner_fail(self):
        s = self._sess()
        out = self.mo.assert_session_owner(s["marathon_session_id"], "cust_b", data_dir=self.data_dir)
        self.assertEqual(out["error_code"], "OWNERSHIP_FAILURE")

    def test_I03_project_denied(self):
        s = self._sess()
        out = self.mo.project_session_for_customer(s["marathon_session_id"], "cust_b", data_dir=self.data_dir)
        self.assertFalse(out["ok"])

    def test_I04_intervention_record_only(self):
        s = self._sess()
        out = self.mo.record_intervention(s["marathon_session_id"], step="DETECT", classification="STUCK", proposal="inspect", data_dir=self.data_dir)
        self.assertTrue(out["ok"])

    def test_I05_intervention_apply_forbidden(self):
        s = self._sess()
        out = self.mo.record_intervention(
            s["marathon_session_id"], step="PROPOSE_MINIMAL_FIX", classification="STUCK", proposal="patch", applied=True, data_dir=self.data_dir
        )
        self.assertEqual(out["error_code"], "SAFE_AUTO_REPAIR_BOUNDARY")

    def test_I06_invalid_intervention_step(self):
        s = self._sess()
        out = self.mo.record_intervention(s["marathon_session_id"], step="HACK", classification="X", data_dir=self.data_dir)
        self.assertFalse(out["ok"])


# ---- J: metrics / report / smoke ----
class J_MetricsReportSmokeTests(C10Base):
    def test_J01_metrics_counts(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        self.mo.record_api_call(sid, provider="m", operation="a", status="OK", latency_ms=10, data_dir=self.data_dir)
        self.mo.record_api_call(sid, provider="m", operation="b", status="OK", latency_ms=20, data_dir=self.data_dir)
        m = self.mo.compute_metrics(sid, data_dir=self.data_dir)
        self.assertEqual(m["api_call_count"], 2)
        self.assertFalse(m["fabricated"])
        self.assertEqual(m["paid_call_count"], 0)

    def test_J02_p50(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        for lat in (10, 20, 30):
            self.mo.record_api_call(sid, provider="m", operation="a", status="OK", latency_ms=lat, data_dir=self.data_dir)
        m = self.mo.compute_metrics(sid, data_dir=self.data_dir)
        self.assertEqual(m["provider_latency_p50_ms"], 20)

    def test_J03_report_sections(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        self.mo.finish_session(sid, status="COMPLETED", data_dir=self.data_dir)
        out = self.mo.generate_marathon_report(sid, data_dir=self.data_dir, docs_root=self.docs_root)
        self.assertTrue(out["ok"])
        text = Path(out["path"]).read_text(encoding="utf-8")
        for n in range(1, 36):
            self.assertIn(f"## {n}.", text)

    def test_J04_report_no_secrets(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        self.mo.record_evidence(
            sid, ledger="timeline", stage="X", component="c", operation="o", event_type="E", metadata={"api_key": "secret-value"}, data_dir=self.data_dir
        )
        out = self.mo.generate_marathon_report(sid, data_dir=self.data_dir, docs_root=self.docs_root)
        # secrets redacted in ledger; report must not echo raw secret
        ledger = json.dumps(self.mo.read_ledger(sid, "timeline", data_dir=self.data_dir))
        self.assertIn("[redacted]", ledger)
        text = Path(out["path"]).read_text(encoding="utf-8")
        self.assertNotIn("secret-value", text)

    def test_J05_offline_smoke(self):
        out = self.mo.run_offline_smoke(data_dir=self.data_dir, docs_root=self.docs_root)
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["cases"]), 2)
        self.assertEqual(out["paid_api_calls"], 0)
        self.assertFalse(out["executed_real_marathon"])
        types = {c["video_type"] for c in out["cases"]}
        self.assertEqual(types, {"LONG", "SHORT"})

    def test_J06_smoke_reports_exist(self):
        out = self.mo.run_offline_smoke(data_dir=self.data_dir, docs_root=self.docs_root)
        for c in out["cases"]:
            self.assertTrue(Path(c["report_path"]).is_file())


# ---- K: authority / contract guards ----
class K_AuthorityGuardTests(C10Base):
    def test_K01_module_no_idempotency_store(self):
        src = Path(self.mo.__file__).read_text(encoding="utf-8")
        self.assertNotIn("class IdempotencyStore", src)

    def test_K02_module_no_scheduler_service(self):
        src = Path(self.mo.__file__).read_text(encoding="utf-8")
        self.assertNotIn("class SchedulerService", src)

    def test_K03_detect_duplicate_engines_helper(self):
        hits = self.mo.detect_duplicate_engines("class IdempotencyStore:\n    pass\n")
        self.assertIn("second_idempotency_store", hits)

    def test_K04_owns_production_false(self):
        s = self._sess()
        self.assertFalse(s.get("owns_production"))

    def test_K05_no_real_marathon_in_smoke(self):
        src = inspect.getsource(self.mo.run_offline_smoke)
        self.assertIn("executed_real_marathon", inspect.getsource(self.mo.run_offline_smoke) + "False")
        self.assertNotIn("allow_live_provider", src)

    def test_K06_watchdog_interval_default(self):
        self.assertEqual(self.mo.WATCHDOG_DEFAULT_INTERVAL_SEC, 600)

    def test_K07_intervention_steps_complete(self):
        for step in ("DETECT", "COLLECT_EVIDENCE", "CLASSIFY", "PROPOSE_MINIMAL_FIX", "RUN_TARGETED_TEST", "VALIDATE", "RESUME"):
            self.assertIn(step, self.mo.INTERVENTION_STEPS)


# ---- L: expanded matrix to exceed 150 ----
class L_ExpandedMatrixTests(C10Base):
    def test_L01_locale_default(self):
        self.assertEqual(self._sess()["locale"], "en")

    def test_L02_timezone_default(self):
        self.assertEqual(self._sess()["timezone"], "UTC")

    def test_L03_environment(self):
        s = self.mo.create_marathon_session(
            login_id="a", test_case_id="MARATHON_SHORT", video_type="SHORT", environment="lab", data_dir=self.data_dir
        )
        self.assertEqual(s["environment"], "lab")

    def test_L04_finish_missing_session(self):
        self.assertFalse(self.mo.finish_session("missing", data_dir=self.data_dir).get("ok"))

    def test_L05_bind_missing_session(self):
        self.assertFalse(self.mo.bind_job("missing", 1, data_dir=self.data_dir).get("ok"))

    def test_L06_unbind_job(self):
        s = self._sess()
        self.mo.bind_job(s["marathon_session_id"], 7, login_id="cust_a", data_dir=self.data_dir)
        self.mo.unbind_job(7)
        self.assertNotIn(7, self.mo._JOB_BINDINGS)

    def test_L07_read_empty_ledger(self):
        s = self._sess()
        self.assertEqual(self.mo.read_ledger(s["marathon_session_id"], "repair", data_dir=self.data_dir), [])

    def test_L08_verify_empty_ok(self):
        s = self._sess()
        self.assertTrue(self.mo.verify_ledger_integrity(s["marathon_session_id"], "repair", data_dir=self.data_dir)["ok"])

    def test_L09_healthy_fresh(self):
        clf = self.mo.classify_watchdog(current_state="RUNNING", last_event_age_sec=5, interval_sec=600)
        self.assertEqual(clf["classification"], "HEALTHY")

    def test_L10_slow(self):
        clf = self.mo.classify_watchdog(current_state="RUNNING", last_event_age_sec=700, interval_sec=600)
        self.assertEqual(clf["classification"], "SLOW")

    def test_L11_provider_pending_waiting(self):
        clf = self.mo.classify_watchdog(current_state="RUNNING", last_event_age_sec=900, provider_pending=True)
        self.assertEqual(clf["classification"], "WAITING")

    def test_L12_upload_accepted_wait(self):
        clf = self.mo.classify_watchdog(current_state="UPLOAD_ACCEPTED", last_event_age_sec=2000)
        self.assertEqual(clf["classification"], "WAITING")

    def test_L13_api_http_status(self):
        s = self._sess()
        self.mo.record_api_call(
            s["marathon_session_id"], provider="m", operation="u", status="OK", latency_ms=1, http_status=200, data_dir=self.data_dir
        )
        self.assertEqual(self.mo.read_ledger(s["marathon_session_id"], "api", data_dir=self.data_dir)[0]["metadata"]["http_status"], 200)

    def test_L14_api_timeout_flag(self):
        s = self._sess()
        self.mo.record_api_call(
            s["marathon_session_id"], provider="m", operation="u", status="FAIL", latency_ms=1, timeout=True, error_classification="TIMEOUT", data_dir=self.data_dir
        )
        meta = self.mo.read_ledger(s["marathon_session_id"], "api", data_dir=self.data_dir)[0]["metadata"]
        self.assertTrue(meta["timeout"])

    def test_L15_paid_flag_metric(self):
        s = self._sess()
        self.mo.record_api_call(s["marathon_session_id"], provider="m", operation="u", status="OK", latency_ms=1, paid=True, data_dir=self.data_dir)
        self.assertEqual(self.mo.compute_metrics(s["marathon_session_id"], data_dir=self.data_dir)["paid_call_count"], 1)

    def test_L16_cache_reuse_metric(self):
        s = self._sess()
        self.mo.record_api_call(s["marathon_session_id"], provider="m", operation="u", status="OK", latency_ms=1, cache_reuse=True, data_dir=self.data_dir)
        self.assertEqual(self.mo.compute_metrics(s["marathon_session_id"], data_dir=self.data_dir)["cache_reuse_count"], 1)

    def test_L17_repair_count_metric(self):
        s = self._sess()
        self.mo.record_repair(s["marathon_session_id"], {"repair_id": "x", "status": "OK"}, data_dir=self.data_dir)
        self.assertEqual(self.mo.compute_metrics(s["marathon_session_id"], data_dir=self.data_dir)["repair_count"], 1)

    def test_L18_image_video_counts(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        self.mo.record_visual_artifact(sid, {"actual_artifact_type": "image", "status": "OK"}, data_dir=self.data_dir)
        self.mo.record_visual_artifact(sid, {"actual_artifact_type": "video", "status": "OK"}, data_dir=self.data_dir)
        m = self.mo.compute_metrics(sid, data_dir=self.data_dir)
        self.assertEqual(m["image_count"], 1)
        self.assertEqual(m["video_clip_count"], 1)

    def test_L19_stuck_count(self):
        s = self._sess()
        # fabricate watchdog STUCK via record_evidence
        self.mo.record_evidence(
            s["marathon_session_id"], ledger="watchdog", stage="W", component="w", operation="c", event_type="WATCHDOG_CHECK", status="STUCK", data_dir=self.data_dir
        )
        self.assertEqual(self.mo.compute_metrics(s["marathon_session_id"], data_dir=self.data_dir)["stuck_count"], 1)

    def test_L20_prompt_entity_mismatch_rule(self):
        s = self._sess()
        self.mo.record_prompt(
            s["marathon_session_id"], provider="m", operation="v", prompt_text="x", data_dir=self.data_dir
        )
        # mutate metadata by writing anomaly via visual missing flag instead — add evidence with entity_mismatch
        self.mo.record_evidence(
            s["marathon_session_id"],
            ledger="prompts",
            stage="PROMPT",
            component="c",
            operation="o",
            event_type="PROMPT_CAPTURE",
            metadata={"entity_mismatch": True, "prompt_id": "pr_x"},
            data_dir=self.data_dir,
        )
        self.assertTrue(any(f["rule"] == "prompt_entity_mismatch" for f in self.mo.detect_anomalies(s["marathon_session_id"], data_dir=self.data_dir)))

    def test_L21_missing_artifact_rule(self):
        s = self._sess()
        self.mo.record_visual_artifact(s["marathon_session_id"], {"missing_expected_artifact": True}, data_dir=self.data_dir)
        self.assertTrue(any(f["rule"] == "missing_expected_artifact" for f in self.mo.detect_anomalies(s["marathon_session_id"], data_dir=self.data_dir)))

    def test_L22_unexpected_fps(self):
        s = self._sess()
        self.mo.record_visual_artifact(s["marathon_session_id"], {"unexpected_fps": True}, data_dir=self.data_dir)
        self.assertTrue(any(f["rule"] == "unexpected_fps" for f in self.mo.detect_anomalies(s["marathon_session_id"], data_dir=self.data_dir)))

    def test_L23_unexpected_resolution(self):
        s = self._sess()
        self.mo.record_visual_artifact(s["marathon_session_id"], {"unexpected_resolution": True}, data_dir=self.data_dir)
        self.assertTrue(any(f["rule"] == "unexpected_resolution" for f in self.mo.detect_anomalies(s["marathon_session_id"], data_dir=self.data_dir)))

    def test_L24_schedule_before_publishability(self):
        s = self._sess()
        self.mo.record_schedule(s["marathon_session_id"], {"status": "SCHEDULED"}, data_dir=self.data_dir)
        self.assertTrue(any(f["rule"] == "schedule_before_publishability" for f in self.mo.detect_anomalies(s["marathon_session_id"], data_dir=self.data_dir)))

    def test_L25_zero_progress_failures(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        self.mo.record_failure(sid, failure_code="A", stage="G", component="c", data_dir=self.data_dir)
        self.mo.record_failure(sid, failure_code="B", stage="G", component="c", data_dir=self.data_dir)
        self.assertTrue(any(f["rule"] == "zero_progress_interval" for f in self.mo.detect_anomalies(sid, data_dir=self.data_dir)))

    def test_L26_diagnostic_actions(self):
        self.assertIn("evidence", self.mo._diagnostic_action("STUCK").lower())

    def test_L27_report_verdict_keys(self):
        s = self._sess()
        self.mo.finish_session(s["marathon_session_id"], status="COMPLETED", data_dir=self.data_dir)
        out = self.mo.generate_marathon_report(s["marathon_session_id"], data_dir=self.data_dir, docs_root=self.docs_root)
        self.assertIn(out["verdict"], ("PASS", "PASS_WITH_LIMITATION", "FAIL"))

    def test_L28_session_report_copy(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        self.mo.generate_marathon_report(sid, data_dir=self.data_dir, docs_root=self.docs_root)
        self.assertTrue((self.mo.session_dir(sid, data_dir=self.data_dir) / "MARATHON_REPORT.md").is_file())

    def test_L29_marathon_root(self):
        root = self.mo.marathon_root(self.data_dir)
        self.assertTrue(root.is_dir())
        self.assertEqual(root.name, "marathon_runs")

    def test_L30_state_pipeline_sequence(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        seq = ["QUEUED", "CLAIMED", "RUNNING", "GENERATING", "VERIFYING", "REPAIRING", "RENDERING", "PREVIEW", "APPROVED"]
        prev = None
        for st in seq:
            self.mo.record_state_transition(sid, from_state=prev, to_state=st, data_dir=self.data_dir)
            prev = st
        rows = [r for r in self.mo.read_ledger(sid, "timeline", data_dir=self.data_dir) if r["event_type"] == "STATE_TRANSITION"]
        self.assertEqual(len(rows), len(seq))

    def test_L31_publish_states_distinct(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        for st in ("UPLOAD_ACCEPTED", "REMOTE_PROCESSING", "PUBLISHED"):
            self.mo.record_publish(sid, {"status": st, "authoritative_confirmation": st == "PUBLISHED"}, data_dir=self.data_dir)
        statuses = [r["status"] for r in self.mo.read_ledger(sid, "publish", data_dir=self.data_dir)]
        self.assertEqual(statuses, ["UPLOAD_ACCEPTED", "REMOTE_PROCESSING", "PUBLISHED"])

    def test_L32_schedule_missed(self):
        s = self._sess()
        self.mo.record_schedule(s["marathon_session_id"], {"status": "MISSED", "operation": "tick"}, data_dir=self.data_dir)
        self.assertEqual(self.mo.read_ledger(s["marathon_session_id"], "schedule", data_dir=self.data_dir)[0]["status"], "MISSED")

    def test_L33_redact_nested(self):
        out = self.mo.redact({"a": {"password": "x", "b": 1}})
        self.assertEqual(out["a"]["password"], "[redacted]")
        self.assertEqual(out["a"]["b"], 1)

    def test_L34_get_test_case_case_insensitive(self):
        self.assertTrue(self.mo.get_test_case("marathon_long").get("ok"))

    def test_L35_contract_version(self):
        self.assertTrue(self.mo.CONTRACT_VERSION.startswith("C10"))

    def test_L36_schema_version(self):
        self.assertIn("c10", self.mo.SCHEMA_VERSION)

    def test_L37_watchdog_on_publish_pending(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        self.mo.record_publish(sid, {"status": "REMOTE_PROCESSING"}, data_dir=self.data_dir)
        alert = self.mo.run_watchdog_check(sid, data_dir=self.data_dir)["alert"]
        self.assertEqual(alert["classification"], "WAITING")

    def test_L38_recovery_count(self):
        s = self._sess()
        self.mo.record_failure(
            s["marathon_session_id"], failure_code="X", stage="G", component="c", recovery_action="restart", data_dir=self.data_dir
        )
        self.assertEqual(self.mo.compute_metrics(s["marathon_session_id"], data_dir=self.data_dir)["recovery_count"], 1)

    def test_L39_subtitle_count(self):
        s = self._sess()
        self.mo.record_subtitle(s["marathon_session_id"], {"dialogue_id": "d"}, data_dir=self.data_dir)
        self.assertEqual(self.mo.compute_metrics(s["marathon_session_id"], data_dir=self.data_dir)["subtitle_count"], 1)

    def test_L40_audio_count(self):
        s = self._sess()
        self.mo.record_audio_artifact(s["marathon_session_id"], {"audio_id": "a"}, data_dir=self.data_dir)
        self.assertEqual(self.mo.compute_metrics(s["marathon_session_id"], data_dir=self.data_dir)["audio_count"], 1)

    def test_L41_prompt_count(self):
        s = self._sess()
        self.mo.record_prompt(s["marathon_session_id"], provider="m", operation="v", prompt_text="p", data_dir=self.data_dir)
        self.assertEqual(self.mo.compute_metrics(s["marathon_session_id"], data_dir=self.data_dir)["prompt_count"], 1)

    def test_L42_forged_session_project(self):
        out = self.mo.project_session_for_customer("ms_forged", "cust_a", data_dir=self.data_dir)
        self.assertFalse(out.get("ok"))

    def test_L43_render_ffprobe_fields(self):
        s = self._sess()
        self.mo.record_render(
            s["marathon_session_id"],
            {"status": "OK", "resolution": "1920x1080", "fps": 30, "codec": "h264", "file_size": 100},
            data_dir=self.data_dir,
        )
        meta = self.mo.read_ledger(s["marathon_session_id"], "render", data_dir=self.data_dir)[0]["metadata"]
        self.assertEqual(meta["fps"], 30)

    def test_L44_repair_fields(self):
        s = self._sess()
        self.mo.record_repair(
            s["marathon_session_id"],
            {
                "repair_id": "rp",
                "failure_reason": "av_desync",
                "repair_target": "audio",
                "pre_repair_status": "FAIL",
                "post_repair_status": "OK",
                "re_verification_result": "UNKNOWN",
            },
            data_dir=self.data_dir,
        )
        meta = self.mo.read_ledger(s["marathon_session_id"], "repair", data_dir=self.data_dir)[0]["metadata"]
        self.assertEqual(meta["repair_target"], "audio")

    def test_L45_failure_retry_owner(self):
        s = self._sess()
        self.mo.record_failure(
            s["marathon_session_id"],
            failure_code="PROVIDER_TEMP",
            stage="GEN",
            component="visual",
            retry_owner="customer_job_automation",
            data_dir=self.data_dir,
        )
        meta = self.mo.read_ledger(s["marathon_session_id"], "failures", data_dir=self.data_dir)[0]["metadata"]
        self.assertEqual(meta["retry_owner"], "customer_job_automation")

    def test_L46_long_case_max_runtime(self):
        tc = self.mo.get_test_case("MARATHON_LONG")["test_case"]
        self.assertGreaterEqual(tc["maximum_runtime_sec"], 3600)

    def test_L47_short_provider_mode_offline(self):
        tc = self.mo.get_test_case("MARATHON_SHORT")["test_case"]
        self.assertEqual(tc["provider_mode"], "offline_mock")

    def test_L48_smoke_watchdog_classification_present(self):
        out = self.mo.run_offline_smoke(data_dir=self.data_dir, docs_root=self.docs_root)
        for c in out["cases"]:
            self.assertIn(c["watchdog"], self.mo.WATCHDOG_STATES)

    def test_L49_append_lifecycle_import_safe(self):
        # ensure fan-out import path exists without binding
        from app.customer_job_automation import append_lifecycle_event

        self.assertTrue(callable(append_lifecycle_event))

    def test_L50_no_blockchain(self):
        src = Path(self.mo.__file__).read_text(encoding="utf-8").lower()
        self.assertNotIn("blockchain", src)
        self.assertNotIn("web3", src)

    def test_L51_due_wait_state(self):
        clf = self.mo.classify_watchdog(current_state="DUE", last_event_age_sec=2000)
        self.assertEqual(clf["classification"], "WAITING")

    def test_L52_queued_wait_state(self):
        clf = self.mo.classify_watchdog(current_state="QUEUED", last_event_age_sec=2000)
        self.assertEqual(clf["classification"], "WAITING")

    def test_L53_preview_ready_wait(self):
        clf = self.mo.classify_watchdog(current_state="PREVIEW_READY", last_event_age_sec=2000)
        self.assertEqual(clf["classification"], "WAITING")

    def test_L54_bind_work_dir(self):
        s = self._sess()
        wd = self.td / "wd3"
        wd.mkdir()
        out = self.mo.bind_work_dir(s["marathon_session_id"], wd, data_dir=self.data_dir)
        self.assertTrue(out["ok"])

    def test_L55_report_missing_session(self):
        out = self.mo.generate_marathon_report("missing", data_dir=self.data_dir, docs_root=self.docs_root)
        self.assertFalse(out.get("ok"))

    def test_L56_watchdog_missing_session(self):
        out = self.mo.run_watchdog_check("missing", data_dir=self.data_dir)
        self.assertFalse(out.get("ok"))

    def test_L57_publish_before_approval_finding(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        self.mo.record_publish(sid, {"status": "PUBLISHED", "authoritative_confirmation": True}, data_dir=self.data_dir)
        findings = self.mo.detect_anomalies(sid, data_dir=self.data_dir)
        self.assertTrue(any(f["rule"] == "publish_before_approval" for f in findings))

    def test_L58_completed_status_watchdog(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        self.mo.finish_session(sid, status="COMPLETED", data_dir=self.data_dir)
        alert = self.mo.run_watchdog_check(sid, data_dir=self.data_dir)["alert"]
        self.assertEqual(alert["classification"], "COMPLETED")

    def test_L59_failed_terminal_watchdog(self):
        clf = self.mo.classify_watchdog(current_state="CANCELLED", last_event_age_sec=1)
        self.assertEqual(clf["classification"], "FAILED")

    def test_L60_api_request_id_auto(self):
        s = self._sess()
        out = self.mo.record_api_call(s["marathon_session_id"], provider="m", operation="x", status="OK", latency_ms=1, data_dir=self.data_dir)
        self.assertTrue(str(out["record"]["request_id"]).startswith("req_"))

    def test_L61_dialogue_in_prompt(self):
        s = self._sess()
        out = self.mo.record_prompt(
            s["marathon_session_id"], provider="m", operation="v", prompt_text="p", dialogue_id="d9", data_dir=self.data_dir
        )
        self.assertEqual(out["record"]["metadata"]["dialogue_id"], "d9")

    def test_L62_continuity_context(self):
        s = self._sess()
        out = self.mo.record_prompt(
            s["marathon_session_id"], provider="m", operation="v", prompt_text="p", continuity_context={"prev": "s0"}, data_dir=self.data_dir
        )
        self.assertEqual(out["record"]["metadata"]["continuity_context"]["prev"], "s0")

    def test_L63_visual_lineage(self):
        s = self._sess()
        self.mo.record_visual_artifact(s["marathon_session_id"], {"asset_id": "x", "lineage": "parent", "fps": 24, "width": 1280, "height": 720}, data_dir=self.data_dir)
        meta = self.mo.read_ledger(s["marathon_session_id"], "visual", data_dir=self.data_dir)[0]["metadata"]
        self.assertEqual(meta["width"], 1280)

    def test_L64_audio_channels(self):
        s = self._sess()
        self.mo.record_audio_artifact(s["marathon_session_id"], {"audio_id": "a", "channels": 1, "codec": "mp3"}, data_dir=self.data_dir)
        meta = self.mo.read_ledger(s["marathon_session_id"], "audio", data_dir=self.data_dir)[0]["metadata"]
        self.assertEqual(meta["channels"], 1)

    def test_L65_subtitle_locale(self):
        s = self._sess()
        self.mo.record_subtitle(s["marathon_session_id"], {"locale": "bn", "dialogue_id": "d"}, data_dir=self.data_dir)
        self.assertEqual(self.mo.read_ledger(s["marathon_session_id"], "subtitles", data_dir=self.data_dir)[0]["metadata"]["locale"], "bn")

    def test_L66_quality_unknown_not_success(self):
        s = self._sess()
        self.mo.record_quality(s["marathon_session_id"], {"status": "UNKNOWN"}, data_dir=self.data_dir)
        self.assertEqual(self.mo.read_ledger(s["marathon_session_id"], "quality", data_dir=self.data_dir)[0]["status"], "UNKNOWN")

    def test_L67_intervention_collect_evidence(self):
        s = self._sess()
        out = self.mo.record_intervention(s["marathon_session_id"], step="COLLECT_EVIDENCE", classification="STUCK", data_dir=self.data_dir)
        self.assertTrue(out["ok"])

    def test_L68_intervention_validate(self):
        s = self._sess()
        out = self.mo.record_intervention(s["marathon_session_id"], step="VALIDATE", classification="HEALTHY", data_dir=self.data_dir)
        self.assertTrue(out["ok"])

    def test_L69_p95_present(self):
        s = self._sess()
        sid = s["marathon_session_id"]
        for lat in (5, 10, 15, 20, 100):
            self.mo.record_api_call(sid, provider="m", operation="a", status="OK", latency_ms=lat, data_dir=self.data_dir)
        m = self.mo.compute_metrics(sid, data_dir=self.data_dir)
        self.assertIsNotNone(m["provider_latency_p95_ms"])

    def test_L70_failure_count_metric(self):
        s = self._sess()
        self.mo.record_failure(s["marathon_session_id"], failure_code="X", stage="G", component="c", data_dir=self.data_dir)
        self.assertEqual(self.mo.compute_metrics(s["marathon_session_id"], data_dir=self.data_dir)["failure_count"], 1)

    def test_L71_watchdog_count_metric(self):
        s = self._sess()
        self.mo.run_watchdog_check(s["marathon_session_id"], data_dir=self.data_dir)
        self.assertEqual(self.mo.compute_metrics(s["marathon_session_id"], data_dir=self.data_dir)["watchdog_count"], 1)

    def test_L72_source_ref_on_evidence(self):
        s = self._sess()
        out = self.mo.record_evidence(
            s["marathon_session_id"], ledger="timeline", stage="S", component="c", operation="o", event_type="E", source_ref="src1", data_dir=self.data_dir
        )
        self.assertEqual(out["record"]["source_ref"], "src1")

    def test_L73_job_id_on_api(self):
        s = self._sess()
        out = self.mo.record_api_call(s["marathon_session_id"], provider="m", operation="x", status="OK", latency_ms=1, job_id=55, data_dir=self.data_dir)
        self.assertEqual(out["record"]["job_id"], 55)

    def test_L74_active_sessions_registered(self):
        s = self._sess()
        self.assertIn(s["marathon_session_id"], self.mo._ACTIVE_SESSIONS)

    def test_L75_redact_list(self):
        out = self.mo.redact([{"api_key": "x"}, 1])
        self.assertEqual(out[0]["api_key"], "[redacted]")
        self.assertEqual(out[1], 1)


if __name__ == "__main__":
    unittest.main()
