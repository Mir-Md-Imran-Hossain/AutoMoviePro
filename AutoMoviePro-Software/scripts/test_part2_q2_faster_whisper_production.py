"""PART-2 Q2 — faster-whisper production ASR wiring."""
from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path


class ProductionAsrGateTests(unittest.TestCase):
    def test_missing_audio_is_unknown_not_pass(self):
        from pipeline.observation.audio_evidence.production import run_production_audio_asr_gate
        from pipeline.quality.publishability import evaluate_publishability

        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            gate = run_production_audio_asr_gate(work, job_id="t1", scenes=[])
            self.assertEqual(gate.get("status"), "UNKNOWN")
            self.assertFalse(gate.get("unknown_as_pass"))
            self.assertTrue((work / "AUDIO_ASR_EVIDENCE_GATE.json").is_file())
            pub = evaluate_publishability(
                technical_pass=True,
                creative_report={"overall_verdict": "PASS", "publishable": True},
                semantic_status="PASS",
                artifact_status="PASS",
                render_status="PASS",
                audio_status="PASS",
                localization_status="ABSENT",
                creative_production_status="PASS",
                rendering_integrity_status="PASS",
                duration_status="PASS",
                multimodal_status="ABSENT",
                multimodal_mandatory_unknown=False,
                asr_evidence_status="UNKNOWN",
            )
            self.assertFalse(pub.get("asr_dialogue_verified"))
            self.assertFalse(pub.get("asr_unknown_as_pass"))
            self.assertEqual(pub.get("asr_evidence_status"), "UNKNOWN")
            # UNKNOWN ASR must not by itself mark dialogue verified
            self.assertNotEqual(pub.get("asr_dialogue_verified"), True)

    def test_asr_fail_blocks_publishability(self):
        from pipeline.quality.publishability import evaluate_publishability

        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            semantic_status="PASS",
            artifact_status="PASS",
            render_status="PASS",
            audio_status="PASS",
            localization_status="ABSENT",
            creative_production_status="PASS",
            rendering_integrity_status="PASS",
            duration_status="PASS",
            multimodal_status="ABSENT",
            multimodal_mandatory_unknown=False,
            asr_evidence_status="FAIL",
        )
        self.assertFalse(pub.get("publishable"))
        self.assertIn("asr_evidence", str(pub.get("reason") or ""))

    def test_production_module_importable_from_pipeline(self):
        import pipeline.video_pipeline as vp

        src = Path(vp.__file__).read_text(encoding="utf-8")
        self.assertIn("run_production_audio_asr_gate", src)
        self.assertIn("audio_asr_blocked", src)


if __name__ == "__main__":
    unittest.main()
