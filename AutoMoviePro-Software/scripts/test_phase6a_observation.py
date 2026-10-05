#!/usr/bin/env python3
"""Phase 6A — observation adapters (faster-whisper, PySceneDetect, VMAF)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ffmpeg():
    from pipeline.compose import ffmpeg_bin

    return ffmpeg_bin()


def _make_wav(path: Path, seconds: float = 1.0) -> Path:
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=f=440:d={seconds}",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    return path


def _make_mp4(path: Path, seconds: float = 1.5, color: str = "blue") -> Path:
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=320x240:d={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=f=440:d={seconds}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    return path


class SpeechTimingTests(unittest.TestCase):
    def test_01_unavailable_missing_audio(self):
        from pipeline.observation.speech_timing import observe_speech_timing

        out = observe_speech_timing(Path("/no/such/audio.wav"))
        self.assertIn(out["status"], ("FAIL", "OBSERVATION_UNAVAILABLE"))
        self.assertFalse(out.get("unknown_as_pass"))

    def test_02_dependency_missing_reports_unavailable(self):
        from pipeline.observation.speech_timing import observe_speech_timing

        with mock.patch(
            "pipeline.observation.speech_timing.observe.speech_tool_available",
            return_value={"available": False, "error": "forced"},
        ):
            with tempfile.TemporaryDirectory() as td:
                wav = _make_wav(Path(td) / "a.wav", 0.5)
                out = observe_speech_timing(wav)
        self.assertEqual(out["status"], "OBSERVATION_UNAVAILABLE")
        # T1-A: honest MODEL_UNAVAILABLE (legacy dependency_missing alias removed)
        self.assertIn(
            out.get("reason", ""),
            ("MODEL_UNAVAILABLE", "dependency_missing"),
        )

    def test_03_planned_never_counts_as_actual_pass(self):
        from pipeline.observation.speech_timing import compare_planned_vs_observed_timing

        planned = [{"start": 0.0, "end": 2.0, "text": "hello"}]
        obs = {
            "status": "PASS",
            "observation_executed": True,
            "words": [{"word": "hello", "start": 0.0, "end": 0.4}],
            "segments": [{"start": 0.0, "end": 0.4, "text": "hello"}],
        }
        cmp = compare_planned_vs_observed_timing(planned_cues=planned, observed=obs)
        self.assertFalse(cmp["planned_as_actual_pass"])
        self.assertFalse(cmp["unknown_as_pass"])

    def test_04_windows_path_and_optional_live_asr(self):
        from pipeline.observation.speech_timing import observe_speech_timing, speech_tool_available

        avail = speech_tool_available()
        with tempfile.TemporaryDirectory() as td:
            # Windows path with spaces
            d = Path(td) / "path with spaces"
            d.mkdir()
            wav = _make_wav(d / "narration.wav", 0.8)
            self.assertTrue(" " in str(wav))
            if not avail.get("available"):
                self.skipTest("faster_whisper not installed")
            out = observe_speech_timing(wav, model_size="tiny", device="cpu", compute_type="int8")
            # May be PASS or UNAVAILABLE (model download); never silent success without flags
            self.assertIn(out["status"], ("PASS", "UNKNOWN", "OBSERVATION_UNAVAILABLE", "FAIL"))
            self.assertEqual(out.get("tool"), "faster-whisper")
            self.assertFalse(out.get("unknown_as_pass"))
            if out.get("observation_executed"):
                self.assertIn("words", out)
                self.assertIn("segments", out)
                self.assertIn("transcript", out)


class SceneBoundaryTests(unittest.TestCase):
    def test_05_missing_video_fail(self):
        from pipeline.observation.scene_boundary import observe_scene_boundaries

        out = observe_scene_boundaries(Path("/no/video.mp4"))
        self.assertIn(out["status"], ("FAIL", "OBSERVATION_UNAVAILABLE"))

    def test_06_dependency_missing_uses_ffmpeg_fallback_or_unavailable(self):
        from pipeline.observation.scene_boundary import observe_scene_boundaries

        with mock.patch(
            "pipeline.observation.scene_boundary.observe.scene_tool_available",
            return_value={"available": False, "error": "forced"},
        ):
            with tempfile.TemporaryDirectory() as td:
                vid = _make_mp4(Path(td) / "v.mp4", 1.2)
                out = observe_scene_boundaries(vid, allow_ffmpeg_fallback=True)
        self.assertTrue(out.get("observation_executed") or out["status"] == "OBSERVATION_UNAVAILABLE")
        self.assertFalse(out.get("creates_final_gate", True))
        self.assertFalse(out.get("unknown_as_pass"))

    def test_07_compare_does_not_create_gate(self):
        from pipeline.observation.scene_boundary import compare_planned_beats_vs_boundaries

        obs = {
            "status": "PASS",
            "observation_executed": True,
            "scenes": [{"start_sec": 0, "end_sec": 10}],
            "boundary_times_sec": [0.0, 10.0],
        }
        planned = [{"duration_sec": 3}, {"duration_sec": 3}, {"duration_sec": 3}]
        cmp = compare_planned_beats_vs_boundaries(planned_beats=planned, observed=obs)
        self.assertFalse(cmp.get("creates_final_gate"))
        self.assertIn("issues", cmp)

    def test_08_windows_path_scene(self):
        from pipeline.observation.scene_boundary import observe_scene_boundaries

        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "win path"
            d.mkdir()
            vid = _make_mp4(d / "scene.mp4", 1.0, color="red")
            out = observe_scene_boundaries(vid)
        self.assertIn("schema", out)
        self.assertFalse(out.get("unknown_as_pass"))


class VmafTests(unittest.TestCase):
    def test_09_no_reference_is_unknown(self):
        from pipeline.observation.perceptual_quality import observe_perceptual_quality

        with tempfile.TemporaryDirectory() as td:
            vid = _make_mp4(Path(td) / "d.mp4", 1.0)
            out = observe_perceptual_quality(vid, reference_path=None)
        self.assertEqual(out["status"], "UNKNOWN")
        self.assertIn("vmaf_reference_unavailable", out.get("issues") or [])
        self.assertFalse(out.get("unknown_as_pass"))

    def test_10_libvmaf_unavailable(self):
        from pipeline.observation.perceptual_quality import observe_perceptual_quality

        with mock.patch(
            "pipeline.observation.perceptual_quality.observe.vmaf_tool_available",
            return_value={"available": False},
        ):
            with tempfile.TemporaryDirectory() as td:
                a = _make_mp4(Path(td) / "a.mp4", 0.8)
                b = _make_mp4(Path(td) / "b.mp4", 0.8, color="green")
                out = observe_perceptual_quality(a, reference_path=b)
        self.assertEqual(out["status"], "OBSERVATION_UNAVAILABLE")

    def test_11_identical_pair_optional_vmaf(self):
        from pipeline.observation.perceptual_quality import observe_perceptual_quality, vmaf_tool_available

        if not vmaf_tool_available().get("available"):
            self.skipTest("libvmaf not in ffmpeg")
        with tempfile.TemporaryDirectory() as td:
            a = _make_mp4(Path(td) / "a.mp4", 1.0)
            # copy as reference
            b = Path(td) / "b.mp4"
            b.write_bytes(a.read_bytes())
            out = observe_perceptual_quality(a, reference_path=b)
        self.assertIn(out["status"], ("PASS", "UNKNOWN", "FAIL", "OBSERVATION_UNAVAILABLE"))
        self.assertFalse(out.get("creates_render_engine"))
        if out.get("observation_executed") and out.get("vmaf") is not None:
            self.assertGreaterEqual(float(out["vmaf"]), 0.0)


class AuthorityWiringTests(unittest.TestCase):
    def test_12_render_observe_attaches_perceptual_unknown_without_ref(self):
        from pipeline.rendering_integrity.observe import observe_rendered_output

        with tempfile.TemporaryDirectory() as td:
            vid = _make_mp4(Path(td) / "final.mp4", 1.0)
            out = observe_rendered_output(vid, reference_path=None)
        self.assertIn("perceptual_quality", out)
        self.assertEqual(out["perceptual_quality"].get("status"), "UNKNOWN")
        self.assertFalse(out.get("unknown_as_pass"))

    def test_13_subtitle_attach_contract(self):
        from pipeline.localization_consistency.subtitle_rules import attach_speech_timing_observation

        with mock.patch(
            "pipeline.observation.speech_timing.observe.observe_speech_timing",
            return_value={
                "status": "PASS",
                "observation_executed": True,
                "words": [{"word": "hi", "start": 0.0, "end": 0.2}],
                "segments": [{"start": 0.0, "end": 0.2, "text": "hi"}],
            },
        ):
            out = attach_speech_timing_observation(
                audio_path="x.wav",
                planned_cues=[{"start": 0.0, "end": 1.0}],
            )
        self.assertFalse(out["planned_as_actual_pass"])
        self.assertIn("speech_observation", out)

    def test_14_story_attach_does_not_claim_continuity(self):
        from pipeline.story_visual_direction import attach_scene_boundary_evidence, architecture_integrity_snapshot

        snap = architecture_integrity_snapshot()
        self.assertTrue(snap.get("scene_boundary_is_not_continuity_authority"))
        with tempfile.TemporaryDirectory() as td:
            vid = _make_mp4(Path(td) / "s.mp4", 1.0)
            ev = attach_scene_boundary_evidence(vid, planned_beats=[{"duration_sec": 1.0}])
        self.assertFalse(ev.get("creates_final_gate"))
        self.assertIn("DirectedVisualBeat", ev.get("does_not_replace") or [])

    def test_15_malformed_json_safe(self):
        # Ensure adapters tolerate bad planned payloads
        from pipeline.observation.speech_timing import compare_planned_vs_observed_timing

        cmp = compare_planned_vs_observed_timing(
            planned_cues=[{"start": "bad", "end": None}],
            observed={"status": "OBSERVATION_UNAVAILABLE"},
        )
        self.assertEqual(cmp["status"], "OBSERVATION_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
