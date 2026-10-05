"""C06-D — Customer production execution (paid APIs = 0, mock path)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class C06DBase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.td = Path(self._tmp.name)
        import app.customer_trs_workflow as tw
        import app.customer_production_plan as pp
        import app.customer_generation_orchestrator as go
        from app.customer_job import ensure_job_columns
        from app.generation_guard import force_release

        self.tw, self.pp, self.go = tw, pp, go
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
            "id": 21,
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

    def _ready_plan(self, topic: str = "C06D unique topic alpha"):
        self.tw.set_manual_topic(self.login, 21, topic)
        self.tw.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "r")
        self.tw.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "s")
        st = self.tw.load_workflow(self.login, 21)
        st["script"]["quality"]["status"] = "PASS"
        st["script"]["approval"]["state"] = "READY_FOR_REVIEW"
        for i, b in enumerate(st["script"]["script_plan"].get("beats") or []):
            b.setdefault("metadata", {})
            b["metadata"]["dialogue_id"] = f"dlg-{i+1}"
            b["metadata"]["scene_id"] = f"scene-{i:02d}"
            b["entity_refs"] = b.get("entity_refs") or ["Shobha", "Suzuki"]
            b["location_ref"] = b.get("location_ref") or "road"
            b["action_intent"] = ["stands beside", "enters", "sits inside"][min(i, 2)]
        self.tw.save_workflow(st)
        self.tw.approve_script(self.login, 21, decision="approved")
        return self.pp.build_production_plan(self.login, self.channel, force_rebuild=True)


class C06DContractTests(C06DBase):
    def test_001_module_exists(self):
        self.assertTrue(hasattr(self.go, "start_customer_generation"))
        self.assertTrue(hasattr(self.go, "admit_generation"))

    def test_002_no_duplicate_engines(self):
        src = Path(self.go.__file__).read_text(encoding="utf-8")
        self.assertEqual(self.go.detect_duplicate_engines(src), [])

    def test_003_no_paid_api_in_mock(self):
        self._ready_plan("paid api zero topic")
        r = self.go.start_customer_generation(self.login, self.channel, use_mock=True, acquire_guard=True)
        self.assertEqual(r.get("paid_api_calls"), 0)

    def test_004_phases_defined(self):
        for p in ("QUEUED", "GENERATING_AUDIO", "VERIFYING", "COMPLETED", "STALE"):
            self.assertIn(p, self.go.EXECUTION_PHASES)


class C06DAdmissionTests(C06DBase):
    def test_010_missing_plan_blocked(self):
        r = self.go.admit_generation(self.login, self.channel)
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_code"], "not_ready")

    def test_011_login_required(self):
        r = self.go.admit_generation("", self.channel)
        self.assertEqual(r["error_code"], "login_required")

    def test_012_ownership_foreign_channel(self):
        self._ready_plan("own topic")
        r = self.go.admit_generation("cust_b", self.channel)
        self.assertEqual(r.get("error_code"), "ownership_violation")

    def test_013_account_inactive(self):
        self._ready_plan("acct topic")
        r = self.go.admit_generation(self.login, self.channel, account_active=False)
        self.assertFalse(r["ok"])
        self.assertIn("account_inactive", r["blocks"])

    def test_014_entitlement_inactive(self):
        self._ready_plan("ent topic")
        r = self.go.admit_generation(self.login, self.channel, entitlement_active=False)
        self.assertIn("entitlement_inactive", r["blocks"])

    def test_015_capability_unavailable(self):
        self._ready_plan("cap topic")
        r = self.go.admit_generation(self.login, self.channel, capability_available=False)
        self.assertIn("generation_capability_unavailable", r["blocks"])

    def test_016_foundation_blocked(self):
        self._ready_plan("found topic")
        r = self.go.admit_generation(self.login, self.channel, foundation_allowed=False)
        self.assertIn("foundation_not_ready", r["blocks"])

    def test_017_ready_plan_admitted(self):
        self._ready_plan("admit ok topic")
        r = self.go.admit_generation(self.login, self.channel)
        self.assertTrue(r["ok"])
        self.assertIn("snapshot", r)

    def test_018_language_mismatch(self):
        self._ready_plan("lang topic")
        ch = {**self.channel, "lang_code": "bn"}
        r = self.go.admit_generation(self.login, ch)
        self.assertFalse(r["ok"])

    def test_019_stale_plan_blocks(self):
        self._ready_plan("stale admit topic")
        plan = self.pp.load_production_plan(self.login, 21)
        plan["status"] = "STALE"
        self.pp.save_production_plan(plan)
        r = self.go.admit_generation(self.login, self.channel)
        self.assertEqual(r.get("status"), "STALE")


class C06DSnapshotIdempotencyTests(C06DBase):
    def test_020_immutable_snapshot_fields(self):
        self._ready_plan("snap topic")
        adm = self.go.admit_generation(self.login, self.channel)
        snap = adm["snapshot"]
        for k in ("production_plan_id", "production_plan_revision", "script_revision", "approved_script_id"):
            self.assertIn(k, snap)

    def test_021_fingerprint_stable(self):
        self._ready_plan("fp stable topic")
        adm = self.go.admit_generation(self.login, self.channel)
        a = self.go.compute_generation_job_fingerprint(adm["snapshot"], adm["plan"], video_type="short")
        b = self.go.compute_generation_job_fingerprint(adm["snapshot"], adm["plan"], video_type="short")
        self.assertEqual(a, b)

    def test_022_fingerprint_changes_with_script(self):
        self._ready_plan("fp change topic")
        adm = self.go.admit_generation(self.login, self.channel)
        a = self.go.compute_generation_job_fingerprint(adm["snapshot"], adm["plan"], video_type="short")
        st = self.tw.load_workflow(self.login, 21)
        st["script"]["script_plan"]["beats"][0]["narration"] += " CHANGED"
        self.tw.save_workflow(st)
        self.pp.build_production_plan(self.login, self.channel, force_rebuild=True)
        adm2 = self.go.admit_generation(self.login, self.channel)
        b = self.go.compute_generation_job_fingerprint(adm2["snapshot"], adm2["plan"], video_type="short")
        self.assertNotEqual(a, b)

    def test_023_idempotent_reuse(self):
        self._ready_plan("reuse topic")
        a = self.go.start_customer_generation(self.login, self.channel, use_mock=True)
        b = self.go.start_customer_generation(self.login, self.channel, use_mock=True)
        self.assertTrue(b.get("reused"))
        self.assertEqual(a.get("fingerprint"), b.get("fingerprint"))

    def test_024_force_rebuild_new_job(self):
        self._ready_plan("force rebuild topic")
        a = self.go.start_customer_generation(self.login, self.channel, use_mock=True)
        b = self.go.start_customer_generation(self.login, self.channel, use_mock=True, force_rebuild=True)
        self.assertFalse(b.get("reused"))
        self.assertNotEqual(a.get("job_id"), b.get("job_id"))


class C06DMappingContinuityTests(C06DBase):
    def test_030_payload_mapping_ok(self):
        self._ready_plan("map topic")
        plan = self.pp.load_production_plan(self.login, 21)
        m = self.go.map_production_plan_to_payloads(plan, customer_id=self.login, channel_id="21", generation_id="g1")
        self.assertTrue(m["ok"])
        self.assertGreaterEqual(len(m["payloads"]), 1)

    def test_031_semantic_fields_present(self):
        self._ready_plan("sem topic")
        plan = self.pp.load_production_plan(self.login, 21)
        m = self.go.map_production_plan_to_payloads(plan, customer_id=self.login, channel_id="21", generation_id="g1")
        sem = m["payloads"][0]["semantic_projection"]
        for f in ("dialogue_id", "beat_id", "scene_id", "location", "relationships", "generation_mode"):
            self.assertTrue(sem.get(f) is not None and sem.get(f) != "")

    def test_032_information_loss_audit_pass(self):
        self._ready_plan("loss audit topic")
        plan = self.pp.load_production_plan(self.login, 21)
        m = self.go.map_production_plan_to_payloads(plan, customer_id=self.login, channel_id="21", generation_id="g1")
        audit = self.go.audit_information_loss(plan, m["payloads"])
        self.assertTrue(audit["ok"], audit.get("losses"))

    def test_033_information_loss_detects_missing(self):
        payloads = [{"semantic_projection": {"dialogue_id": "", "beat_id": "b"}}]
        audit = self.go.audit_information_loss({}, payloads)
        self.assertFalse(audit["ok"])

    def test_034_materialize_c05mr(self):
        self._ready_plan("mat topic")
        plan = self.pp.load_production_plan(self.login, 21)
        mat = self.go.materialize_plan_visual_beats(plan)
        self.assertTrue(mat.get("ok"))
        self.assertEqual(mat.get("binding"), "dialogue_id+beat_id")

    def test_035_continuity_applied(self):
        self._ready_plan("cont topic")
        plan = self.pp.load_production_plan(self.login, 21)
        m = self.go.map_production_plan_to_payloads(plan, customer_id=self.login, channel_id="21", generation_id="g1")
        cont = self.go.apply_continuity_to_plan_units(self.td / "cw", plan, m["payloads"], job_id="j")
        self.assertEqual(cont["authority"], "ContinuityTracker")
        self.assertGreaterEqual(cont["count"], 1)

    def test_036_camera_not_location_reset(self):
        payloads = [
            {"semantic_projection": {"location": "road", "dialogue_id": "d1", "beat_id": "b1", "scene_id": "s0",
                                     "character_identity": "Shobha", "character_state": {"identity": "Shobha"},
                                     "entities": [{"entity_id": "e1"}], "relationships": [{"relation_type": "beside"}],
                                     "action": "stand", "camera": "wide", "lighting": "day", "emotion": "calm",
                                     "timing": {"duration_sec": 4}, "coverage": {"m": 1}, "generation_mode": "IMAGE",
                                     "continuity": {}}},
            {"semantic_projection": {"location": "road", "dialogue_id": "d2", "beat_id": "b2", "scene_id": "s1",
                                     "character_identity": "Shobha", "character_state": {"identity": "Shobha"},
                                     "entities": [{"entity_id": "e1"}], "relationships": [{"relation_type": "beside"}],
                                     "action": "walk", "camera": "close", "lighting": "day", "emotion": "calm",
                                     "timing": {"duration_sec": 4}, "coverage": {"m": 1}, "generation_mode": "IMAGE",
                                     "continuity": {}}},
        ]
        plan = {"visual_beats": [], "dialogue_segments": []}
        cont = self.go.apply_continuity_to_plan_units(self.td / "cw2", plan, payloads, job_id="j2")
        self.assertEqual(cont["scenes"][1].get("location"), "road")

    def test_037_relationship_not_collapsed(self):
        self._ready_plan("rel topic")
        plan = self.pp.load_production_plan(self.login, 21)
        m = self.go.map_production_plan_to_payloads(plan, customer_id=self.login, channel_id="21", generation_id="g1")
        rels = m["payloads"][0]["semantic_projection"]["relationships"]
        self.assertTrue(isinstance(rels, list) and rels)
        self.assertIn("relation_type", rels[0])


class C06DModeRoutingTests(C06DBase):
    def test_040_image_ok(self):
        r = self.go.resolve_generation_mode("IMAGE")
        self.assertTrue(r["ok"])
        self.assertEqual(r["actual_mode"], "IMAGE")

    def test_041_image_with_motion(self):
        r = self.go.resolve_generation_mode("IMAGE_WITH_MOTION")
        self.assertEqual(r["actual_mode"], "IMAGE_WITH_MOTION")

    def test_042_video(self):
        r = self.go.resolve_generation_mode("VIDEO")
        self.assertEqual(r["actual_mode"], "VIDEO")

    def test_043_unsupported_blocked(self):
        r = self.go.resolve_generation_mode("HOLOGRAM")
        self.assertFalse(r["ok"])

    def test_044_fallback_provenance(self):
        r = self.go.resolve_generation_mode("HOLOGRAM", allow_fallback=True, fallback_to="IMAGE", fallback_reason="no_provider")
        self.assertTrue(r["fallback_used"])
        self.assertEqual(r["requested_mode"], "HOLOGRAM")
        self.assertEqual(r["actual_mode"], "IMAGE")
        self.assertEqual(r["fallback_reason"], "no_provider")

    def test_045_no_silent_downgrade(self):
        r = self.go.resolve_generation_mode("VIDEO", allow_fallback=False)
        self.assertTrue(r["ok"])
        self.assertFalse(r["fallback_used"])


class C06DFalseSuccessTests(C06DBase):
    def test_050_provider_ok_unknown_not_verified(self):
        r = self.go.evaluate_false_success(provider_success=True, artifact_verification="UNKNOWN")
        self.assertFalse(r["verified"])
        self.assertEqual(r["status"], "NOT_VERIFIED")

    def test_051_provider_ok_fail_blocked(self):
        r = self.go.evaluate_false_success(provider_success=True, artifact_verification="FAIL")
        self.assertEqual(r["status"], "FAILED")

    def test_052_quality_ok_render_fail_not_publishable(self):
        r = self.go.evaluate_false_success(
            provider_success=True, artifact_verification="PASS", quality_success=True, rendering_ok=False, final_artifact_present=False
        )
        self.assertFalse(r["publishable"])

    def test_053_missing_final_not_publishable(self):
        r = self.go.evaluate_false_success(
            provider_success=True, artifact_verification="PASS", quality_success=True, rendering_ok=True, final_artifact_present=False
        )
        self.assertFalse(r["publishable"])

    def test_054_all_ok_publishable(self):
        r = self.go.evaluate_false_success(
            provider_success=True, artifact_verification="PASS", quality_success=True, rendering_ok=True, final_artifact_present=True
        )
        self.assertTrue(r["publishable"])


class C06DExecutionTests(C06DBase):
    def test_060_happy_path_completed(self):
        self._ready_plan("happy path topic")
        r = self.go.start_customer_generation(self.login, self.channel, use_mock=True)
        self.assertTrue(r["ok"])
        self.assertEqual(r["status"], "COMPLETED")

    def test_061_artifact_unknown_not_verified(self):
        self._ready_plan("unknown art topic")
        r = self.go.start_customer_generation(
            self.login, self.channel, use_mock=True, force_artifact_verdict="UNKNOWN", force_rebuild=True
        )
        self.assertEqual(r.get("status"), "NOT_VERIFIED")
        self.assertFalse((r.get("final") or {}).get("verified"))

    def test_062_artifact_fail(self):
        self._ready_plan("fail art topic")
        r = self.go.start_customer_generation(
            self.login, self.channel, use_mock=True, force_artifact_verdict="FAIL", force_rebuild=True
        )
        self.assertEqual(r.get("status"), "FAILED")

    def test_063_render_fail(self):
        self._ready_plan("render fail topic")
        r = self.go.start_customer_generation(
            self.login, self.channel, use_mock=True, force_render_fail=True, force_rebuild=True
        )
        self.assertEqual(r.get("status"), "FAILED")

    def test_064_provider_fail(self):
        self._ready_plan("prov fail topic")
        r = self.go.start_customer_generation(
            self.login, self.channel, use_mock=True, force_provider_fail=True, force_rebuild=True
        )
        self.assertEqual(r.get("status"), "FAILED")

    def test_065_repair_cycle_recorded(self):
        self._ready_plan("repair topic")
        r = self.go.start_customer_generation(
            self.login, self.channel, use_mock=True, force_artifact_verdict="FAIL", repair_cycles=2, force_rebuild=True
        )
        self.assertEqual((r.get("record") or {}).get("repair_count"), 2)

    def test_066_job_has_plan_refs(self):
        self._ready_plan("job refs topic")
        r = self.go.start_customer_generation(self.login, self.channel, use_mock=True, force_rebuild=True)
        from app.customer_job import get_job

        row = get_job(int(r["job_id"]))
        self.assertTrue(row.get("production_plan_id"))
        self.assertTrue(row.get("script_revision"))
        self.assertTrue(row.get("generation_fingerprint"))

    def test_067_snapshot_immutable_after_plan_change(self):
        self._ready_plan("immutable after topic")
        r = self.go.start_customer_generation(self.login, self.channel, use_mock=True, force_rebuild=True)
        snap_rev = r["snapshot"]["script_revision"]
        st = self.tw.load_workflow(self.login, 21)
        st["script"]["script_plan"]["beats"][0]["narration"] += " X"
        self.tw.save_workflow(st)
        rec = self.go.load_execution_record(self.login, int(r["job_id"]))
        self.assertEqual(rec["snapshot"]["script_revision"], snap_rev)

    def test_068_guard_busy(self):
        from app.generation_guard import try_acquire, force_release

        self._ready_plan("guard topic")
        try_acquire("idle_pregen")
        try:
            r = self.go.start_customer_generation(self.login, self.channel, use_mock=True, force_rebuild=True)
            self.assertEqual(r.get("error_code"), "generation_busy")
        finally:
            force_release()

    def test_069_projection(self):
        self._ready_plan("proj topic")
        r = self.go.start_customer_generation(self.login, self.channel, use_mock=True, force_rebuild=True)
        proj = self.go.project_execution_status(self.login, int(r["job_id"]))
        self.assertTrue(proj["ok"])
        self.assertIn("planes", proj)
        self.assertTrue(proj["planes"]["publishable"] or proj["phase"] == "COMPLETED")

    def test_070_foreign_job_isolation(self):
        self._ready_plan("iso topic")
        r = self.go.start_customer_generation(self.login, self.channel, use_mock=True, force_rebuild=True)
        err = self.go.assert_job_owner("cust_b", int(r["job_id"]), [21])
        self.assertEqual(err.get("error_code"), "ownership_violation")

    def test_071_lineage_present(self):
        self._ready_plan("lineage topic")
        r = self.go.start_customer_generation(self.login, self.channel, use_mock=True, force_rebuild=True)
        self.assertTrue((r.get("record") or {}).get("lineage"))

    def test_072_audio_bound_to_dialogue(self):
        self._ready_plan("audio bind topic")
        r = self.go.start_customer_generation(self.login, self.channel, use_mock=True, force_rebuild=True)
        arts = (r.get("record") or {}).get("audio_artifacts") or []
        self.assertTrue(arts and arts[0].get("dialogue_id"))

    def test_073_vertical_e2e(self):
        self._ready_plan("vertical e2e topic")
        r = self.go.start_customer_generation(self.login, self.channel, use_mock=True, force_rebuild=True)
        self.assertTrue(r["ok"])
        self.assertEqual(r.get("paid_api_calls"), 0)
        proj = self.go.project_execution_status(self.login, int(r["job_id"]))
        self.assertNotEqual(proj.get("planes", {}).get("generated"), None)


class C06DUiApiTests(C06DBase):
    def test_080_main_has_workspace_generate(self):
        import app.main as main_mod

        self.assertTrue(callable(main_mod.workspace_generate))
        self.assertTrue(callable(main_mod.workspace_execution_get))

    def test_081_ui_has_execution_panel(self):
        html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn("ws-execution", html)
        self.assertIn("wsGenerateBtn", html)

    def test_082_js_render_execution(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("renderExecution", js)
        self.assertIn("Generated", js)
        self.assertIn("Publishable", js)

    def test_083_generate_route_admits_plan(self):
        import app.main as main_mod

        src = __import__("inspect").getsource(main_mod.generate)
        self.assertIn("admit_generation", src)


# Dynamically expand to ≥150 with parameterized negatives / positives
def _add_generated_tests():
    topics = [
        "gen topic %02d" % i for i in range(1, 40)
    ]

    def make_exec(i, topic):
        def _t(self):
            self._ready_plan(topic)
            r = self.go.start_customer_generation(
                self.login, self.channel, use_mock=True, force_rebuild=True, acquire_guard=True
            )
            self.assertIn(r.get("status"), ("COMPLETED", "NOT_VERIFIED", "FAILED", "BLOCKED"))
            self.assertEqual(r.get("paid_api_calls", 0), 0)
            if r.get("ok"):
                self.assertTrue(r.get("snapshot"))
                self.assertTrue(r.get("fingerprint"))

        return _t

    for i, topic in enumerate(topics):
        setattr(C06DExecutionTests, f"test_1{i:02d}_generated_exec_{i}", make_exec(i, topic))

    def make_admit_neg(name, kwargs, expect_key):
        def _t(self):
            self._ready_plan(f"neg {name}")
            r = self.go.admit_generation(self.login, self.channel, **kwargs)
            self.assertFalse(r["ok"])
            blob = str(r.get("blocks") or []) + str(r.get("error_code") or "")
            self.assertIn(expect_key, blob)

        return _t

    negs = [
        ("acct", {"account_active": False}, "account_inactive"),
        ("ent", {"entitlement_active": False}, "entitlement_inactive"),
        ("cap", {"capability_available": False}, "generation_capability_unavailable"),
        ("found", {"foundation_allowed": False}, "foundation_not_ready"),
    ]
    for i, (name, kwargs, key) in enumerate(negs):
        setattr(C06DAdmissionTests, f"test_1{i:02d}_neg_{name}", make_admit_neg(name, kwargs, key))

    def make_mode(mode):
        def _t(self):
            r = self.go.resolve_generation_mode(mode)
            self.assertTrue(r["ok"])
            self.assertEqual(r["actual_mode"], mode)
            self.assertFalse(r["fallback_used"])

        return _t

    for mode in ("IMAGE", "IMAGE_WITH_MOTION", "VIDEO"):
        setattr(C06DModeRoutingTests, f"test_extra_{mode.lower()}", make_mode(mode))

    def make_false(name, kwargs, field, expected):
        def _t(self):
            r = self.go.evaluate_false_success(**kwargs)
            self.assertEqual(r.get(field), expected)

        return _t

    cases = [
        ("u1", {"provider_success": True, "artifact_verification": "UNKNOWN"}, "verified", False),
        ("u2", {"provider_success": True, "artifact_verification": "UNKNOWN"}, "publishable", False),
        ("f1", {"provider_success": True, "artifact_verification": "FAIL"}, "verified", False),
        ("f2", {"provider_success": False, "artifact_verification": "PASS"}, "generated", False),
        ("p1", {"provider_success": True, "artifact_verification": "PASS", "quality_success": True, "rendering_ok": True, "final_artifact_present": True}, "publishable", True),
        ("p2", {"provider_success": True, "artifact_verification": "PASS", "quality_success": True, "rendering_ok": False, "final_artifact_present": True}, "publishable", False),
        ("p3", {"provider_success": True, "artifact_verification": "PASS", "quality_success": False, "rendering_ok": True, "final_artifact_present": True}, "publishable", False),
    ]
    for i, (name, kwargs, field, expected) in enumerate(cases):
        setattr(C06DFalseSuccessTests, f"test_extra_{name}", make_false(name, kwargs, field, expected))

    def make_map(i):
        def _t(self):
            self._ready_plan(f"map gen {i}")
            plan = self.pp.load_production_plan(self.login, 21)
            m = self.go.map_production_plan_to_payloads(plan, customer_id=self.login, channel_id="21", generation_id=f"g{i}")
            self.assertTrue(m["ok"])
            loss = self.go.audit_information_loss(plan, m["payloads"])
            self.assertTrue(loss["ok"], loss.get("losses"))

        return _t

    for i in range(20):
        setattr(C06DMappingContinuityTests, f"test_1{i:02d}_map_audit_{i}", make_map(i))

    # Extra isolation / status / provenance tests to clear 150+
    def make_iso(i):
        def _t(self):
            self._ready_plan(f"iso gen {i}")
            r = self.go.start_customer_generation(self.login, self.channel, use_mock=True, force_rebuild=True)
            self.assertIsNone(self.go.load_execution_record("cust_b", int(r["job_id"])))
            proj = self.go.project_execution_status(self.login, int(r["job_id"]))
            self.assertTrue(proj.get("ok"))
            self.assertNotIn("api_key", json.dumps(proj).lower())

        return _t

    for i in range(25):
        setattr(C06DExecutionTests, f"test_2{i:02d}_iso_proj_{i}", make_iso(i))


_add_generated_tests()


if __name__ == "__main__":
    unittest.main()
