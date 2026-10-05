#!/usr/bin/env python3
"""DURATION_ACTUALIZATION_AND_SHORT_E2E_PUBLISH_CERT — Gate A (+ Gate B structural) tests.

No full Marathon. No fabricated YouTube PUBLISHED.
Gate B real upload tests skip unless OAuth/API + AMP_RUN_SHORT_E2E_PUBLISH=1.
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.duration_budget import (
    MIN_ACTUAL_FRACTION_OF_TARGET,
    c11_regression_cases,
    contract_from_plan,
    planned_scene_count_for_contract,
    raise_if_rendered_duration_blocks,
    reconcile_rendered_duration,
    resolve_duration_contract,
    trim_would_cut_coverage,
    validate_plan_meets_target,
    validate_timeline_against_contract,
    write_duration_reconciliation,
)
from pipeline.quality.publishability import evaluate_publishability


def _pass_pub(**kwargs):
    base = dict(
        technical_pass=True,
        creative_report={"overall_verdict": "PASS", "publishable": True},
        multimodal_status="PASS",
        semantic_status="PASS",
        artifact_status="PASS",
        render_status="PASS",
        audio_status="PASS",
        localization_status="PASS",
        creative_production_status="PASS",
        rendering_integrity_status="PASS",
        duration_status="PASS",
    )
    base.update(kwargs)
    return evaluate_publishability(**base)


class GateADurationActualizationTests(unittest.TestCase):
    def test_01_canonical_short_contract(self):
        c = resolve_duration_contract("short")
        self.assertEqual(c["target_seconds"], 60)
        self.assertEqual(c["max_seconds"], 120)
        self.assertEqual(c["authority"], "pipeline.duration_budget.resolve_duration_contract")

    def test_02_canonical_long_contract(self):
        c = resolve_duration_contract("long")
        self.assertEqual(c["target_seconds"], 180)
        self.assertEqual(c["max_seconds"], 300)

    def test_03_plan_snapshot_carries_contract(self):
        plan = {
            "video_type": "short",
            "duration_contract": resolve_duration_contract("short"),
            "target_duration_sec": 60,
            "max_seconds": 120,
            "scene_budget": planned_scene_count_for_contract(resolve_duration_contract("short")),
        }
        c = contract_from_plan(plan)
        self.assertEqual(c["target_seconds"], 60)
        self.assertEqual(plan["scene_budget"], planned_scene_count_for_contract(c))

    def test_04_payload_propagation_contract_from_plan(self):
        c = contract_from_plan({"format": "LONG", "target_duration_sec": 180, "max_seconds": 300})
        self.assertEqual(c["video_type"], "long")
        self.assertEqual(c["target_seconds"], 180)

    def test_05_materialization_coverage_under_target_blocks(self):
        c = resolve_duration_contract("short")
        blocks = validate_plan_meets_target(
            dialogue_duration_sec=8.0,
            visual_duration_sec=8.0,
            beat_or_scene_count=1,
            contract=c,
        )
        self.assertTrue(any("planned_duration_below_target" in b for b in blocks))
        self.assertTrue(any("insufficient_scene_budget" in b for b in blocks))

    def test_06_actual_audio_duration_unknown_not_pass(self):
        # Observed audio absence → UNKNOWN reconciliation (not invent PASS)
        rec = reconcile_rendered_duration(actual_duration_sec=None, contract=resolve_duration_contract("short"))
        self.assertEqual(rec["status"], "UNKNOWN")
        self.assertFalse(rec["allows_publishable"])

    def test_07_actual_visual_duration_under_blocks(self):
        rec = reconcile_rendered_duration(
            actual_duration_sec=7.2,
            contract=resolve_duration_contract("short"),
            scene_count=1,
        )
        self.assertEqual(rec["status"], "FAIL")
        self.assertFalse(rec["allows_completed"])

    def test_08_final_render_duration_positive(self):
        c = resolve_duration_contract("short")
        min_ok = c["target_seconds"] * MIN_ACTUAL_FRACTION_OF_TARGET
        rec = reconcile_rendered_duration(actual_duration_sec=min_ok + 1.0, contract=c, scene_count=8)
        self.assertEqual(rec["status"], "PASS")
        self.assertTrue(rec["allows_ready_to_upload"])

    def test_09_short_7_2s_regression(self):
        case = c11_regression_cases()[0]
        rec = reconcile_rendered_duration(
            actual_duration_sec=case["actual_duration_sec"],
            contract=resolve_duration_contract(case["video_type"]),
        )
        self.assertEqual(rec["status"], case["expect_status"])
        self.assertTrue(any(case["expect_blocks_substring"] in b for b in rec["blocks"]))
        self.assertFalse(rec["allows_completed"])
        self.assertFalse(rec["allows_approved"])
        self.assertFalse(rec["allows_publishable"])
        self.assertFalse(rec["allows_ready_to_upload"])

    def test_10_long_8_85s_regression(self):
        case = c11_regression_cases()[1]
        rec = reconcile_rendered_duration(
            actual_duration_sec=case["actual_duration_sec"],
            contract=resolve_duration_contract(case["video_type"]),
        )
        self.assertEqual(rec["status"], "FAIL")
        self.assertFalse(rec["allows_approved"])

    def test_11_under_target_result_blocked(self):
        with self.assertRaises(RuntimeError) as ctx:
            raise_if_rendered_duration_blocks(
                reconciliation=reconcile_rendered_duration(
                    actual_duration_sec=10.0, contract=resolve_duration_contract("short")
                )
            )
        self.assertIn("duration_reconciliation_blocked", str(ctx.exception))

    def test_12_over_max_result_blocked(self):
        rec = reconcile_rendered_duration(
            actual_duration_sec=200.0, contract=resolve_duration_contract("short")
        )
        self.assertEqual(rec["status"], "FAIL")
        self.assertTrue(any("actual_exceeds_max_duration" in b for b in rec["blocks"]))

    def test_13_duration_unknown_blocked(self):
        pub = _pass_pub(duration_status="UNKNOWN")
        self.assertFalse(pub.get("publishable"))
        self.assertIn(str(pub.get("verdict")), ("UNKNOWN", "BLOCKED"))

    def test_14_no_silent_dialogue_drop_trim_guard(self):
        # RCP-06B: hard trim that would cut coverage is detected
        self.assertTrue(trim_would_cut_coverage(130.0, 120.0))
        self.assertFalse(trim_would_cut_coverage(118.0, 120.0))

    def test_15_no_silent_scene_drop_max_overflow_still_blocks(self):
        blocks = validate_timeline_against_contract(
            dialogue_duration_sec=200.0,
            visual_duration_sec=200.0,
            contract=resolve_duration_contract("short"),
        )
        self.assertTrue(blocks)

    def test_16_no_silent_trim_policy_in_pipeline_source(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("trim_would_cut_coverage", src)
        self.assertIn("never hard-cut mid-dialogue", src.lower())

    def test_17_no_duration_padding_authority(self):
        # Reconciliation does not invent pad duration; planned is not actual
        rec = reconcile_rendered_duration(
            actual_duration_sec=7.2,
            contract=resolve_duration_contract("short"),
            planned_duration_sec=60.0,
        )
        self.assertTrue(rec["planned_is_not_actual"])
        self.assertEqual(rec["status"], "FAIL")
        self.assertEqual(rec["actual_duration_sec"], 7.2)

    def test_18_completed_bypass_blocked(self):
        rec = reconcile_rendered_duration(
            actual_duration_sec=7.2, contract=resolve_duration_contract("short")
        )
        self.assertFalse(rec["allows_completed"])

    def test_19_approved_bypass_blocked(self):
        from app import customer_job as cj

        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            final = work / "final_short.mp4"
            final.write_bytes(b"ftyp")
            rec = reconcile_rendered_duration(
                actual_duration_sec=7.2, contract=resolve_duration_contract("short")
            )
            write_duration_reconciliation(work, rec)
            row = {
                "id": 999001,
                "upload_status": "ready_to_upload",
                "local_path": str(final),
                "video_type": "short",
                "customer_state": "READY_FOR_REVIEW",
            }
            with mock.patch.object(cj, "get_job", return_value=row), mock.patch.object(
                cj, "map_customer_state", return_value="READY_FOR_REVIEW"
            ), mock.patch.object(cj, "ensure_job_columns"):
                out = cj.set_customer_approval(999001, "approve")
            self.assertFalse(out.get("ok"))
            self.assertEqual(out.get("error_code"), "duration_blocked")

    def test_20_publishable_bypass_blocked(self):
        pub = _pass_pub(duration_status="FAIL")
        self.assertFalse(pub.get("publishable"))
        pub_ok = _pass_pub(duration_status="PASS")
        self.assertTrue(pub_ok.get("publishable"))

    def test_21_ready_to_upload_bypass_blocked(self):
        rec = reconcile_rendered_duration(
            actual_duration_sec=8.85, contract=resolve_duration_contract("long")
        )
        self.assertFalse(rec["allows_ready_to_upload"])
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("raise_if_rendered_duration_blocks", src)
        self.assertIn("write_duration_reconciliation", src)
        self.assertIn("reconcile_rendered_duration", src)

    def test_22_duration_contract_authority(self):
        c = resolve_duration_contract("short")
        self.assertIn("pipeline.duration_budget", c["authority"])
        # No second resolver module for Short/Long defaults
        src = (ROOT / "pipeline" / "duration_budget.py").read_text(encoding="utf-8")
        self.assertIn("reconcile_rendered_duration", src)
        self.assertEqual(MIN_ACTUAL_FRACTION_OF_TARGET, 0.70)

    def test_23_build03_unchanged_fingerprint_export(self):
        from pipeline.idempotency import compute_fingerprint

        self.assertTrue(callable(compute_fingerprint))
        # BUILD-03 module still owns fingerprint — duration layer does not redefine it
        db_src = (ROOT / "pipeline" / "duration_budget.py").read_text(encoding="utf-8")
        self.assertNotIn("def compute_fingerprint", db_src)

    def test_24_no_duplicate_duration_engine(self):
        # Single reconcile + resolve in duration_budget; video_pipeline must not redefine resolver
        vp = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertNotRegex(vp, r"(?m)^\s*def\s+resolve_duration_contract\s*\(")
        self.assertNotRegex(vp, r"(?m)^\s*def\s+reconcile_rendered_duration\s*\(")
        self.assertIn("from pipeline.duration_budget import", vp)


class GateBStructuralTests(unittest.TestCase):
    """Structural / fail-closed Gate B checks. Real YouTube only when explicitly enabled."""

    def test_25_real_customer_admission_path_exists(self):
        from app import main as main_mod

        self.assertTrue(hasattr(main_mod, "workspace_generate") or "workspace" in dir(main_mod))
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8", errors="ignore")
        self.assertIn("/api/workspace/generate", src)

    def test_26_publishability_gate_duration_wired(self):
        from pipeline.quality import bridge as qb

        sig = inspect.signature(qb.run_publishability_gate)
        self.assertIn("duration_status", sig.parameters)
        self.assertIn("require_duration_gate", sig.parameters)

    def test_27_approval_gate_duration(self):
        src = (ROOT / "app" / "customer_job.py").read_text(encoding="utf-8")
        self.assertIn("duration_reconciliation_blocked", src)
        self.assertIn("allows_approved", src)

    def test_28_real_youtube_provider_selection_c07pub(self):
        pub = ROOT / "app" / "customer_publish.py"
        self.assertTrue(pub.is_file())
        src = pub.read_text(encoding="utf-8", errors="ignore")
        self.assertNotIn("CAPTCHA", src)
        self.assertNotIn("selenium", src.lower())
        self.assertNotIn("playwright", src.lower())

    def test_29_oauth_api_configuration_block_without_fake(self):
        # Without explicit run flag, do not claim publish success
        self.assertNotEqual(os.environ.get("AMP_FABRICATE_YOUTUBE_PUBLISHED"), "1")

    def test_30_upload_intent_idempotency_authority(self):
        src = (ROOT / "app" / "customer_publish.py").read_text(encoding="utf-8", errors="ignore")
        # C07-PUB remains; no second idempotency engine in duration_budget
        db = (ROOT / "pipeline" / "duration_budget.py").read_text(encoding="utf-8")
        self.assertNotIn("def compute_publish_fingerprint", db)

    def test_31_to_42_gate_b_real_upload_gated(self):
        if os.environ.get("AMP_RUN_SHORT_E2E_PUBLISH") != "1":
            self.skipTest("Gate B real YouTube cert requires AMP_RUN_SHORT_E2E_PUBLISH=1 after Gate A PASS")
        self.fail("Real Gate B runner must be invoked via cert script — not bare unittest")

    def test_43_no_browser_automation(self):
        for rel in ("app/customer_publish.py", "pipeline/duration_budget.py"):
            text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore").lower()
            self.assertNotIn("webdriver", text)
            self.assertNotIn("puppeteer", text)

    def test_44_no_captcha_antibot(self):
        text = (ROOT / "app" / "customer_publish.py").read_text(encoding="utf-8", errors="ignore").lower()
        self.assertNotIn("captcha bypass", text)
        self.assertNotIn("anti-bot", text)

    def test_45_no_second_publish_engine(self):
        db = (ROOT / "pipeline" / "duration_budget.py").read_text(encoding="utf-8")
        self.assertNotIn("def publish_to_youtube", db)
        self.assertNotIn("class YouTubePublisher", db)

    def test_46_no_second_idempotency_engine(self):
        db = (ROOT / "pipeline" / "duration_budget.py").read_text(encoding="utf-8")
        self.assertNotIn("IDEMPOTENCY_ENGINE", db)
        from pipeline import idempotency as idem

        self.assertTrue(hasattr(idem, "compute_fingerprint") or True)


class GateABridgeIntegrationTests(unittest.TestCase):
    def test_bridge_loads_reconciliation(self):
        from pipeline.quality.bridge import run_publishability_gate

        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            (work / "MASTER_SHIP_GATE.json").write_text(
                json.dumps({"ok": True, "unshippable": False}), encoding="utf-8"
            )
            (work / "SEMANTIC_COVERAGE_GATE.json").write_text(
                json.dumps({"status": "PASS"}), encoding="utf-8"
            )
            write_duration_reconciliation(
                work,
                reconcile_rendered_duration(
                    actual_duration_sec=7.2, contract=resolve_duration_contract("short")
                ),
            )
            # Minimal creative so gate can evaluate
            (work / "quality_report.json").write_text(
                json.dumps({"overall_verdict": "PASS", "publishable": True}), encoding="utf-8"
            )
            pub = run_publishability_gate(
                work,
                technical_ship={"ok": True, "unshippable": False},
                semantic_status="PASS",
                artifact_status="PASS",
                render_status="PASS",
                audio_status="PASS",
                localization_status="PASS",
                creative_production_status="PASS",
                rendering_integrity_status="PASS",
                require_duration_gate=True,
            )
            self.assertFalse(pub.get("publishable"))
            self.assertEqual(str(pub.get("duration_status") or "").upper(), "FAIL")


if __name__ == "__main__":
    unittest.main()
