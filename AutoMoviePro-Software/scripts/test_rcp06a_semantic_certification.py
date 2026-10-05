#!/usr/bin/env python3
"""RCP-06A — Semantic certification wiring (no paid API / no generation)."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.quality.bridge import load_semantic_certification_status, run_publishability_gate
from pipeline.quality.publishability import PublishabilityVerdict, evaluate_publishability, semantic_status_allows_publish


def _pass_gates(**extra):
    base = dict(
        technical_pass=True,
        creative_report={"overall_verdict": "PASS", "publishable": True},
        multimodal_status="PASS",
        artifact_status="PASS",
        render_status="PASS",
        audio_status="PASS",
        localization_status="ABSENT",
        creative_production_status="PASS",
        rendering_integrity_status="PASS",
    )
    base.update(extra)
    return base


class Rcp06aSemanticCertificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rcp06a_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ship(self, ok: bool = True):
        (self.tmp / "MASTER_SHIP_GATE.json").write_text(
            json.dumps({"ok": ok, "unshippable": not ok}),
            encoding="utf-8",
        )

    def _creative(self):
        (self.tmp / "CREATIVE_QUALITY_GATE.json").write_text(
            json.dumps({"overall_verdict": "PASS", "publishable": True, "ok": True}),
            encoding="utf-8",
        )

    def test_01_semantic_pass_required_helper(self):
        self.assertTrue(semantic_status_allows_publish("PASS"))
        self.assertFalse(semantic_status_allows_publish("UNKNOWN"))
        self.assertFalse(semantic_status_allows_publish("FAIL"))
        self.assertFalse(semantic_status_allows_publish("ABSENT"))
        self.assertFalse(semantic_status_allows_publish(None))

    def test_02_absent_blocks_publishability(self):
        pub = evaluate_publishability(**_pass_gates(semantic_status="ABSENT"))
        self.assertFalse(pub["publishable"])
        self.assertEqual(pub["reason"], "semantic_absent_mandatory")
        self.assertEqual(pub["verdict"], PublishabilityVerdict.BLOCKED.value)

    def test_03_unknown_blocks_publishability(self):
        pub = evaluate_publishability(**_pass_gates(semantic_status="UNKNOWN"))
        self.assertFalse(pub["publishable"])
        self.assertEqual(pub["reason"], "semantic_unknown_mandatory")
        self.assertEqual(pub["verdict"], PublishabilityVerdict.UNKNOWN.value)

    def test_04_fail_blocks_publishability(self):
        pub = evaluate_publishability(**_pass_gates(semantic_status="FAIL"))
        self.assertFalse(pub["publishable"])
        self.assertEqual(pub["reason"], "semantic_blocked")

    def test_05_pass_allows_publishability(self):
        pub = evaluate_publishability(**_pass_gates(semantic_status="PASS"))
        self.assertTrue(pub["publishable"])
        self.assertEqual(pub["verdict"], PublishabilityVerdict.PUBLISHABLE.value)
        self.assertEqual(pub["semantic_status"], "PASS")

    def test_06_missing_semantic_defaults_absent_not_publishable(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            multimodal_status="PASS",
            artifact_status="PASS",
            render_status="PASS",
        )
        self.assertFalse(pub["publishable"])
        self.assertIn(pub["reason"], ("semantic_absent_mandatory", "semantic_pass_required"))

    def test_07_bridge_prefers_coverage_gate(self):
        self._ship(True)
        self._creative()
        (self.tmp / "SEMANTIC_COVERAGE_GATE.json").write_text(
            json.dumps({"verdict": "UNKNOWN", "blocking": True, "reason": "semantic_unknown"}),
            encoding="utf-8",
        )
        (self.tmp / "SEMANTIC_GATE.json").write_text(
            json.dumps({"verdict": "PASS"}),
            encoding="utf-8",
        )
        self.assertEqual(load_semantic_certification_status(self.tmp), "UNKNOWN")
        pub = run_publishability_gate(
            self.tmp,
            artifact_status="PASS",
            render_status="PASS",
            audio_status="PASS",
            creative_production_status="PASS",
            rendering_integrity_status="PASS",
            multimodal_status="PASS",
        )
        self.assertFalse(pub["publishable"])
        self.assertEqual(pub["semantic_status"], "UNKNOWN")

    def test_08_bridge_alias_gate_when_coverage_missing(self):
        self._ship(True)
        self._creative()
        (self.tmp / "SEMANTIC_GATE.json").write_text(
            json.dumps({"verdict": "PASS"}),
            encoding="utf-8",
        )
        self.assertEqual(load_semantic_certification_status(self.tmp), "PASS")
        pub = run_publishability_gate(
            self.tmp,
            artifact_status="PASS",
            render_status="PASS",
            audio_status="PASS",
            creative_production_status="PASS",
            rendering_integrity_status="PASS",
            multimodal_status="PASS",
        )
        self.assertTrue(pub["publishable"], pub)

    def test_09_job2293_like_unknown_not_publishable(self):
        """Regression: coverage UNKNOWN must never certify PUBLISHABLE (RCP-04/05/06)."""
        self._ship(True)
        self._creative()
        (self.tmp / "SEMANTIC_COVERAGE_GATE.json").write_text(
            json.dumps(
                {
                    "verdict": "UNKNOWN",
                    "blocking": True,
                    "reason": "semantic_unknown",
                    "beats": [{"overall": "UNKNOWN"}],
                }
            ),
            encoding="utf-8",
        )
        pub = run_publishability_gate(
            self.tmp,
            artifact_status="PASS",
            render_status="PASS",
            audio_status="PASS",
            localization_status="PASS",
            creative_production_status="PASS",
            rendering_integrity_status="PASS",
            multimodal_status="PASS",
        )
        self.assertFalse(pub.get("publishable"))
        self.assertNotEqual(pub.get("verdict"), PublishabilityVerdict.PUBLISHABLE.value)
        self.assertEqual(pub.get("semantic_status"), "UNKNOWN")

    def test_10_pipeline_blocks_unknown_compose(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("SEMANTIC_COVERAGE_BLOCKED:UNKNOWN", src)
        self.assertIn('SEMANTIC_GATE.json', src)
        self.assertIn("load_semantic_certification_status", src)
        # Soft-continue warning path must be gone
        self.assertNotIn("continue render but gate artifact records UNKNOWN", src)


if __name__ == "__main__":
    unittest.main()
