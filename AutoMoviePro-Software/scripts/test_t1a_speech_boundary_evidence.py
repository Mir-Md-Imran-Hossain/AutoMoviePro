#!/usr/bin/env python3
"""T1-A — Independent Speech & Boundary Evidence Pack tests.

Separates:
  - deterministic unit tests (no live model required for most)
  - REAL_MEDIA / golden integration tests (job2333 artifacts)

Does not mock the entire observer into meaninglessness for schema proofs.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

JOB2333 = (
    ROOT
    / "data"
    / "customer_generation_work"
    / "c11_marathon_customer"
    / "job2333"
)
EVIDENCE_DIR = ROOT / "docs" / "marathon" / "evidence" / "t1a"


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


def _make_cut_mp4(path: Path) -> Path:
    """Two hard color cuts (genuine scene change)."""
    with tempfile.TemporaryDirectory() as td:
        a = Path(td) / "a.mp4"
        b = Path(td) / "b.mp4"
        _make_mp4(a, 0.8, "red")
        _make_mp4(b, 0.8, "green")
        lst = Path(td) / "list.txt"
        lst.write_text(f"file '{a.as_posix()}'\nfile '{b.as_posix()}'\n", encoding="utf-8")
        subprocess.run(
            [
                _ffmpeg(),
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(lst),
                "-c",
                "copy",
                str(path),
            ],
            capture_output=True,
            check=True,
        )
    return path


def _make_kenburns_mp4(path: Path, seconds: float = 3.0) -> Path:
    """Slow zoom on a still — Ken Burns-style motion without hard cut."""
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x334455:s=640x360:d={seconds}",
            "-vf",
            "zoompan=z='min(zoom+0.0015,1.5)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=320x180:fps=24",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-t",
            str(seconds),
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    return path


class SpeechTimestampUnitTests(unittest.TestCase):
    """Deterministic unit tests — no live ASR required."""

    def test_A_segment_timestamp_schema(self):
        from pipeline.observation.speech_timing import validate_timestamp_evidence

        segs = [{"start": 0.0, "end": 1.2, "text": "hello"}]
        v = validate_timestamp_evidence(segments=segs, words=[])
        self.assertTrue(v["ok"])
        self.assertEqual(v["segment_count"], 1)

    def test_B_word_timestamp_schema(self):
        from pipeline.observation.speech_timing import validate_timestamp_evidence

        segs = [{"start": 0.0, "end": 2.0, "text": "hi there"}]
        words = [
            {"word": "hi", "start": 0.1, "end": 0.4},
            {"word": "there", "start": 0.5, "end": 1.0},
        ]
        v = validate_timestamp_evidence(segments=segs, words=words)
        self.assertTrue(v["ok"])
        self.assertEqual(v["word_count"], 2)

    def test_C_monotonicity(self):
        from pipeline.observation.speech_timing import validate_timestamp_evidence

        segs = [
            {"start": 0.0, "end": 1.0},
            {"start": 0.5, "end": 1.5},  # overlaps prior end → non-monotonic start
        ]
        v = validate_timestamp_evidence(segments=segs, words=[])
        self.assertFalse(v["ok"])
        self.assertTrue(any("non_monotonic" in i for i in v["issues"]))

    def test_D_bounds_validation(self):
        from pipeline.observation.speech_timing import validate_timestamp_evidence

        segs = [{"start": 0.0, "end": 1.0}]
        words = [{"word": "x", "start": 5.0, "end": 5.2}]  # outside
        v = validate_timestamp_evidence(segments=segs, words=words)
        self.assertFalse(v["ok"])
        self.assertTrue(any("outside" in i or "negative" in i for i in v["issues"]))

        bad = validate_timestamp_evidence(
            segments=[{"start": -1.0, "end": 0.5}],
            words=[{"word": "y", "start": 0.0, "end": -0.1}],
        )
        self.assertFalse(bad["ok"])
        self.assertTrue(any("negative" in i for i in bad["issues"]))

    def test_E_empty_failed_asr_unknown(self):
        from pipeline.observation.speech_timing import observe_speech_timing

        out = observe_speech_timing(Path("/no/such/audio_t1a.wav"))
        self.assertIn(out["status"], ("FAIL", "OBSERVATION_UNAVAILABLE", "UNKNOWN"))
        self.assertEqual(out.get("reason"), "INVALID_MEDIA")
        self.assertFalse(out.get("unknown_as_pass"))
        self.assertIn("provenance", out)

    def test_F_model_unavailable_unknown(self):
        from pipeline.observation.speech_timing import observe_speech_timing

        with mock.patch(
            "pipeline.observation.speech_timing.observe.speech_tool_available",
            return_value={"available": False, "error": "forced_t1a"},
        ):
            with tempfile.TemporaryDirectory() as td:
                wav = _make_wav(Path(td) / "a.wav", 0.4)
                out = observe_speech_timing(wav)
        self.assertEqual(out["status"], "OBSERVATION_UNAVAILABLE")
        self.assertEqual(out.get("reason"), "MODEL_UNAVAILABLE")
        self.assertFalse(out.get("unknown_as_pass"))

    def test_G_provenance_preservation_fields(self):
        from pipeline.observation.speech_timing import observe_speech_timing

        with mock.patch(
            "pipeline.observation.speech_timing.observe.speech_tool_available",
            return_value={"available": False, "error": "x"},
        ):
            with tempfile.TemporaryDirectory() as td:
                wav = _make_wav(Path(td) / "p.wav", 0.3)
                out = observe_speech_timing(wav)
        self.assertIn("provenance", out)
        self.assertIn("audio_path", out["provenance"])
        self.assertFalse(out.get("claims_semantic_truth", True))

    def test_H_backward_compat_schema_name(self):
        from pipeline.observation.common import SCHEMA_SPEECH
        from pipeline.observation.speech_timing.observe import SCHEMA_VERSION

        self.assertEqual(SCHEMA_SPEECH, "amp_observation_speech_timing_v1")
        self.assertTrue(SCHEMA_VERSION.startswith("amp_observation_speech_timing_v1"))


class SceneBoundaryUnitTests(unittest.TestCase):
    """Deterministic + synthetic media scene boundary tests."""

    def test_1_genuine_scene_cut(self):
        from pipeline.observation.scene_boundary import observe_scene_boundaries

        with tempfile.TemporaryDirectory() as td:
            vid = _make_cut_mp4(Path(td) / "cuts.mp4")
            out = observe_scene_boundaries(vid, threshold=20.0)
        self.assertTrue(out.get("observation_executed") or out["status"] == "OBSERVATION_UNAVAILABLE")
        self.assertFalse(out.get("unknown_as_pass"))
        if out.get("observation_executed") and out.get("provider_verified"):
            self.assertGreaterEqual(int(out.get("scene_count") or 0), 2)
            self.assertIn("provenance", out)
            self.assertIn("source_hash", out)

    def test_2_long_documentary_hold(self):
        from pipeline.observation.scene_boundary import (
            compare_planned_beats_vs_boundaries,
            observe_scene_boundaries,
        )

        with tempfile.TemporaryDirectory() as td:
            vid = _make_mp4(Path(td) / "hold.mp4", seconds=12.0, color="gray")
            obs = observe_scene_boundaries(vid)
        planned = [{"duration_sec": 4}, {"duration_sec": 4}, {"duration_sec": 4}]
        cmp = compare_planned_beats_vs_boundaries(
            planned_beats=planned, observed=obs, static_hold_sec=10.5
        )
        self.assertFalse(cmp.get("creates_final_gate"))
        # Soft documentary — must not hard-FAIL solely on hold/missing_cut
        self.assertEqual(cmp.get("hard_issues"), [])
        self.assertTrue(
            any("documentary_hold" in i or "static_hold" in i or "missing_cut" in i for i in (cmp.get("soft_issues") or cmp.get("issues") or []))
            or cmp["status"] in ("PASS", "UNKNOWN")
        )
        if cmp.get("soft_issues"):
            self.assertNotEqual(cmp["status"], "FAIL")

    def test_3_ken_burns_style_motion(self):
        from pipeline.observation.scene_boundary import (
            classify_boundary_issues,
            compare_planned_beats_vs_boundaries,
            observe_scene_boundaries,
        )

        # Synthetic micro-segments = Ken Burns / false flash soft class
        obs = {
            "status": "PASS",
            "observation_executed": True,
            "scenes": [
                {"start_sec": 0.0, "end_sec": 0.2},
                {"start_sec": 0.2, "end_sec": 0.4},
                {"start_sec": 0.4, "end_sec": 3.0},
            ],
            "boundary_times_sec": [0.0, 0.2, 0.4, 3.0],
        }
        planned = [{"duration_sec": 3.0}]
        cmp = compare_planned_beats_vs_boundaries(planned_beats=planned, observed=obs)
        self.assertTrue(any("ken_burns" in i or "micro" in i for i in (cmp.get("soft_issues") or [])))
        self.assertEqual(cmp.get("hard_issues"), [])
        self.assertNotEqual(cmp["status"], "FAIL")

        with tempfile.TemporaryDirectory() as td:
            try:
                vid = _make_kenburns_mp4(Path(td) / "kb.mp4", 2.5)
            except Exception:
                self.skipTest("kenburns ffmpeg filter unavailable")
            out = observe_scene_boundaries(vid)
        self.assertIn(out["status"], ("PASS", "UNKNOWN", "OBSERVATION_UNAVAILABLE", "FAIL"))
        self.assertFalse(out.get("unknown_as_pass"))

    def test_4_missing_cut_soft(self):
        from pipeline.observation.scene_boundary import compare_planned_beats_vs_boundaries

        obs = {
            "status": "PASS",
            "observation_executed": True,
            "scenes": [{"start_sec": 0, "end_sec": 12}],
            "boundary_times_sec": [0.0, 12.0],
        }
        planned = [{"duration_sec": 4}, {"duration_sec": 4}, {"duration_sec": 4}]
        cmp = compare_planned_beats_vs_boundaries(planned_beats=planned, observed=obs)
        self.assertTrue(any("missing_cut" in i for i in cmp.get("issues") or []))
        self.assertIn("missing_cut:expected_multi_beat_single_observed_scene", cmp.get("soft_issues") or [])
        self.assertEqual(cmp["status"], "PASS")
        self.assertEqual(cmp.get("hard_issues"), [])

    def test_5_empty_invalid_media(self):
        from pipeline.observation.scene_boundary import observe_scene_boundaries

        out = observe_scene_boundaries(Path("/no/video_t1a.mp4"))
        self.assertIn(out["status"], ("FAIL", "OBSERVATION_UNAVAILABLE"))
        self.assertEqual(out.get("reason"), "INVALID_MEDIA")
        self.assertIn("missing_or_tiny_video", out.get("hard_issues") or out.get("issues") or [])

    def test_6_detector_unavailable(self):
        from pipeline.observation.scene_boundary import observe_scene_boundaries

        with mock.patch(
            "pipeline.observation.scene_boundary.observe.scene_tool_available",
            return_value={"available": False, "error": "forced"},
        ):
            with tempfile.TemporaryDirectory() as td:
                vid = _make_mp4(Path(td) / "v.mp4", 1.0)
                out = observe_scene_boundaries(vid, allow_ffmpeg_fallback=False)
        self.assertEqual(out["status"], "OBSERVATION_UNAVAILABLE")
        self.assertEqual(out.get("reason"), "DETECTOR_UNAVAILABLE")
        self.assertFalse(out.get("unknown_as_pass"))

    def test_7_soft_issue_classification(self):
        from pipeline.observation.scene_boundary import classify_boundary_issues

        c = classify_boundary_issues(
            [
                "excessive_static_hold:13.0s",
                "missing_cut:expected_multi_beat_single_observed_scene",
                "missing_or_tiny_video",
            ]
        )
        self.assertIn("missing_or_tiny_video", c["hard_issues"])
        self.assertTrue(c["has_soft"])
        self.assertTrue(c["has_hard"])

    def test_8_unknown_handling(self):
        from pipeline.observation.scene_boundary import compare_planned_beats_vs_boundaries

        cmp = compare_planned_beats_vs_boundaries(
            planned_beats=[{"duration_sec": 1}],
            observed={"status": "UNKNOWN", "observation_executed": False},
        )
        self.assertEqual(cmp["status"], "UNKNOWN")
        self.assertFalse(cmp.get("unknown_as_pass"))


@unittest.skipUnless(
    JOB2333.is_dir() and (JOB2333 / "final_short.mp4").is_file(),
    "REAL_MEDIA: job2333 marathon artifact missing",
)
class RealMediaGoldenTests(unittest.TestCase):
    """REAL_MEDIA — job2333 golden ASR + scene boundary. Does not mutate job files."""

    @classmethod
    def setUpClass(cls):
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    def test_REAL_job2333_asr_word_timestamps(self):
        from pipeline.observation.speech_timing import observe_speech_timing, speech_tool_available

        avail = speech_tool_available()
        if not avail.get("available"):
            self.skipTest("faster_whisper not installed")

        audio = JOB2333 / "narration_00.m4a"
        self.assertTrue(audio.is_file(), "job2333 English narration missing")

        t0 = time.perf_counter()
        out = observe_speech_timing(audio, language_hint="en", model_size="tiny", device="cpu", compute_type="int8")
        wall = round(time.perf_counter() - t0, 3)

        # Never alter job artifact — write under marathon evidence
        payload = {
            "label": "REAL_MEDIA_GOLDEN_ASR",
            "job": "job2333",
            "audio": str(audio),
            "wall_sec": wall,
            "observation": out,
        }
        (EVIDENCE_DIR / "job2333_asr_narration_00.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        self.assertIn(out["status"], ("PASS", "FAIL", "UNKNOWN", "OBSERVATION_UNAVAILABLE"))
        self.assertFalse(out.get("unknown_as_pass"))
        if out.get("observation_executed") and out["status"] == "PASS":
            self.assertTrue(out.get("segments"))
            self.assertIn("source_hash", out)
            self.assertIn("provenance", out)
            self.assertIn("tool_version", out)
            self.assertIn("metrics", out)
            # Word timestamps if backend supports
            words = out.get("words") or []
            metrics = out.get("metrics") or {}
            if words:
                self.assertTrue(metrics.get("word_timestamps_present"))
                for w in words:
                    if w.get("start") is not None:
                        self.assertGreaterEqual(float(w["start"]), 0.0)
            else:
                # Explicit backend limitation documented in evidence
                self.assertIn("word_timestamps_absent", out.get("issues") or [])

            tv = out.get("timestamp_validation") or {}
            self.assertTrue(tv.get("ok"), msg=str(tv.get("issues")))

    def test_REAL_job2333_concat_english_master_audio(self):
        """Concatenate narration_00..04 into evidence-only master; run ASR."""
        from pipeline.observation.speech_timing import observe_speech_timing, speech_tool_available

        if not speech_tool_available().get("available"):
            self.skipTest("faster_whisper not installed")

        parts = [JOB2333 / f"narration_0{i}.m4a" for i in range(5)]
        for p in parts:
            self.assertTrue(p.is_file(), f"missing {p.name}")

        master = EVIDENCE_DIR / "job2333_english_master_concat.m4a"
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        lst = EVIDENCE_DIR / "job2333_concat_list.txt"
        lst.write_text(
            "\n".join(f"file '{p.resolve().as_posix()}'" for p in parts) + "\n",
            encoding="utf-8",
        )
        subprocess.run(
            [_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(master)],
            capture_output=True,
            check=True,
        )

        t0 = time.perf_counter()
        out = observe_speech_timing(master, language_hint="en", model_size="tiny", device="cpu", compute_type="int8")
        wall = round(time.perf_counter() - t0, 3)
        (EVIDENCE_DIR / "job2333_asr_english_master.json").write_text(
            json.dumps(
                {
                    "label": "REAL_MEDIA_GOLDEN_ASR_MASTER",
                    "job": "job2333",
                    "audio": str(master),
                    "wall_sec": wall,
                    "observation": {
                        k: out.get(k)
                        for k in (
                            "status",
                            "reason",
                            "tool",
                            "tool_version",
                            "model",
                            "source_hash",
                            "segments",
                            "words",
                            "metrics",
                            "provenance",
                            "timestamp_validation",
                            "issues",
                            "transcript",
                            "language_detected",
                        )
                    },
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )
        self.assertEqual(out.get("tool"), "faster-whisper")
        self.assertIn("provenance", out)
        if out.get("observation_executed"):
            self.assertTrue(out.get("segments") or out["status"] in ("UNKNOWN", "FAIL"))

    def test_REAL_job2333_scene_boundary(self):
        from pipeline.observation.scene_boundary import (
            compare_planned_beats_vs_boundaries,
            observe_scene_boundaries,
        )

        video = JOB2333 / "final_short.mp4"
        self.assertTrue(video.is_file())

        t0 = time.perf_counter()
        obs = observe_scene_boundaries(video)
        wall = round(time.perf_counter() - t0, 3)

        planned = [
            {"duration_sec": 10},
            {"duration_sec": 10},
            {"duration_sec": 10},
            {"duration_sec": 10},
            {"duration_sec": 10},
        ]
        cmp = compare_planned_beats_vs_boundaries(planned_beats=planned, observed=obs)

        payload = {
            "label": "REAL_MEDIA_GOLDEN_SCENE_BOUNDARY",
            "job": "job2333",
            "video": str(video),
            "wall_sec": wall,
            "observation": obs,
            "comparison": cmp,
        }
        (EVIDENCE_DIR / "job2333_scene_boundary.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        self.assertTrue(obs.get("observation_executed") or obs["status"] == "OBSERVATION_UNAVAILABLE")
        self.assertFalse(obs.get("unknown_as_pass"))
        self.assertFalse(cmp.get("unknown_as_pass"))
        if obs.get("observation_executed"):
            self.assertIn("source_hash", obs)
            self.assertIn("provenance", obs)
            self.assertGreaterEqual(int(obs.get("scene_count") or 0), 1)
            # Soft issues may exist; must remain visible; hard empty for typical doc short
            if cmp.get("soft_issues"):
                self.assertTrue(cmp.get("soft_issue_visible"))
            # Do not force PASS merely because detector produced output — status from classify
            self.assertIn(cmp["status"], ("PASS", "FAIL", "UNKNOWN", "OBSERVATION_UNAVAILABLE"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
