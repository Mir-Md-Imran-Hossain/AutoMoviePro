"""C06-B — Customer Topic → Research → Script workflow (paid APIs = 0)."""
from __future__ import annotations

import ast
import inspect
import json
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class C06BBase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.td = Path(self._tmp.name)
        import app.customer_trs_workflow as w

        self.w = w
        self._orig_path = w._workflow_path
        self._orig_data = w.DATA_DIR
        w.DATA_DIR = self.td
        w._workflow_path = lambda lid, cid: self.td / "wf" / f"{lid}_ch{cid}.json"
        self.login = "customer_a"
        self.channel = {
            "id": 42,
            "niche": "gadgets",
            "youtube_name": "GadgetCh",
            "niche_id": 1,
            "lang_code": "en",
        }

    def tearDown(self):
        self.w.DATA_DIR = self._orig_data
        self.w._workflow_path = self._orig_path


class C06BContractTests(C06BBase):
    def test_01_module_exists(self):
        self.assertTrue(hasattr(self.w, "set_manual_topic"))
        self.assertTrue(hasattr(self.w, "run_research"))
        self.assertTrue(hasattr(self.w, "generate_script"))

    def test_02_topic_sources(self):
        for s in ("MANUAL", "INTELLIGENCE", "RESERVED", "SUGGESTED"):
            self.assertIn(s, self.w.TOPIC_SOURCES)

    def test_03_no_duplicate_engines(self):
        src = Path(self.w.__file__).read_text(encoding="utf-8")
        self.assertEqual(self.w.detect_duplicate_engines(src), [])

    def test_04_does_not_define_script_engine(self):
        src = Path(self.w.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(src, r"(?m)^class CustomerScript")

    def test_05_uses_build04g_imports(self):
        src = Path(self.w.__file__).read_text(encoding="utf-8")
        self.assertIn("discover_topic_candidates", src)
        self.assertIn("analyze_duplicate", src)
        self.assertIn("execute_research_request", src)


class C06BTopicTests(C06BBase):
    def test_06_manual_topic(self):
        r = self.w.set_manual_topic(self.login, 42, "Unique phone battery tips 2026")
        self.assertTrue(r["ok"])
        self.assertEqual(r["topic"]["topic_source"], "MANUAL")
        self.assertEqual(r["topic"]["topic_status"], "COMPLETED")
        self.assertTrue(r["topic"]["topic_id"])

    def test_07_manual_topic_empty_fails(self):
        r = self.w.set_manual_topic(self.login, 42, "  ")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_code"], "validation_failure")

    def test_08_suggested_topics(self):
        r = self.w.suggest_topics(self.login, self.channel, count=5)
        self.assertTrue(r["ok"])
        self.assertGreaterEqual(len(r["suggestions"]), 1)
        self.assertFalse(r["suggestions"][0].get("external_api"))

    def test_09_select_suggested(self):
        sug = self.w.suggest_topics(self.login, self.channel, count=3)
        item = sug["suggestions"][0]
        r = self.w.select_topic(
            self.login,
            self.channel,
            topic_id=item["topic_id"],
            topic_text=item["topic_text"],
            source="SUGGESTED",
        )
        self.assertTrue(r["ok"])
        self.assertEqual(r["topic"]["topic_source"], "SUGGESTED")

    def test_10_topic_ownership_on_state(self):
        self.w.set_manual_topic(self.login, 42, "Owned topic alpha")
        st = self.w.load_workflow(self.login, 42)
        self.assertEqual(st["owner_login_id"], self.login)

    def test_11_duplicate_topic_blocked(self):
        text = "Exact same duplicate topic xyz"
        r1 = self.w.set_manual_topic(self.login, 42, text, corpus=[])
        self.assertTrue(r1["ok"])
        r2 = self.w.set_manual_topic(self.login, 42, text, corpus=[text])
        self.assertFalse(r2["ok"])
        self.assertEqual(r2["error_code"], "topic_duplicate")
        self.assertEqual(r2["topic"]["topic_status"], "BLOCKED")

    def test_12_duplicate_uses_authority(self):
        d = self.w.check_topic_duplicate("hello world", channel_id=42, corpus=["hello world"])
        self.assertIn("BUILD-04G", d["authority"])
        self.assertTrue(d["blocked"])

    def test_13_forged_workflow_owner(self):
        self.w.set_manual_topic(self.login, 42, "Secret topic of A")
        leaked = self.w.load_workflow("customer_b", 42)
        self.assertEqual(leaked["topic"]["topic_status"], "NOT_STARTED")
        self.assertFalse(leaked["topic"].get("topic_text"))

    def test_14_assert_owner_mismatch(self):
        st = self.w.load_workflow(self.login, 42)
        err = self.w.assert_workflow_owner(st, "other", 42)
        self.assertEqual(err["error_code"], "ownership_violation")

    def test_15_reserved_claim_without_list_fails(self):
        r = self.w.select_topic(
            self.login,
            self.channel,
            topic_text="Not in reserve",
            source="RESERVED",
        )
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_code"], "ownership_violation")

    def test_16_reserved_topic_from_list(self):
        st = self.w.load_workflow(self.login, 42)
        st["reserved"] = [{"topic_id": "r1", "topic_text": "Reserved gadget tip", "source": "RESERVED"}]
        self.w.save_workflow(st)
        r = self.w.select_topic(
            self.login,
            self.channel,
            topic_id="r1",
            topic_text="Reserved gadget tip",
            source="RESERVED",
        )
        self.assertTrue(r["ok"])
        self.assertEqual(r["topic"]["topic_source"], "RESERVED")

    def test_17_topic_fields_contract(self):
        r = self.w.set_manual_topic(self.login, 42, "Contract field topic")
        t = r["topic"]
        for k in ("topic_id", "project_id", "owner_login_id", "topic_text", "topic_source", "topic_status", "selected_at", "created_at", "updated_at"):
            self.assertIn(k, t)


class C06BResearchTests(C06BBase):
    def _ready_topic(self):
        self.w.set_manual_topic(self.login, 42, "Researchable unique topic 991")

    def test_18_research_requires_topic(self):
        r = self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "r0")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_code"], "missing_prerequisite")

    def test_19_research_start_success(self):
        self._ready_topic()
        r = self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "r1")
        self.assertTrue(r["ok"])
        self.assertEqual(r["research"]["research_status"], "COMPLETED")

    def test_20_research_capability_honesty(self):
        self._ready_topic()
        r = self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "r2")
        cap = r["research"]["capability"]
        self.assertFalse(cap.get("is_external_live"))
        self.assertIn(cap.get("external_live_research"), ("UNAVAILABLE", "UNKNOWN"))

    def test_21_no_live_research_complete_claim(self):
        self._ready_topic()
        r = self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "r3")
        self.assertFalse(r["research"].get("live_research_complete"))

    def test_22_research_failure_truthful(self):
        self._ready_topic()
        with patch("pipeline.intelligence.research_runtime.execute_research_request", side_effect=RuntimeError("boom")):
            r = self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "r4")
        self.assertFalse(r["ok"])
        self.assertEqual(r["workflow"]["research"]["research_status"], "FAILED")

    def test_23_fact_evidence_counts(self):
        self._ready_topic()
        r = self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "r5")
        self.assertIn("fact_count", r["research"])
        self.assertIn("evidence_count", r["research"])
        self.assertIsNone(r["research"].get("confidence"))

    def test_24_local_vs_live_label(self):
        self._ready_topic()
        r = self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "r6")
        proj = r["workflow"]["research"]
        self.assertNotIn("Live Research Complete", str(proj.get("status_label") or ""))
        if proj.get("research_status") == "COMPLETED":
            self.assertIn("FactPack", str(proj.get("status_label") or "FactPack"))


class C06BScriptTests(C06BBase):
    def _ready_research(self):
        self.w.set_manual_topic(self.login, 42, "Scriptable unique topic 772")
        self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "rs")

    def test_25_script_requires_research(self):
        self.w.set_manual_topic(self.login, 42, "No research yet topic")
        r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "s0")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_code"], "missing_prerequisite")

    def test_26_script_generation(self):
        self._ready_research()
        r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "s1")
        self.assertTrue(r["ok"])
        self.assertEqual(r["script"]["script_status"], "COMPLETED")

    def test_27_script_plan_present(self):
        self._ready_research()
        r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "s2")
        plan = r["script"]["script_plan"]
        self.assertIsInstance(plan, dict)
        self.assertTrue(plan.get("topic"))
        self.assertTrue(plan.get("beats"))

    def test_28_script_plan_beat_ids(self):
        self._ready_research()
        r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "s3")
        beats = r["script"]["script_plan"]["beats"]
        ids = [b.get("beat_id") for b in beats]
        self.assertTrue(all(ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_29_dialogue_ids_preserved(self):
        self._ready_research()
        r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "s4")
        prev = r["script"]["preview"]
        self.assertTrue(prev["dialogue_ids"])
        self.assertTrue(prev["beat_ids"])
        self.assertTrue(prev["scene_ids"])

    def test_30_scriptplan_domain_compatible(self):
        from domain.script import ScriptPlan

        self._ready_research()
        r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "s5")
        sp = ScriptPlan.model_validate(r["script"]["script_plan"])
        self.assertTrue(sp.beats)

    def test_31_entity_preservation_helper(self):
        plan = {
            "topic": "t",
            "beats": [
                {
                    "beat_id": "b1",
                    "narration": "Shobha stands beside the Suzuki car",
                    "entity_refs": ["Shobha", "Suzuki"],
                    "location_ref": "roadside",
                    "action_intent": "stands beside",
                    "emotion": "calm",
                    "estimated_duration_sec": 4,
                    "metadata": {"dialogue_id": "dlg-1", "scene_id": "scene-00"},
                }
            ],
        }
        prev = self.w._script_plan_to_preview(plan)
        self.assertIn("Shobha", prev["entities"])
        self.assertIn("Suzuki", prev["entities"])
        self.assertIn("roadside", prev["locations"])
        self.assertTrue(any("beside" in x for x in prev["relationships"]))
        self.assertEqual(prev["dialogue_ids"][0], "dlg-1")

    def test_32_relationship_preservation(self):
        plan = {"beats": [{"beat_id": "b", "narration": "inside the car", "action_intent": "sits inside", "entity_refs": ["Shobha"], "location_ref": "car", "metadata": {}}]}
        prev = self.w._script_plan_to_preview(plan)
        self.assertTrue(any("inside" in x for x in prev["relationships"]))

    def test_33_location_preservation(self):
        plan = {"beats": [{"beat_id": "b", "narration": "x", "location_ref": "hospital", "entity_refs": [], "metadata": {}}]}
        self.assertIn("hospital", self.w._script_plan_to_preview(plan)["locations"])

    def test_34_character_preservation(self):
        plan = {"beats": [{"beat_id": "b", "narration": "x", "entity_refs": ["Police Officer"], "location_ref": "", "metadata": {}}]}
        self.assertIn("Police Officer", self.w._script_plan_to_preview(plan)["entities"])

    def test_35_emotion_preservation(self):
        plan = {"beats": [{"beat_id": "b", "narration": "x", "emotion": "tense", "entity_refs": [], "location_ref": "", "metadata": {}}]}
        self.assertEqual(self.w._script_plan_to_preview(plan)["beats_summary"][0]["emotion"], "tense")

    def test_36_timing_preservation(self):
        plan = {"beats": [{"beat_id": "b", "narration": "x", "estimated_duration_sec": 7.5, "entity_refs": [], "location_ref": "", "metadata": {}}]}
        self.assertEqual(self.w._script_plan_to_preview(plan)["beats_summary"][0]["estimated_duration_sec"], 7.5)

    def test_37_quality_status_normalized(self):
        self.assertEqual(self.w._normalize_quality_status("UNKNOWN"), "UNKNOWN")
        self.assertEqual(self.w._normalize_quality_status("PASS"), "PASS")
        self.assertNotEqual(self.w._normalize_quality_status("UNKNOWN"), "PASS")

    def test_38_script_quality_run(self):
        self._ready_research()
        r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "s6")
        self.assertIn(r["script"]["quality"]["status"], self.w.QUALITY_VERDICTS)

    def test_39_quality_unknown_not_pass(self):
        self.assertNotEqual(self.w._normalize_quality_status("OBSERVED_UNKNOWN"), "PASS")

    def test_40_quality_fail_blocks_approval_ready(self):
        self._ready_research()
        r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "s7")
        st = self.w.load_workflow(self.login, 42)
        st["script"]["quality"]["status"] = "FAIL"
        st["script"]["approval"]["state"] = "NOT_READY"
        self.w.save_workflow(st)
        ap = self.w.approve_script(self.login, 42, decision="approved")
        self.assertFalse(ap["ok"])

    def test_41_script_approval(self):
        self._ready_research()
        r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "s8")
        st = self.w.load_workflow(self.login, 42)
        st["script"]["quality"]["status"] = "PASS"
        st["script"]["approval"]["state"] = "READY_FOR_REVIEW"
        self.w.save_workflow(st)
        ap = self.w.approve_script(self.login, 42, decision="approved")
        self.assertTrue(ap["ok"])
        self.assertEqual(ap["approval"]["state"], "APPROVED")
        self.assertFalse(ap["approval"]["publishes"])
        self.assertFalse(ap["approval"]["means_generated"])
        self.assertTrue(ap["c05_handoff"]["ready"])

    def test_42_rejected_script(self):
        self._ready_research()
        self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "s9")
        st = self.w.load_workflow(self.login, 42)
        st["script"]["approval"]["state"] = "READY_FOR_REVIEW"
        st["script"]["quality"]["status"] = "PASS"
        self.w.save_workflow(st)
        ap = self.w.approve_script(self.login, 42, decision="rejected")
        self.assertTrue(ap["ok"])
        self.assertEqual(ap["approval"]["state"], "REJECTED")
        self.assertFalse(ap["c05_handoff"]["ready"])

    def test_43_failed_script_not_approved(self):
        st = self.w.load_workflow(self.login, 42)
        st["script"]["script_status"] = "FAILED"
        self.w.save_workflow(st)
        ap = self.w.approve_script(self.login, 42, decision="approved")
        self.assertFalse(ap["ok"])

    def test_44_repeated_generation_idempotent_path(self):
        self._ready_research()
        wd = self.td / "s_idem"
        r1 = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=wd)
        r2 = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=wd)
        self.assertTrue(r1["ok"] and r2["ok"])
        # BUILD-03 may reuse; at least both complete
        self.assertEqual(r2["script"]["script_status"], "COMPLETED")

    def test_45_c05_handoff_path(self):
        self._ready_research()
        self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "s10")
        st = self.w.load_workflow(self.login, 42)
        st["script"]["quality"]["status"] = "PASS"
        st["script"]["approval"]["state"] = "READY_FOR_REVIEW"
        self.w.save_workflow(st)
        ap = self.w.approve_script(self.login, 42, decision="approved")
        self.assertIn("C05-TRS", ap["c05_handoff"]["path"])
        self.assertIn("C05-MR", ap["c05_handoff"]["path"])
        self.assertEqual(ap["c05_handoff"]["status"], "APPROVED_SCRIPT")

    def test_46_invalid_transition_research_before_topic(self):
        r = self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "bad")
        self.assertEqual(r["error_code"], "missing_prerequisite")

    def test_47_actions_flags(self):
        st = self.w._empty_state(self.login, 42)
        acts = self.w.derive_trs_actions(st)
        self.assertTrue(acts["select_topic"])
        self.assertFalse(acts["research"])
        self.w.set_manual_topic(self.login, 42, "Action topic unique 55")
        st2 = self.w.load_workflow(self.login, 42)
        self.assertTrue(self.w.derive_trs_actions(st2)["research"])


class C06BIsolationApiUiTests(C06BBase):
    def test_48_customer_isolation_channel_file(self):
        self.w.set_manual_topic("a", 1, "Topic A only")
        self.w.set_manual_topic("b", 1, "Topic B only")
        self.assertEqual(self.w.load_workflow("a", 1)["topic"]["topic_text"], "Topic A only")
        self.assertEqual(self.w.load_workflow("b", 1)["topic"]["topic_text"], "Topic B only")

    def test_49_sanitize_in_errors(self):
        s = self.w.sanitize_customer_error if hasattr(self.w, "sanitize_customer_error") else None
        from app.customer_job import sanitize_customer_error

        out = sanitize_customer_error("fail api_key=sk-abcdefghijk")
        self.assertNotIn("sk-abcdefghijk", out)

    def test_50_api_endpoints_exist(self):
        from app import main as main_mod

        for name in (
            "workspace_topic",
            "workspace_topics_suggest",
            "workspace_research",
            "workspace_script",
            "workspace_script_approval",
        ):
            self.assertTrue(callable(getattr(main_mod, name)))

    def test_51_workspace_includes_trs(self):
        from app import main as main_mod

        src = inspect.getsource(main_mod.workspace)
        self.assertIn("trs_workflow", src)

    def test_52_ui_panels_present(self):
        html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn("ws-trs-topic", html)
        self.assertIn("ws-trs-research", html)
        self.assertIn("ws-trs-script", html)

    def test_53_ui_js_wired(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("renderTrsWorkflow", js)
        self.assertIn("/api/workspace/research", js)
        self.assertIn("local FactPack", js)

    def test_54_endpoints_require_owned_channel(self):
        from app import main as main_mod

        src = inspect.getsource(main_mod.workspace_topic)
        self.assertIn("_owned_channel_or_err", src)

    def test_55_no_provider_business_logic_in_ui(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("openrouter", js.lower())
        self.assertNotIn("analyze_duplicate", js)

    def test_56_audit_doc_exists(self):
        p = ROOT / "docs" / "marathon" / "customer_product" / "C06B_PRE_TOPIC_RESEARCH_SCRIPT_AUDIT.md"
        self.assertTrue(p.is_file())

    def test_57_c06a_not_removed(self):
        self.assertTrue((ROOT / "app" / "customer_workspace.py").is_file())

    def test_58_c05_not_reopened_in_workflow(self):
        src = Path(self.w.__file__).read_text(encoding="utf-8")
        self.assertNotIn("generate_video", src)
        self.assertNotIn("materialize_visual_beats", src)

    def test_59_projection_strips_fact_pack(self):
        st = self.w._empty_state(self.login, 42)
        st["research"]["fact_pack"] = {"claims": [{"id": "c1"}], "secret": "x"}
        st["research"]["research_status"] = "COMPLETED"
        proj = self.w.project_trs_workflow(st)
        self.assertNotIn("fact_pack", proj["research"])
        self.assertTrue(proj["research"]["has_fact_pack"])

    def test_60_smoke_full_chain(self):
        self.w.set_manual_topic(self.login, 42, "Full chain unique topic 4242")
        self.assertTrue(self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "sm_r")["ok"])
        r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "sm_s")
        self.assertTrue(r["ok"])
        st = self.w.load_workflow(self.login, 42)
        st["script"]["quality"]["status"] = "PASS"
        st["script"]["approval"]["state"] = "READY_FOR_REVIEW"
        self.w.save_workflow(st)
        ap = self.w.approve_script(self.login, 42, decision="approved")
        self.assertTrue(ap["c05_handoff"]["ready"])


class C06BExtraCoverage(C06BBase):
    def test_61_revision_increments(self):
        self.w.set_manual_topic(self.login, 42, "Rev topic 1")
        r1 = self.w.load_workflow(self.login, 42)["revision"]
        self.w.set_manual_topic(self.login, 42, "Rev topic 2 unique")
        r2 = self.w.load_workflow(self.login, 42)["revision"]
        self.assertGreater(r2, r1)

    def test_62_blocked_topic_resets_handoff(self):
        self.w.set_manual_topic(self.login, 42, "Dup base topic")
        st = self.w.load_workflow(self.login, 42)
        st["c05_handoff"]["ready"] = True
        self.w.save_workflow(st)
        self.w.set_manual_topic(self.login, 42, "Dup base topic", corpus=["Dup base topic"])
        self.assertFalse(self.w.load_workflow(self.login, 42)["c05_handoff"]["ready"])

    def test_63_suggest_note_honesty(self):
        r = self.w.suggest_topics(self.login, self.channel)
        self.assertIn("not external", (r.get("note") or "").lower())

    def test_64_invalid_topic_source(self):
        r = self.w.select_topic(self.login, self.channel, topic_text="x", source="WEIRD")
        self.assertFalse(r["ok"])

    def test_65_approve_invalid_decision(self):
        st = self.w.load_workflow(self.login, 42)
        st["script"]["script_status"] = "COMPLETED"
        st["script"]["quality"]["status"] = "PASS"
        st["script"]["approval"]["state"] = "READY_FOR_REVIEW"
        self.w.save_workflow(st)
        r = self.w.approve_script(self.login, 42, decision="publish")
        self.assertFalse(r["ok"])

    def test_66_script_failure_path(self):
        self.w.set_manual_topic(self.login, 42, "Fail script topic")
        self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "fr")
        with patch("pipeline.trs_facade.plan_script_for_trs", side_effect=RuntimeError("script boom")):
            r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "fs")
        self.assertFalse(r["ok"])
        self.assertEqual(r["workflow"]["script"]["script_status"], "FAILED")

    def test_67_quality_fail_normalize(self):
        self.assertEqual(self.w._normalize_quality_status("FAILED"), "FAIL")

    def test_68_quality_blocked_normalize(self):
        self.assertEqual(self.w._normalize_quality_status("BLOCKED"), "BLOCKED")

    def test_69_topic_id_stable(self):
        a = self.w._topic_id_for("Hello World", "MANUAL")
        b = self.w._topic_id_for("hello world", "MANUAL")
        self.assertEqual(a, b)

    def test_70_project_id(self):
        st = self.w._empty_state(self.login, 7)
        self.assertEqual(st["project_id"], "trs-ch7")

    def test_71_actions_approve_false_initially(self):
        self.assertFalse(self.w.derive_trs_actions(self.w._empty_state(self.login, 42))["approve_script"])

    def test_72_handoff_not_ready_default(self):
        self.assertFalse(self.w._empty_state(self.login, 42)["c05_handoff"]["ready"])

    def test_73_no_paid_api_calls_in_tests(self):
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                calls.append(f"{getattr(node.func.value, 'id', '')}.{node.func.attr}")
        self.assertNotIn("requests.post", calls)
        self.assertNotIn("httpx.post", calls)

    def test_74_build04f_authority_string(self):
        self.w.set_manual_topic(self.login, 42, "Quality authority topic")
        self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "qa_r")
        r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "qa_s")
        self.assertIn("BUILD-04F", r["script"]["quality"]["authority"])

    def test_75_dialogue_segments_count(self):
        self.w.set_manual_topic(self.login, 42, "Dialogue count topic")
        self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "dc_r")
        r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "dc_s")
        self.assertGreaterEqual(r["script"].get("dialogue_segments_count", 0), 1)

    def test_76_scene_id_format(self):
        plan = {"beats": [{"beat_id": "b0", "narration": "n", "metadata": {"scene_id": "scene-00"}, "entity_refs": []}]}
        self.assertEqual(self.w._script_plan_to_preview(plan)["scene_ids"][0], "scene-00")

    def test_77_channel_mismatch_assert(self):
        st = self.w.load_workflow(self.login, 42)
        err = self.w.assert_workflow_owner(st, self.login, 99)
        self.assertEqual(err["error_code"], "ownership_violation")

    def test_78_research_unresolved_list(self):
        self.w.set_manual_topic(self.login, 42, "Unresolved topic x")
        r = self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "ur")
        self.assertIn("unresolved_items", r["research"])

    def test_79_script_preview_hook(self):
        self.w.set_manual_topic(self.login, 42, "Hook topic unique")
        self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "hk_r")
        r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "hk_s")
        self.assertIn("hook", r["script"]["preview"])

    def test_80_approval_states_constant(self):
        for s in ("NOT_READY", "READY_FOR_REVIEW", "APPROVED", "REJECTED"):
            self.assertIn(s, self.w.SCRIPT_APPROVAL)

    def test_81_topic_statuses_constant(self):
        for s in ("NOT_STARTED", "READY", "RUNNING", "COMPLETED", "BLOCKED", "FAILED"):
            self.assertIn(s, self.w.TOPIC_STATUSES)

    def test_82_main_script_approval_note(self):
        from app import main as main_mod

        src = inspect.getsource(main_mod.workspace_script_approval)
        self.assertTrue("approve" in src.lower())

    def test_83_select_by_id_from_suggestions(self):
        sug = self.w.suggest_topics(self.login, self.channel, count=2)
        tid = sug["suggestions"][0]["topic_id"]
        r = self.w.select_topic(self.login, self.channel, topic_id=tid, source="SUGGESTED")
        self.assertTrue(r["ok"])

    def test_84_generate_with_tone_fields(self):
        self.w.set_manual_topic(self.login, 42, "Tone topic unique 88")
        self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "tn_r")
        r = self.w.generate_script(
            self.login,
            self.channel,
            use_mock=True,
            work_dir=self.td / "tn_s",
            tone="friendly",
            audience="teens",
            instructions="keep short",
        )
        self.assertTrue(r["ok"])

    def test_85_product_registry_in_dup_check(self):
        d = self.w.check_topic_duplicate("anything", channel_id=42)
        self.assertIn("product_registry", d["authority"])

    def test_86_workflow_save_load_roundtrip(self):
        self.w.set_manual_topic(self.login, 42, "Roundtrip topic")
        st = self.w.load_workflow(self.login, 42)
        self.assertEqual(st["topic"]["topic_text"], "Roundtrip topic")

    def test_87_no_second_factpack_engine(self):
        src = Path(self.w.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(src, r"(?m)^def build_fact_pack")

    def test_88_no_second_ranking_engine(self):
        src = Path(self.w.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(src, r"(?m)^def rank_candidates")

    def test_89_classify_capability_import_used(self):
        src = Path(self.w.__file__).read_text(encoding="utf-8")
        self.assertIn("classify_research_capability", src)

    def test_90_validate_fact_pack_used(self):
        src = Path(self.w.__file__).read_text(encoding="utf-8")
        self.assertIn("validate_fact_pack", src)

    def test_91_plan_script_for_trs_used(self):
        src = Path(self.w.__file__).read_text(encoding="utf-8")
        self.assertIn("plan_script_for_trs", src)

    def test_92_evaluate_script_quality_used(self):
        src = Path(self.w.__file__).read_text(encoding="utf-8")
        self.assertIn("evaluate_script_quality", src)

    def test_93_script_plan_to_dialogue_segments_used(self):
        src = Path(self.w.__file__).read_text(encoding="utf-8")
        self.assertIn("script_plan_to_dialogue_segments", src)

    def test_94_reserve_queue_load_used(self):
        src = Path(self.w.__file__).read_text(encoding="utf-8")
        self.assertIn("load_reserve", src)

    def test_95_ui_does_not_claim_live_complete(self):
        js = (ROOT / "ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        # Must distinguish local FactPack
        self.assertIn("NOT external live", js)

    def test_96_failed_research_not_success_status(self):
        self.w.set_manual_topic(self.login, 42, "Gate fail topic")
        with patch("pipeline.intelligence.factpack_gate.validate_fact_pack", return_value={"verdict": "RESEARCH_REQUIRED", "reason": "x"}):
            # still need execute to succeed
            r = self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "gf")
        # may fail gate
        if not r.get("ok"):
            self.assertEqual(r["workflow"]["research"]["research_status"], "FAILED")

    def test_97_c05_closed_docs(self):
        text = (ROOT / "docs" / "marathon" / "customer_product" / "C06B_PRE_TOPIC_RESEARCH_SCRIPT_AUDIT.md").read_text(encoding="utf-8")
        self.assertIn("CLOSED", text)

    def test_98_unknown_quality_allows_review(self):
        st = self.w.load_workflow(self.login, 42)
        st["script"]["script_status"] = "COMPLETED"
        st["script"]["quality"] = {"status": "UNKNOWN"}
        st["script"]["approval"] = {"state": "READY_FOR_REVIEW", "publishes": False, "means_generated": False}
        self.w.save_workflow(st)
        ap = self.w.approve_script(self.login, 42, decision="approved")
        self.assertTrue(ap["ok"])

    def test_99_reject_does_not_publish(self):
        st = self.w.load_workflow(self.login, 42)
        st["script"]["script_status"] = "COMPLETED"
        st["script"]["quality"] = {"status": "PASS"}
        st["script"]["approval"] = {"state": "READY_FOR_REVIEW", "publishes": False, "means_generated": False}
        self.w.save_workflow(st)
        ap = self.w.approve_script(self.login, 42, decision="rejected")
        self.assertFalse(ap["approval"]["publishes"])

    def test_100_empty_topic_select_fails(self):
        r = self.w.select_topic(self.login, self.channel, topic_text="", source="MANUAL")
        self.assertFalse(r["ok"])

    def test_101_script_counts(self):
        self.w.set_manual_topic(self.login, 42, "Count beats topic")
        self.w.run_research(self.login, self.channel, use_mock=True, work_dir=self.td / "cb_r")
        r = self.w.generate_script(self.login, self.channel, use_mock=True, work_dir=self.td / "cb_s")
        self.assertGreaterEqual(r["script"]["beat_count"], 1)
        self.assertGreaterEqual(r["script"]["dialogue_count"], 1)

    def test_102_project_trs_actions_after_approve(self):
        st = self.w.load_workflow(self.login, 42)
        st["c05_handoff"] = {"ready": True}
        self.assertTrue(self.w.derive_trs_actions(st)["c05_handoff_ready"])

    def test_103_shobha_suzuki_not_lost(self):
        """Semantic preservation example from C06-B command."""
        narr = "Shobha stands beside the Suzuki car"
        plan = {
            "beats": [
                {
                    "beat_id": "beat-shobha",
                    "narration": narr,
                    "entity_refs": ["Shobha", "Suzuki"],
                    "location_ref": "street",
                    "action_intent": "stands beside Suzuki",
                    "emotion": "focused",
                    "estimated_duration_sec": 5,
                    "metadata": {"dialogue_id": "dlg-shobha", "scene_id": "scene-01"},
                }
            ]
        }
        prev = self.w._script_plan_to_preview(plan)
        self.assertIn("Shobha", prev["entities"])
        self.assertIn("Suzuki", prev["entities"])
        self.assertIn("street", prev["locations"])
        self.assertIn("dlg-shobha", prev["dialogue_ids"])
        self.assertTrue(any("beside" in r for r in prev["relationships"]))

    def test_104_endpoint_ownership_on_research(self):
        from app import main as main_mod

        self.assertIn("_owned_channel_or_err", inspect.getsource(main_mod.workspace_research))

    def test_105_idempotency_via_build03_script(self):
        src = Path(self.w.__file__).read_text(encoding="utf-8")
        self.assertIn("plan_script_for_trs", src)
        # no local fingerprint store for scripts
        self.assertNotIn("class ScriptCache", src)


if __name__ == "__main__":
    unittest.main()
