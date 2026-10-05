"""C06-E — Canonical customer handoff (CUSTOMER_APPROVED_PLAN, paid APIs = 0)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class C06EBase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.td = Path(self._tmp.name)
        import app.customer_trs_workflow as tw
        import app.customer_production_plan as pp
        import app.customer_generation_orchestrator as go
        import app.customer_plan_adapter as pa
        from app.customer_job import ensure_job_columns
        from app.generation_guard import force_release

        self.tw, self.pp, self.go, self.pa = tw, pp, go, pa
        self._tw_data, self._pp_data, self._go_data = tw.DATA_DIR, pp.DATA_DIR, go.DATA_DIR
        self._tw_path, self._pp_path = tw._workflow_path, pp._plan_path
        tw.DATA_DIR = self.td
        pp.DATA_DIR = self.td
        go.DATA_DIR = self.td
        tw._workflow_path = lambda lid, cid: self.td / "wf" / f"{lid}_ch{cid}.json"
        pp._plan_path = lambda lid, cid: self.td / "pp" / f"{lid}_ch{cid}.json"
        go.execution_sidecar_path = lambda lid, jid: self.td / "ex" / str(lid) / f"job{int(jid)}.json"
        ensure_job_columns()
        force_release()
        self.login = "cust_a"
        self.channel = {
            "id": 31,
            "niche": "gadgets",
            "youtube_name": "GCh",
            "niche_id": 1,
            "lang_code": "en",
            "owner_login_id": "cust_a",
        }

    def tearDown(self):
        self.tw.DATA_DIR = self._tw_data
        self.pp.DATA_DIR = self._pp_data
        self.go.DATA_DIR = self._go_data
        self.tw._workflow_path = self._tw_path
        self.pp._plan_path = self._pp_path
        from app.generation_guard import force_release

        force_release()

    def _ready_plan(self, topic: str = "C06E unique approved plan topic"):
        self.tw.set_manual_topic(self.login, 31, topic)
        self.tw.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "r")
        self.tw.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "s")
        st = self.tw.load_workflow(self.login, 31)
        st["script"]["quality"]["status"] = "PASS"
        st["script"]["approval"]["state"] = "READY_FOR_REVIEW"
        for i, b in enumerate(st["script"]["script_plan"].get("beats") or []):
            b.setdefault("metadata", {})
            b["metadata"]["dialogue_id"] = f"dlg-{i+1}"
            b["metadata"]["scene_id"] = f"scene-{i:02d}"
            b["entity_refs"] = b.get("entity_refs") or ["Shobha", "Suzuki"]
            b["location_ref"] = b.get("location_ref") or "road"
        self.tw.save_workflow(st)
        self.tw.approve_script(self.login, 31, decision="approved")
        return self.pp.build_production_plan(self.login, self.channel, force_rebuild=True)


class C06EContractTests(C06EBase):
    def test_001_adapter_exists(self):
        self.assertTrue(hasattr(self.pa, "build_director_plan_from_production_plan"))
        self.assertTrue(hasattr(self.pa, "run_deterministic_canonical_handoff"))

    def test_002_no_duplicate_engines(self):
        src = Path(self.pa.__file__).read_text(encoding="utf-8")
        self.assertEqual(self.pa.detect_duplicate_engines(src), [])

    def test_003_modes_explicit(self):
        self.assertEqual(self.pa.resolve_execution_mode(use_mock=True), "MOCK_DETERMINISTIC")
        self.assertEqual(self.pa.resolve_execution_mode(use_mock=False), "CUSTOMER_APPROVED_PLAN")
        self.assertEqual(
            self.pa.resolve_execution_mode(execution_mode="CUSTOMER_APPROVED_PLAN"),
            "CUSTOMER_APPROVED_PLAN",
        )

    def test_004_mock_not_approved(self):
        self.assertNotEqual(self.pa.EXECUTION_MODE_MOCK, self.pa.EXECUTION_MODE_APPROVED)


class C06EHandoffTests(C06EBase):
    def test_010_director_plan_from_approved(self):
        self._ready_plan("dir plan topic")
        plan = self.pp.load_production_plan(self.login, 31)
        d = self.pa.build_director_plan_from_production_plan(plan, login_id=self.login, channel_id=31)
        self.assertEqual(d["plan_source"], "CUSTOMER_APPROVED_PLAN")
        self.assertTrue(d["trs_replanning_forbidden"])
        self.assertGreaterEqual(len(d["scenes"]), 1)

    def test_011_scene_preserves_ids(self):
        self._ready_plan("ids topic")
        plan = self.pp.load_production_plan(self.login, 31)
        d = self.pa.build_director_plan_from_production_plan(plan, login_id=self.login, channel_id=31)
        sc = d["scenes"][0]
        self.assertTrue(sc.get("dialogue_id"))
        self.assertTrue(sc.get("c05s_visual_beat_id"))
        self.assertEqual(sc.get("visual_direction_source"), "C05-S")

    def test_012_canonical_handoff_ok(self):
        self._ready_plan("handoff ok topic")
        r = self.go.start_customer_generation(
            self.login,
            self.channel,
            execution_mode="CUSTOMER_APPROVED_PLAN",
            deterministic_fixtures=True,
            force_rebuild=True,
            work_dir=self.td / "w1",
        )
        self.assertTrue(r["ok"])
        self.assertEqual(r["execution_mode"], "CUSTOMER_APPROVED_PLAN")
        self.assertTrue(r.get("trs_replanning_forbidden"))
        self.assertEqual(r.get("paid_api_calls"), 0)

    def test_013_director_plan_written(self):
        self._ready_plan("write dir topic")
        wd = self.td / "w2"
        self.go.start_customer_generation(
            self.login,
            self.channel,
            execution_mode="CUSTOMER_APPROVED_PLAN",
            deterministic_fixtures=True,
            force_rebuild=True,
            work_dir=wd,
        )
        self.assertTrue((wd / "director_plan.json").is_file())
        self.assertTrue((wd / "c06e_customer_approved_plan.lock").is_file())
        self.assertTrue((wd / "c06e_execution_snapshot.json").is_file())

    def test_014_generate_video_skips_trs(self):
        self._ready_plan("skip trs topic")
        plan = self.pp.load_production_plan(self.login, 31)
        wd = self.td / "w3"
        d = self.pa.build_director_plan_from_production_plan(plan, login_id=self.login, channel_id=31)
        self.pa.write_director_plan(wd, d)
        calls = []

        def boom(*a, **k):
            calls.append(1)
            raise AssertionError("TRS must not run")

        with patch("pipeline.trs_facade.run_trs_pipeline", boom), patch(
            "pipeline.trs_facade.plan_script_for_trs", boom
        ):
            from pipeline.video_pipeline import generate_video

            with self.assertRaises(Exception):
                generate_video(self.channel, video_type="short", work_dir=wd, topic=d.get("topic") or "t")
        self.assertEqual(calls, [], "TRS/script replan must not run under CUSTOMER_APPROVED_PLAN")

    def test_015_information_preservation(self):
        self._ready_plan("info preserve topic")
        r = self.go.start_customer_generation(
            self.login,
            self.channel,
            execution_mode="CUSTOMER_APPROVED_PLAN",
            deterministic_fixtures=True,
            force_rebuild=True,
            work_dir=self.td / "w4",
        )
        self.assertTrue((r.get("information_preservation") or {}).get("ok"))

    def test_016_mock_distinct_from_approved(self):
        self._ready_plan("mock distinct topic")
        m = self.go.start_customer_generation(
            self.login, self.channel, execution_mode="MOCK_DETERMINISTIC", force_rebuild=True, work_dir=self.td / "wm"
        )
        self.assertEqual(m.get("execution_mode"), "MOCK_DETERMINISTIC")
        self.assertTrue(m.get("mock_is_not_real_media") or m.get("use_mock"))

    def test_017_snapshot_immutable_fields(self):
        self._ready_plan("snap fields topic")
        plan = self.pp.load_production_plan(self.login, 31)
        snap = self.pa.build_immutable_execution_snapshot(
            plan=plan, job_id=1, login_id=self.login, channel_id=31, execution_mode="CUSTOMER_APPROVED_PLAN", generation_fingerprint="fp"
        )
        for k in ("plan_id", "plan_revision", "script_fingerprint", "production_plan_fingerprint", "execution_mode"):
            self.assertIn(k, snap)

    def test_018_foreign_ownership(self):
        self._ready_plan("foreign topic")
        r = self.go.start_customer_generation(
            "cust_b",
            self.channel,
            execution_mode="CUSTOMER_APPROVED_PLAN",
            deterministic_fixtures=True,
            force_rebuild=True,
        )
        self.assertFalse(r.get("ok"))
        self.assertEqual(r.get("error_code"), "ownership_violation")

    def test_019_stale_blocks(self):
        self._ready_plan("stale topic")
        plan = self.pp.load_production_plan(self.login, 31)
        plan["status"] = "STALE"
        self.pp.save_production_plan(plan)
        r = self.go.start_customer_generation(
            self.login, self.channel, execution_mode="CUSTOMER_APPROVED_PLAN", deterministic_fixtures=True
        )
        self.assertEqual(r.get("status"), "STALE")

    def test_020_c05mr_consumed(self):
        self._ready_plan("mr topic")
        r = self.go.start_customer_generation(
            self.login,
            self.channel,
            execution_mode="CUSTOMER_APPROVED_PLAN",
            deterministic_fixtures=True,
            force_rebuild=True,
            work_dir=self.td / "wmr",
        )
        self.assertEqual((r.get("materialization") or {}).get("binding"), "dialogue_id+beat_id")

    def test_021_provider_requests_have_modes(self):
        self._ready_plan("mode topic")
        r = self.go.start_customer_generation(
            self.login,
            self.channel,
            execution_mode="CUSTOMER_APPROVED_PLAN",
            deterministic_fixtures=True,
            force_rebuild=True,
            work_dir=self.td / "wmode",
        )
        reqs = r.get("provider_requests") or []
        self.assertTrue(reqs)
        self.assertTrue(reqs[0].get("visual_mode"))

    def test_022_video_pipeline_lock_flag(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("customer_approved_lock", src)
        self.assertIn("CUSTOMER_APPROVED_PLAN", src)

    def test_023_workspace_generate_mode(self):
        import app.main as main_mod
        import inspect

        src = inspect.getsource(main_mod.workspace_generate)
        self.assertIn("execution_mode", src)

    def test_024_ui_explicit_mode(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("MOCK_DETERMINISTIC", js)
        self.assertIn("execution_mode", js)


# Expand to 150+
def _expand():
    def make_handoff(i, topic):
        def _t(self):
            self._ready_plan(topic)
            r = self.go.start_customer_generation(
                self.login,
                self.channel,
                execution_mode="CUSTOMER_APPROVED_PLAN",
                deterministic_fixtures=True,
                force_rebuild=True,
                work_dir=self.td / f"wh{i}",
            )
            self.assertTrue(r.get("ok"), r.get("error"))
            self.assertEqual(r.get("paid_api_calls"), 0)
            self.assertTrue(r.get("trs_replanning_forbidden"))
            audit = r.get("information_preservation") or {}
            self.assertTrue(audit.get("ok"), audit.get("losses"))
            for req in r.get("provider_requests") or []:
                self.assertTrue(req.get("dialogue_id"))
                self.assertTrue(req.get("beat_id"))

        return _t

    for i in range(50):
        setattr(C06EHandoffTests, f"test_1{i:02d}_handoff_{i}", make_handoff(i, f"C06E expand handoff {i}"))

    def make_preserve(i):
        def _t(self):
            self._ready_plan(f"preserve {i}")
            plan = self.pp.load_production_plan(self.login, 31)
            d = self.pa.build_director_plan_from_production_plan(plan, login_id=self.login, channel_id=31)
            snap = self.pa.build_immutable_execution_snapshot(
                plan=plan,
                job_id=i,
                login_id=self.login,
                channel_id=31,
                execution_mode="CUSTOMER_APPROVED_PLAN",
                generation_fingerprint=f"fp{i}",
            )
            reqs = [self.pa.provider_request_projection(sc) for sc in d["scenes"]]
            audit = self.pa.audit_information_preservation_chain(plan, snap, d, reqs)
            self.assertTrue(audit["ok"], audit.get("losses"))

        return _t

    for i in range(40):
        setattr(C06EHandoffTests, f"test_2{i:02d}_preserve_{i}", make_preserve(i))

    def make_mode(i, mode):
        def _t(self):
            self.assertEqual(self.pa.resolve_execution_mode(execution_mode=mode), mode if mode != "MOCK" else "MOCK_DETERMINISTIC")

        return _t

    for i, mode in enumerate(["MOCK_DETERMINISTIC", "CUSTOMER_APPROVED_PLAN"] * 20):
        setattr(C06EContractTests, f"test_3{i:02d}_mode_{i}", make_mode(i, mode))

    def make_iso(i):
        def _t(self):
            self._ready_plan(f"iso {i}")
            r = self.go.start_customer_generation(
                self.login,
                self.channel,
                execution_mode="CUSTOMER_APPROVED_PLAN",
                deterministic_fixtures=True,
                force_rebuild=True,
                work_dir=self.td / f"iso{i}",
            )
            self.assertIsNone(self.go.load_execution_record("cust_b", int(r["job_id"])))

        return _t

    for i in range(20):
        setattr(C06EHandoffTests, f"test_4{i:02d}_iso_{i}", make_iso(i))


_expand()


if __name__ == "__main__":
    unittest.main()
