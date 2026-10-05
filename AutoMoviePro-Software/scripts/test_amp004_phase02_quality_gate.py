#!/usr/bin/env python3
"""AMP-004 Phase-02 — Quality Gate Foundation behavioral tests."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.idempotency.mock_visual_provider import MockBehavior, get_mock_provider, reset_mock_provider
from pipeline.quality.bridge import run_publishability_gate
from pipeline.quality.multimodal_aggregate import (
    assert_production_semantic_bypass_forbidden,
    persist_multimodal_report,
    aggregate_and_persist,
)
from pipeline.quality.publishability import PublishabilityVerdict, evaluate_publishability


def _creative_pass() -> dict:
    return {"overall_verdict": "PASS", "publishable": True, "overall_score": 0.95}


def _sem_pass() -> dict:
    """RCP-06A: semantic PASS required for PUBLISHABLE."""
    return {"semantic_status": "PASS"}


def _write_semantic_pass(work: Path) -> None:
    payload = {"verdict": "PASS", "blocking": False, "reason": "all_pass"}
    (work / "SEMANTIC_COVERAGE_GATE.json").write_text(json.dumps(payload), encoding="utf-8")
    (work / "SEMANTIC_GATE.json").write_text(json.dumps(payload), encoding="utf-8")


def _creative_blocked() -> dict:
    return {"overall_verdict": "BLOCKED", "publishable": False, "overall_score": 0.2}


def _mm_report(status: str, scene_id: str = "1", dialogue_id: str = "dlg-1") -> dict:
    return {
        "scene_id": scene_id,
        "dialogue_id": dialogue_id,
        "revision_id": "r1",
        "intent_fingerprint": "fp-test",
        "final_status": status,
        "layers": [],
        "metadata": {},
    }


class Phase02QualityGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        reset_mock_provider()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_ship(self, ok: bool = True):
        ship = {"ok": ok, "unshippable": not ok, "critical_issues": [] if ok else ["black_tail"]}
        (self.tmp / "MASTER_SHIP_GATE.json").write_text(json.dumps(ship), encoding="utf-8")
        return ship

    def _write_creative(self, report: dict):
        (self.tmp / "CREATIVE_QUALITY_GATE.json").write_text(
            json.dumps({"ok": report.get("publishable", False), **report}), encoding="utf-8"
        )

    # TEST-01
    def test_01_valid_complete_quality_state(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report=_creative_pass(),
            multimodal_status="PASS",
            artifact_status="PASS",
            render_status="PASS",
            semantic_status="PASS",
        )
        self.assertTrue(pub["publishable"])
        self.assertEqual(pub["verdict"], PublishabilityVerdict.PUBLISHABLE.value)

    # TEST-02
    def test_02_multimodal_blocked(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report=_creative_pass(),
            multimodal_status="BLOCKED",
        )
        self.assertFalse(pub["publishable"])
        self.assertEqual(pub["verdict"], PublishabilityVerdict.BLOCKED.value)
        self.assertEqual(pub["reason"], "multimodal_blocked")

    # TEST-03
    def test_03_multimodal_mandatory_unknown(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report=_creative_pass(),
            multimodal_status="UNKNOWN",
            multimodal_mandatory_unknown=True,
        )
        self.assertFalse(pub["publishable"])
        self.assertIn(pub["verdict"], (PublishabilityVerdict.UNKNOWN.value, PublishabilityVerdict.BLOCKED.value))
        self.assertEqual(pub["reason"], "multimodal_unknown_mandatory")

    # TEST-04
    def test_04_multimodal_advisory_unknown_not_false_pass(self):
        # Advisory UNKNOWN must not invent PASS when other gates fail
        pub = evaluate_publishability(
            technical_pass=False,
            creative_report=_creative_pass(),
            multimodal_status="UNKNOWN",
            multimodal_mandatory_unknown=False,
        )
        self.assertFalse(pub["publishable"])
        # And advisory alone with all else PASS: dimension N/A-like when mandatory_unknown False
        pub2 = evaluate_publishability(
            technical_pass=True,
            creative_report=_creative_pass(),
            multimodal_status="UNKNOWN",
            multimodal_mandatory_unknown=False,
            **_sem_pass(),
        )
        # Soft advisory unknown does not hard-block; may publish if other gates pass
        self.assertTrue(pub2["publishable"])
        self.assertEqual(pub2["multimodal_status"], "UNKNOWN")

    # TEST-05
    def test_05_technical_blocked(self):
        pub = evaluate_publishability(
            technical_pass=False, creative_report=_creative_pass(), multimodal_status="PASS", **_sem_pass()
        )
        self.assertFalse(pub["publishable"])
        self.assertEqual(pub["reason"], "technical_validation_failed")

    # TEST-06
    def test_06_creative_blocked(self):
        pub = evaluate_publishability(
            technical_pass=True, creative_report=_creative_blocked(), multimodal_status="PASS", **_sem_pass()
        )
        self.assertFalse(pub["publishable"])
        self.assertEqual(pub["reason"], "creative_quality_blocked")

    # TEST-07
    def test_07_artifact_blocked(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report=_creative_pass(),
            multimodal_status="PASS",
            artifact_status="BLOCKED",
            **_sem_pass(),
        )
        self.assertFalse(pub["publishable"])
        self.assertEqual(pub["reason"], "artifact_blocked")

    # TEST-08
    def test_08_render_blocked(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report=_creative_pass(),
            multimodal_status="PASS",
            render_status="BLOCKED",
            **_sem_pass(),
        )
        self.assertFalse(pub["publishable"])
        self.assertEqual(pub["reason"], "render_blocked")

    # TEST-09
    def test_09_multiple_simultaneous_blocked(self):
        pub = evaluate_publishability(
            technical_pass=False,
            creative_report=_creative_blocked(),
            multimodal_status="BLOCKED",
            artifact_status="BLOCKED",
        )
        self.assertFalse(pub["publishable"])
        # First hard dimension in check order wins (multimodal before creative in our order)
        self.assertEqual(pub["reason"], "multimodal_blocked")

    # TEST-10 / TEST-11
    def test_10_11_no_production_quality_bypass(self):
        with self.assertRaises(PermissionError):
            assert_production_semantic_bypass_forbidden(
                {"skip_semantic_validation": True},
                production=True,
                allow_test_only=False,
            )
        with self.assertRaises(PermissionError):
            assert_production_semantic_bypass_forbidden(
                {"skip_semantic_validation": True, "semantic_bypass_class": "TEST_ONLY"},
                production=True,
                allow_test_only=False,  # production caller must not enable test flag
            )

    # TEST-12
    def test_12_test_only_bypass_available(self):
        assert_production_semantic_bypass_forbidden(
            {"skip_semantic_validation": True, "semantic_bypass_class": "TEST_ONLY"},
            production=True,
            allow_test_only=True,
        )  # does not raise

    # TEST-13
    def test_13_publication_blocked_after_mandatory_failure(self):
        self._write_ship(True)
        self._write_creative(_creative_pass())
        persist_multimodal_report(self.tmp, _mm_report("BLOCKED"), scene_key="s1")
        pub = run_publishability_gate(self.tmp)
        self.assertFalse(pub["publishable"])
        self.assertEqual(pub["reason"], "multimodal_blocked")
        # Simulate video_pipeline gate
        self.assertFalse(bool(pub.get("publishable")))

    # TEST-14
    def test_14_publication_allowed_when_all_pass(self):
        self._write_ship(True)
        self._write_creative(_creative_pass())
        _write_semantic_pass(self.tmp)
        persist_multimodal_report(self.tmp, _mm_report("PASS"), scene_key="s1")
        pub = run_publishability_gate(self.tmp)
        self.assertTrue(pub["publishable"])
        self.assertEqual(pub["verdict"], PublishabilityVerdict.PUBLISHABLE.value)

    # TEST-15
    def test_15_no_false_pass_after_cache_reuse(self):
        self._write_ship(True)
        self._write_creative(_creative_pass())
        _write_semantic_pass(self.tmp)
        persist_multimodal_report(self.tmp, _mm_report("PASS"), scene_key="s1")
        pub1 = run_publishability_gate(self.tmp)
        self.assertTrue(pub1["publishable"])
        # Stale overwrite: multimodal becomes BLOCKED — must re-evaluate from disk
        persist_multimodal_report(self.tmp, _mm_report("BLOCKED"), scene_key="s1")
        pub2 = run_publishability_gate(self.tmp)
        self.assertFalse(pub2["publishable"])

    # TEST-16
    def test_16_stale_quality_cannot_authorize_publication(self):
        self._write_ship(True)
        # Tampered creative PASS on disk but multimodal BLOCKED
        self._write_creative(_creative_pass())
        _write_semantic_pass(self.tmp)
        (self.tmp / "PUBLISHABILITY_GATE.json").write_text(
            json.dumps({"publishable": True, "verdict": "PUBLISHABLE", "reason": "tampered"}),
            encoding="utf-8",
        )
        persist_multimodal_report(self.tmp, _mm_report("BLOCKED"), scene_key="s1")
        pub = run_publishability_gate(self.tmp)
        self.assertFalse(pub["publishable"])
        self.assertNotEqual(pub.get("reason"), "tampered")

    # TEST-17
    def test_17_provenance_incomplete_blocks(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report=_creative_pass(),
            multimodal_status="PASS",
            provenance_complete=False,
            **_sem_pass(),
        )
        self.assertFalse(pub["publishable"])
        self.assertEqual(pub["reason"], "provenance_incomplete")

    # TEST-18
    def test_18_checkpoint_gate_file_written(self):
        self._write_ship(True)
        self._write_creative(_creative_pass())
        _write_semantic_pass(self.tmp)
        persist_multimodal_report(self.tmp, _mm_report("PASS"), scene_key="s1")
        pub = run_publishability_gate(self.tmp)
        gate = self.tmp / "PUBLISHABILITY_GATE.json"
        self.assertTrue(gate.is_file())
        disk = json.loads(gate.read_text(encoding="utf-8"))
        self.assertEqual(disk.get("publishable"), pub.get("publishable"))
        mm = self.tmp / "MULTIMODAL_QUALITY_GATE.json"
        self.assertTrue(mm.is_file())

    # TEST-19
    def test_19_idempotency_not_duplicated(self):
        from pipeline.idempotency.executor import IdempotentExecutor
        from pipeline.idempotency.store import IdempotencyStore
        import pipeline.quality.multimodal_aggregate as ma

        self.assertTrue(callable(IdempotentExecutor))
        self.assertTrue(callable(IdempotencyStore))
        self.assertFalse(hasattr(ma, "IdempotencyStore"))
        self.assertFalse(hasattr(ma, "IdempotentExecutor"))

    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    def test_20_production_call_path_bypass_and_persist(self, direct_mock):
        provider = get_mock_provider()
        provider.behavior = MockBehavior.SUCCESS
        from pipeline.idempotency.agnes_bridge import idempotent_generate_agnes_beat_result
        import pipeline.idempotency.agnes_bridge as ab

        out = self.tmp / "beat.mp4"
        real_build = ab._build_agnes_spec

        def build_with_skip(**kwargs):
            spec = real_build(**kwargs)
            spec.metadata["skip_semantic_validation"] = True
            return spec

        with mock.patch.object(ab, "_build_agnes_spec", side_effect=build_with_skip):
            result = idempotent_generate_agnes_beat_result(
                work_dir=self.tmp,
                job_id="job-p02",
                scene_id=1,
                part_index=0,
                attempt=1,
                product_name="prod",
                element="beat",
                visual_prompt="person drinks tea",
                out_path=out,
                narration_hint="The person drinks tea.",
                dialogue_id="dlg-p02",
                canonical_scene_id="scene-p02",
                use_mock=True,
                production_identity=True,
            )
        self.assertFalse(result.success)
        self.assertEqual(result.action, "identity_blocked")
        self.assertIn("skip_semantic_validation", result.detail or "")
        direct_mock.assert_not_called()

        result2 = idempotent_generate_agnes_beat_result(
            work_dir=self.tmp,
            job_id="job-p02b",
            scene_id=2,
            part_index=0,
            attempt=1,
            product_name="prod",
            element="beat",
            visual_prompt="person drinks tea with cup",
            out_path=self.tmp / "beat2.mp4",
            narration_hint="The person drinks tea at the table.",
            dialogue_id="dlg-p02b",
            canonical_scene_id="scene-p02b",
            use_mock=True,
        )
        self.assertTrue(result2.success)
        self.assertTrue(
            (self.tmp / "MULTIMODAL_QUALITY_GATE.json").is_file()
            or (self.tmp / "multimodal_gates").is_dir()
        )
    def test_high_creative_score_cannot_override_multimodal_block(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True, "overall_score": 0.99},
            multimodal_status="BLOCKED",
        )
        self.assertFalse(pub["publishable"])

    def test_bridge_loads_multimodal_from_disk(self):
        self._write_ship(True)
        self._write_creative(_creative_pass())
        persist_multimodal_report(self.tmp, _mm_report("UNKNOWN"), scene_key="u1")
        pub = run_publishability_gate(self.tmp)
        self.assertFalse(pub["publishable"])
        self.assertEqual(pub["reason"], "multimodal_unknown_mandatory")


if __name__ == "__main__":
    unittest.main(verbosity=2)
