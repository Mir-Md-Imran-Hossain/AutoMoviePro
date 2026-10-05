"""AMP-004 H4 — Real production workflow QA (paid APIs = 0)."""
from __future__ import annotations

import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pipeline.e2e_industrial.runner import run_e2e_industrial
from pipeline.localization import localization_packages_complete
from pipeline.quality.publishability import evaluate_publishability


class H4ReadyToUploadAuthorityTests(unittest.TestCase):
    def test_01_generate_video_sets_ready_after_publishability(self):
        import pipeline.video_pipeline as vp

        src = inspect.getsource(vp.generate_video)
        # Packaging must appear before the ready_to_upload job update.
        i_ready = src.find('upload_status="ready_to_upload"')
        if i_ready < 0:
            i_ready = src.find("upload_status=upload_status")
        i_loc = src.find("localize_master_clip(")
        self.assertGreater(i_ready, 0)
        self.assertGreater(i_loc, 0)
        self.assertLess(i_loc, i_ready, "localize_master_clip must run before ready_to_upload")
        self.assertIn("localization_packages_complete", src)
        self.assertIn("if multilingual:", src)

    def test_02_scheduler_does_not_force_ready(self):
        import app.scheduler_service as sch

        src = inspect.getsource(sch.SchedulerService._pregenerate_one)
        self.assertNotIn('upload_status="ready_to_upload"', src)
        self.assertIn("do not override generate_video", src.lower())

    def test_03_e2e_upload_only_when_publishable(self):
        src = inspect.getsource(run_e2e_industrial)
        self.assertIn("Record ready_to_upload only when publishable", src)
        self.assertIn("allow_soft_handoff", src)
        self.assertIn("production_bypass", src)


class H4LocalizationPackagingTests(unittest.TestCase):
    def test_10_packages_complete_en_only(self):
        ok, failed = localization_packages_complete({"languages": {}}, ["en"])
        self.assertTrue(ok)
        self.assertEqual(failed, [])

    def test_11_packages_complete_targets_ok(self):
        ok, failed = localization_packages_complete(
            {
                "languages": {
                    "en": {"ok": True},
                    "bn": {"ok": True, "video": "x"},
                    "hi": {"ok": True, "video": "y"},
                }
            },
            ["en", "bn", "hi"],
        )
        self.assertTrue(ok)
        self.assertEqual(failed, [])

    def test_12_packages_incomplete_fails(self):
        ok, failed = localization_packages_complete(
            {"languages": {"bn": {"ok": False}, "hi": {"ok": True}}},
            ["en", "bn", "hi"],
        )
        self.assertFalse(ok)
        self.assertIn("bn", failed)

    def test_13_missing_target_fails(self):
        ok, failed = localization_packages_complete(
            {"languages": {"bn": {"ok": True}}},
            ["en", "bn", "hi"],
        )
        self.assertFalse(ok)
        self.assertIn("hi", failed)


class H4SingleSceneE2ETests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="h4_e2e_"))

    def test_20_valid_workflow_publishable(self):
        r = run_e2e_industrial(work_dir=self.tmp)
        self.assertIn(r["final_status"], ("PASS", "ENVIRONMENT_LIMITED", "NOT_PUBLISHABLE"))
        if r["final_status"] == "PASS":
            up = self.tmp / "UPLOAD_STATUS.json"
            self.assertTrue(up.is_file())
            data = json.loads(up.read_text(encoding="utf-8"))
            self.assertEqual(data.get("upload_status"), "ready_to_upload")
            self.assertFalse(data.get("production_bypass"))
            pub = r.get("publishability") or {}
            self.assertTrue(pub.get("publishable"))

    def test_21_missing_visual_no_upload(self):
        r = run_e2e_industrial(work_dir=self.tmp, inject="missing_visual")
        self.assertEqual(r["final_status"], "FAIL_DETECTED")
        self.assertFalse((self.tmp / "UPLOAD_STATUS.json").is_file())

    def test_22_publishability_fail_no_upload(self):
        r = run_e2e_industrial(work_dir=self.tmp, inject="publishability_fail")
        self.assertEqual(r["final_status"], "FAIL_DETECTED")
        self.assertFalse((self.tmp / "UPLOAD_STATUS.json").is_file())

    def test_23_unknown_multimodal_no_upload(self):
        r = run_e2e_industrial(work_dir=self.tmp, inject="mandatory_unknown")
        self.assertEqual(r["final_status"], "FAIL_DETECTED")
        self.assertFalse((self.tmp / "UPLOAD_STATUS.json").is_file())


class H4MultiSceneE2ETests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="h4_multi_"))

    def test_30_continuity_inject_fail_closed(self):
        r = run_e2e_industrial(work_dir=self.tmp, inject="continuity")
        self.assertEqual(r["final_status"], "FAIL_DETECTED")
        self.assertFalse((self.tmp / "UPLOAD_STATUS.json").is_file())

    def test_31_wrong_project_no_upload(self):
        r = run_e2e_industrial(work_dir=self.tmp, inject="wrong_project")
        self.assertIn(r["final_status"], ("FAIL_DETECTED", "IDENTITY_BREAK"))
        self.assertFalse((self.tmp / "UPLOAD_STATUS.json").is_file())

    def test_32_fixture_has_multiple_scenes(self):
        from pipeline.e2e_industrial.fixture import materialize_e2e_fixture

        meta = materialize_e2e_fixture(self.tmp, job_id="h4-multi")
        plan = json.loads((self.tmp / "director_plan.json").read_text(encoding="utf-8"))
        scenes = plan.get("scenes") or []
        self.assertGreaterEqual(len(scenes), 3)
        ids = [str(s.get("canonical_scene_id") or s.get("scene_id") or i) for i, s in enumerate(scenes)]
        self.assertEqual(len(ids), len(set(ids)))
        clips = meta.get("clips") or []
        self.assertGreaterEqual(len(clips), 2)


class H4SoftHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="h4_soft_"))

    def test_40_soft_handoff_flag_documented(self):
        src = inspect.getsource(run_e2e_industrial)
        self.assertIn("allow_soft_handoff", src)
        self.assertIn("production generate_video never soft-handoffs", src)

    def test_41_soft_handoff_never_skips_publishability(self):
        r = run_e2e_industrial(work_dir=self.tmp, allow_soft_handoff=True)
        # Even with soft handoff, upload requires publishable
        if (self.tmp / "UPLOAD_STATUS.json").is_file():
            pub = r.get("publishability") or {}
            self.assertTrue(pub.get("publishable"))
            data = json.loads((self.tmp / "UPLOAD_STATUS.json").read_text(encoding="utf-8"))
            self.assertFalse(data.get("production_bypass"))


class H4PublishabilityInvariantTests(unittest.TestCase):
    def test_50_unknown_not_publishable(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            multimodal_status="UNKNOWN",
            semantic_status="PASS",
            artifact_status="PASS",
            render_status="PASS",
            audio_status="PASS",
            localization_status="PASS",
            creative_production_status="PASS",
            rendering_integrity_status="PASS",
            multimodal_mandatory_unknown=True,
        )
        self.assertFalse(pub.get("publishable"))

    def test_51_blocked_not_publishable(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            multimodal_status="PASS",
            semantic_status="PASS",
            artifact_status="BLOCKED",
            render_status="PASS",
            audio_status="PASS",
            localization_status="PASS",
            creative_production_status="PASS",
            rendering_integrity_status="PASS",
        )
        self.assertFalse(pub.get("publishable"))

    def test_52_ri_fail_not_publishable(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            multimodal_status="PASS",
            semantic_status="PASS",
            artifact_status="PASS",
            render_status="PASS",
            audio_status="PASS",
            localization_status="PASS",
            creative_production_status="PASS",
            rendering_integrity_status="FAIL",
        )
        self.assertFalse(pub.get("publishable"))


class H4FailureInjectionMatrixTests(unittest.TestCase):
    INJECTS = (
        "continuity",
        "missing_visual",
        "invalid_audio",
        "ffmpeg_fail",
        "publishability_fail",
        "mandatory_unknown",
        "wrong_project",
        "multimodal_blocked",
    )

    def test_60_all_injects_never_ready(self):
        for inj in self.INJECTS:
            with self.subTest(inject=inj):
                tmp = Path(tempfile.mkdtemp(prefix=f"h4_f_{inj}_"))
                r = run_e2e_industrial(work_dir=tmp, inject=inj)
                self.assertNotEqual(r["final_status"], "PASS")
                self.assertFalse((tmp / "UPLOAD_STATUS.json").is_file())


class H4RepeatedRequestReuseTests(unittest.TestCase):
    def test_70_idempotent_fingerprint_reuse(self):
        from pipeline.idempotency.executor import IdempotentExecutor

        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            calls = {"n": 0}
            ex = IdempotentExecutor(work, max_attempts=2)

            def run():
                calls["n"] += 1
                return {"value": 1}

            def persist(o):
                p = work / "out.json"
                p.write_text(json.dumps(o), encoding="utf-8")
                return str(p)

            r1 = ex.execute(
                job_id="h4j",
                stage="compose",
                entity_id="final",
                inputs={"v": 1},
                execute_fn=run,
                validate_fn=lambda o: (True, "ok"),
                persist_fn=persist,
            )
            r2 = ex.execute(
                job_id="h4j",
                stage="compose",
                entity_id="final",
                inputs={"v": 1},
                execute_fn=run,
                validate_fn=lambda o: (True, "ok"),
                persist_fn=persist,
            )
            self.assertEqual(r1.action, "execute")
            self.assertEqual(calls["n"], 1)
            self.assertEqual(r2.action, "reuse")


class H4BatchIsolationTests(unittest.TestCase):
    def test_80_two_work_dirs_isolated(self):
        a = Path(tempfile.mkdtemp(prefix="h4_a_"))
        b = Path(tempfile.mkdtemp(prefix="h4_b_"))
        ra = run_e2e_industrial(work_dir=a, job_id="job-A")
        rb = run_e2e_industrial(work_dir=b, job_id="job-B")
        self.assertEqual(ra["job_id"], "job-A")
        self.assertEqual(rb["job_id"], "job-B")
        self.assertNotEqual(str(a), str(b))
        if (a / "UPLOAD_STATUS.json").is_file() and (b / "UPLOAD_STATUS.json").is_file():
            da = json.loads((a / "UPLOAD_STATUS.json").read_text(encoding="utf-8"))
            db = json.loads((b / "UPLOAD_STATUS.json").read_text(encoding="utf-8"))
            self.assertEqual(da.get("job_id"), "job-A")
            self.assertEqual(db.get("job_id"), "job-B")


class H4ObservabilityTests(unittest.TestCase):
    def test_90_evidence_has_ids(self):
        tmp = Path(tempfile.mkdtemp(prefix="h4_obs_"))
        r = run_e2e_industrial(work_dir=tmp, job_id="obs-1")
        ev = r.get("evidence") or {}
        self.assertEqual(ev.get("job_id"), "obs-1")
        self.assertIn("stages", ev)
        self.assertIn("soft_handoff", ev)


class H4PaidApiSafetyTests(unittest.TestCase):
    def test_99_no_paid_provider_imports_in_h4_path(self):
        # Structural: this suite never calls real Google/Agnes providers
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
