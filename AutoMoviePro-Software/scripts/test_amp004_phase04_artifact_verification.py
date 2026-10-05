"""AMP-004 Phase-04 — Industrial artifact verification behavioral tests.

No paid API calls. Offline fixtures + local media inspection only.
"""
from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline.artifact_verification.contracts import (
    ObservationStatus,
    MediaType,
)
from pipeline.artifact_verification.gate import (
    MAX_VERIFY_REPAIR_CYCLES,
    aggregate_artifact_gate,
    allow_another_repair_cycle,
    persist_artifact_gate,
    persist_observation,
    record_verify_cycle,
    read_verify_cycles,
)
from pipeline.artifact_verification.production import run_production_artifact_verification
from pipeline.artifact_verification.repair_bridge import (
    may_regenerate_artifact,
    plan_artifact_repair,
)
from pipeline.artifact_verification.semantic_boundary import classify_semantic_observation
from pipeline.artifact_verification.verifiers import (
    verify_audio_artifact,
    verify_composite_artifact,
    verify_subtitle_artifact,
    verify_visual_artifact,
)
from pipeline.quality.contracts import RepairScope
from pipeline.quality.publishability import evaluate_publishability


def _ftyp(path: Path, size: int = 9000) -> Path:
    path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * max(0, size - 12))
    return path


def _wav_silence(path: Path, samples: int = 8000) -> Path:
    import array
    import struct

    pcm = array.array("h", [0] * samples)
    data = pcm.tobytes()
    hdr = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        16000,
        32000,
        2,
        16,
        b"data",
        len(data),
    )
    path.write_bytes(hdr + data)
    return path


def _wav_tone(path: Path, samples: int = 16000) -> Path:
    import array
    import math
    import struct

    pcm = array.array("h", [int(8000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(samples)])
    data = pcm.tobytes()
    hdr = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        16000,
        32000,
        2,
        16,
        b"data",
        len(data),
    )
    path.write_bytes(hdr + data)
    return path


def _png(path: Path, size: int = 2000) -> Path:
    # Minimal valid PNG header + padding (not a full image decode, enough for magic)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * size)
    return path


def _srt(path: Path, text: str = "Hello world") -> Path:
    path.write_text(
        "1\n00:00:00,000 --> 00:00:01,500\n" + text + "\n\n"
        "2\n00:00:01,600 --> 00:00:03,000\nSecond cue\n",
        encoding="utf-8",
    )
    return path


class Phase04ArtifactVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="amp004_p04_"))

    def test_01_missing_artifact(self):
        obs = verify_visual_artifact(self.tmp / "missing.mp4", mode="video")
        self.assertEqual(obs.observation_status, ObservationStatus.FAIL)
        self.assertIn("missing_artifact", obs.issues)

    def test_02_corrupt_artifact(self):
        bad = self.tmp / "corrupt.mp4"
        bad.write_bytes(b"not-a-video" + b"\x00" * 9000)
        obs = verify_visual_artifact(bad, mode="video")
        self.assertEqual(obs.observation_status, ObservationStatus.FAIL)

    def test_03_invalid_video(self):
        tiny = self.tmp / "tiny.mp4"
        tiny.write_bytes(b"\x00\x00\x00\x18ftypisom")
        obs = verify_visual_artifact(tiny, mode="video", min_bytes=8000)
        self.assertEqual(obs.observation_status, ObservationStatus.FAIL)

    def test_04_invalid_audio(self):
        bad = self.tmp / "bad.wav"
        bad.write_bytes(b"XXXX" + b"\x00" * 1000)
        obs = verify_audio_artifact(bad)
        self.assertEqual(obs.observation_status, ObservationStatus.FAIL)

    def test_05_invalid_subtitle(self):
        bad = self.tmp / "bad.srt"
        bad.write_text("not a subtitle file", encoding="utf-8")
        obs = verify_subtitle_artifact(bad)
        self.assertEqual(obs.observation_status, ObservationStatus.FAIL)

    def test_06_valid_technical_artifact(self):
        wav = _wav_tone(self.tmp / "ok.wav")
        obs = verify_audio_artifact(wav, dialogue_id="d1", scene_id="s1")
        self.assertEqual(obs.technical_status, ObservationStatus.PASS)
        self.assertEqual(obs.observation_status, ObservationStatus.PASS)

    def test_07_duration_mismatch(self):
        wav = _wav_tone(self.tmp / "dur.wav", samples=16000)  # ~1s
        obs = verify_audio_artifact(wav, expected_duration_sec=10.0, duration_tolerance_sec=1.0)
        self.assertEqual(obs.observation_status, ObservationStatus.FAIL)
        self.assertTrue(any("duration_mismatch" in i for i in obs.issues))

    def test_08_stream_mismatch(self):
        # Composite without streams after probe
        bad = _ftyp(self.tmp / "nostream.mp4")
        with mock.patch(
            "pipeline.artifact_verification.verifiers.validate_render_output",
            return_value=(False, "missing_audio_stream"),
        ):
            with mock.patch(
                "pipeline.artifact_verification.verifiers.probe_render_metadata",
                return_value={
                    "duration_sec": 1.0,
                    "width": 640,
                    "height": 360,
                    "fps": 24,
                    "has_video": True,
                    "has_audio": False,
                },
            ):
                obs = verify_composite_artifact(bad, require_audio=True)
        self.assertEqual(obs.observation_status, ObservationStatus.FAIL)
        self.assertTrue(any("stream" in i or "audio" in i for i in obs.issues))

    def test_09_audio_video_timing_mismatch(self):
        srt = _srt(self.tmp / "late.srt")
        # last cue ends at 3.0; audio only 1.0
        obs = verify_subtitle_artifact(srt, audio_duration_sec=1.0)
        self.assertEqual(obs.observation_status, ObservationStatus.FAIL)
        self.assertTrue(any("timing" in i for i in obs.issues))

    def test_10_provenance_mismatch(self):
        # Intent fingerprint recorded; observation still tracks it
        wav = _wav_tone(self.tmp / "p.wav")
        obs = verify_audio_artifact(wav, intent_fp="intent-abc", dialogue_id="dlg-1")
        self.assertEqual(obs.source_intent_fingerprint, "intent-abc")
        self.assertEqual(obs.evidence.get("dialogue_identity"), "dlg-1")

    def test_11_fingerprint_mismatch(self):
        wav = _wav_tone(self.tmp / "fp.wav")
        obs = verify_audio_artifact(wav, expected_hash="deadbeef" * 8)
        self.assertEqual(obs.observation_status, ObservationStatus.FAIL)
        self.assertTrue(any("hash" in i or "fingerprint" in i for i in obs.issues))

    def test_12_semantic_unknown_is_not_pass(self):
        sem = classify_semantic_observation(
            expected={"objects": ["smartphone"]},
            observed_labels=None,
            has_pixel_or_asr_evidence=False,
        )
        self.assertEqual(sem["semantic_status"], "UNKNOWN")
        self.assertNotEqual(sem["semantic_status"], "PASS")

    def test_13_semantic_contradiction_blocks(self):
        sem = classify_semantic_observation(
            contradiction_issues=[
                {"severity": "CRITICAL", "message": "posture contradiction seated vs standing"}
            ],
            has_pixel_or_asr_evidence=True,
        )
        self.assertEqual(sem["semantic_status"], "FAIL")
        obs = verify_visual_artifact(
            _ftyp(self.tmp / "v.mp4"),
            contradiction_issues=[{"severity": "CRITICAL", "message": "entity substitution"}],
            has_pixel_evidence=True,
            observed_labels=["person"],
        )
        # container may fail L1 probe — force technical via mock
        with mock.patch(
            "pipeline.idempotency.visual_validation.validate_visual_asset",
            return_value=(True, "ok"),
        ):
            with mock.patch(
                "pipeline.artifact_verification.verifiers.probe_media",
                return_value={
                    "exists": True,
                    "decodable": True,
                    "duration": 2.0,
                    "width": 640,
                    "height": 360,
                    "fps": 24,
                    "frame_count": 48,
                    "video_streams": 1,
                    "audio_streams": 0,
                    "subtitle_streams": 0,
                    "video_codec": "h264",
                    "format_name": "mp4",
                    "size_bytes": 9000,
                },
            ):
                obs = verify_visual_artifact(
                    self.tmp / "v.mp4",
                    contradiction_issues=[
                        {"severity": "CRITICAL", "message": "object substitution contradiction"}
                    ],
                    has_pixel_evidence=True,
                    observed_labels=["laptop"],
                    expected={"objects": ["smartphone"]},
                )
        self.assertEqual(obs.observation_status, ObservationStatus.FAIL)

    def test_14_visual_entity_mismatch(self):
        with mock.patch(
            "pipeline.idempotency.visual_validation.validate_visual_asset",
            return_value=(True, "ok"),
        ):
            with mock.patch(
                "pipeline.artifact_verification.verifiers.probe_media",
                return_value={
                    "exists": True,
                    "decodable": True,
                    "duration": 2.0,
                    "width": 640,
                    "height": 360,
                    "fps": 24,
                    "frame_count": 48,
                    "video_streams": 1,
                    "audio_streams": 0,
                    "subtitle_streams": 0,
                    "video_codec": "h264",
                    "format_name": "mp4",
                    "size_bytes": 9000,
                },
            ):
                obs = verify_visual_artifact(
                    _ftyp(self.tmp / "ent.mp4"),
                    expected={"objects": ["smartphone"]},
                    observed_labels=["banana"],
                    has_pixel_evidence=True,
                )
        self.assertEqual(obs.semantic_status, ObservationStatus.FAIL)
        self.assertEqual(obs.observation_status, ObservationStatus.FAIL)

    def test_15_object_identity_mismatch(self):
        sem = classify_semantic_observation(
            expected={"objects": ["red smartphone"]},
            observed_labels=["blue tablet"],
            has_pixel_or_asr_evidence=True,
        )
        self.assertEqual(sem["semantic_status"], "FAIL")

    def test_16_continuity_contradiction(self):
        sem = classify_semantic_observation(
            contradiction_issues=[
                {"severity": "CRITICAL", "message": "continuity break: unexplained location jump"}
            ],
        )
        self.assertEqual(sem["semantic_status"], "FAIL")

    def test_17_final_composite_independently_verified(self):
        path = _ftyp(self.tmp / "final_x.mp4")
        with mock.patch(
            "pipeline.artifact_verification.verifiers.validate_render_output",
            return_value=(True, "ok"),
        ):
            with mock.patch(
                "pipeline.artifact_verification.verifiers.probe_render_metadata",
                return_value={
                    "duration_sec": 5.0,
                    "width": 1280,
                    "height": 720,
                    "fps": 30,
                    "has_video": True,
                    "has_audio": True,
                },
            ):
                obs = verify_composite_artifact(path, job_id="j1")
        self.assertEqual(obs.layer, "E")
        self.assertTrue(obs.evidence.get("independent_of_sources"))
        self.assertEqual(obs.technical_status, ObservationStatus.PASS)

    def test_18_repair_scope_remains_minimal(self):
        wav = _wav_silence(self.tmp / "sil.wav")
        obs = verify_audio_artifact(wav)
        # silence → FAIL
        plan = plan_artifact_repair(obs, attempt=1, work_dir=self.tmp)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.repair_scope, RepairScope.AUDIO_ASSET)
        self.assertNotEqual(plan.repair_scope, RepairScope.SCRIPT)

    def test_19_valid_upstream_artifact_is_reused(self):
        wav = _wav_tone(self.tmp / "reuse.wav")
        obs = verify_audio_artifact(wav)
        self.assertFalse(may_regenerate_artifact(prior_observation=obs, current_fingerprint=obs.artifact_fingerprint))

    def test_20_no_uncontrolled_regeneration_loop(self):
        for i in range(MAX_VERIFY_REPAIR_CYCLES):
            record_verify_cycle(self.tmp, outcome="fail", repair_scope="VISUAL_ASSET")
        self.assertFalse(allow_another_repair_cycle(self.tmp))
        data = read_verify_cycles(self.tmp)
        self.assertTrue(data.get("exhausted"))

    def test_21_mandatory_unknown_blocks_publication(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            artifact_status="UNKNOWN",
            render_status="PASS",
        )
        self.assertFalse(pub.get("publishable"))

    def test_22_artifact_fail_blocks_publication(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            artifact_status="BLOCKED",
            render_status="PASS",
        )
        self.assertFalse(pub.get("publishable"))
        # High creative score cannot override
        pub2 = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True, "score": 0.99},
            artifact_status="FAIL",
            render_status="PASS",
        )
        self.assertFalse(pub2.get("publishable"))

    def test_23_valid_artifact_can_publish(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            artifact_status="PASS",
            render_status="PASS",
            multimodal_status="PASS",
            semantic_status="PASS",
        )
        self.assertTrue(pub.get("publishable"))

    def test_24_observation_persisted(self):
        wav = _wav_tone(self.tmp / "pers.wav")
        obs = verify_audio_artifact(wav, artifact_id="audio:pers")
        path = persist_observation(self.tmp, obs)
        self.assertTrue(path.is_file())

    def test_25_provenance_persisted(self):
        gate = aggregate_artifact_gate([], job_id="j", final_verified=False)
        gate["provenance_chain"] = ["Research", "Observation", "Publication"]
        path = persist_artifact_gate(self.tmp, gate)
        self.assertTrue(path.is_file())
        data = path.read_text(encoding="utf-8")
        self.assertIn("provenance_chain", data)

    def test_26_retry_preserves_artifact_identity_rules(self):
        wav = _wav_tone(self.tmp / "id.wav")
        obs1 = verify_audio_artifact(wav, dialogue_id="d9", scene_id="s9")
        obs2 = verify_audio_artifact(wav, dialogue_id="d9", scene_id="s9")
        self.assertEqual(obs1.artifact_fingerprint, obs2.artifact_fingerprint)
        self.assertEqual(obs1.dialogue_id, obs2.dialogue_id)

    def test_27_no_second_artifact_verification_authority(self):
        import pipeline.artifact_verification as av

        self.assertTrue(hasattr(av, "run_production_artifact_verification"))
        # Sole package authority string
        gate = run_production_artifact_verification(self.tmp, discover_sources=False)
        # Without final → UNKNOWN unverified
        self.assertEqual(gate.get("authority"), "pipeline.artifact_verification")

    def test_28_production_path_actually_performs_artifact_verification(self):
        import pipeline.video_pipeline as vp

        src = inspect.getsource(vp)
        self.assertIn("run_production_artifact_verification", src)
        self.assertIn("require_artifact_gate", src)

    def test_29_no_manual_only_production_invocation(self):
        # Production entry is callable without developer manually constructing tracker
        final = _ftyp(self.tmp / "final_product_review.mp4")
        with mock.patch(
            "pipeline.artifact_verification.verifiers.validate_render_output",
            return_value=(True, "ok"),
        ):
            with mock.patch(
                "pipeline.artifact_verification.verifiers.probe_render_metadata",
                return_value={
                    "duration_sec": 3.0,
                    "width": 640,
                    "height": 360,
                    "fps": 24,
                    "has_video": True,
                    "has_audio": True,
                },
            ):
                gate = run_production_artifact_verification(
                    self.tmp,
                    final_path=final,
                    scenes=[],
                    job_id="auto",
                    discover_sources=False,
                )
        self.assertEqual(gate.get("status"), "PASS")
        self.assertTrue((self.tmp / "ARTIFACT_GATE.json").is_file())

    def test_30_technical_pass_does_not_imply_semantic_pass(self):
        wav = _wav_tone(self.tmp / "tech.wav")
        obs = verify_audio_artifact(wav)
        self.assertEqual(obs.technical_status, ObservationStatus.PASS)
        self.assertEqual(obs.semantic_status, ObservationStatus.UNKNOWN)
        self.assertNotEqual(obs.semantic_status, ObservationStatus.PASS)

    def test_gate_blocked_on_fail_observation(self):
        obs = verify_visual_artifact(self.tmp / "nope.mp4")
        gate = aggregate_artifact_gate([obs], job_id="j", final_verified=True)
        self.assertEqual(gate["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
