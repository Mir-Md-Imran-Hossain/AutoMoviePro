#!/usr/bin/env python3
"""RCP-07 blocker fix — TTS key failover + BN remux SRT path (no paid API required)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.tts_key_map import (
    keys_for_tts_language_with_fallback,
    on_tts_key_rejected,
    reset_english_rotation,
)
from pipeline.quota_backoff import record_key_quota_hit, reset_quota_state


class TtsFailoverTests(unittest.TestCase):
    def setUp(self):
        reset_english_rotation(0)
        # Isolate from leftover per-key cool-downs from prior test runs
        reset_quota_state(keep_per_key=False)

    def tearDown(self):
        reset_quota_state(keep_per_key=False)

    def test_01_en_failover_list_walks_pool(self):
        keys = [f"key{i}_xxxx{i}" for i in range(5)]
        ordered = keys_for_tts_language_with_fallback(keys, "en")
        self.assertEqual(len(ordered), 5)
        self.assertEqual(ordered[0], keys[0])

    def test_02_cooled_key_skipped_when_siblings_healthy(self):
        keys = ["alpha_KEYAAA1", "beta_KEYBBB2", "gamma_KEYCCC3"]
        record_key_quota_hit(keys[0], "google")
        ordered = keys_for_tts_language_with_fallback(keys, "en")
        self.assertNotIn(keys[0], ordered)
        self.assertIn(keys[1], ordered)

    def test_03_429_advances_en_rotation(self):
        reset_english_rotation(0)
        keys = ["k0_AAAA", "k1_BBBB", "k2_CCCC"]
        first = keys_for_tts_language_with_fallback(keys, "en")[0]
        on_tts_key_rejected("en", reason="429_or_quota")
        second = keys_for_tts_language_with_fallback(keys, "en")[0]
        self.assertNotEqual(first, second)

    def test_04_bn_prefers_dedicated_then_failover(self):
        keys = [f"slot{i}_ZZZZ{i}" for i in range(5)]
        ordered = keys_for_tts_language_with_fallback(keys, "bn")
        self.assertEqual(ordered[0], keys[0])  # bn dedicated index 0
        self.assertGreaterEqual(len(ordered), 2)

    def test_05_synthesize_failsover_next_key_on_429(self):
        from pipeline import tts_google

        keys = ["bad_KEY1111", "good_KEY2222"]
        calls = []

        def fake_sdk(api_key, prompt, *, model, voice_name):
            calls.append(api_key[-4:])
            if api_key.endswith("1111"):
                raise RuntimeError("429 RESOURCE_EXHAUSTED You exceeded your current quota")
            return b"\x00\x00" * 8000

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "narration.m4a"
            with mock.patch.object(tts_google, "_tts_via_sdk", side_effect=fake_sdk), mock.patch.object(
                tts_google, "_tts_via_rest", return_value=None
            ), mock.patch.object(tts_google, "_pcm_to_wav"), mock.patch.object(
                tts_google, "_wav_to_m4a", return_value=True
            ), mock.patch("pipeline.google_api_gate._record_call"), mock.patch(
                "pipeline.tts_key_map.on_tts_success"
            ):
                path = tts_google.synthesize_narration(
                    "Hello world for failover test.",
                    out,
                    language_hint="en",
                    google_api_keys=keys,
                    voice_name="Charon",
                    allow_idempotent_edge_fallback=False,
                )
        self.assertTrue(Path(path).exists() or str(path).endswith(".m4a"))
        self.assertIn("1111", calls)
        self.assertIn("2222", calls)
        # First key must not be retried after 429 before failover
        self.assertEqual(calls.count("1111"), 1)

    def test_06_exhausted_log_not_used_for_non_quota(self):
        from pipeline import tts_google

        keys = ["only_KEY9999"]

        def boom(*a, **k):
            raise RuntimeError("connection reset by peer")

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "n.m4a"
            with mock.patch.object(tts_google, "_tts_via_sdk", side_effect=boom), mock.patch.object(
                tts_google, "_tts_via_rest", side_effect=boom
            ), mock.patch("pipeline.google_api_gate._record_call"), mock.patch(
                "pipeline.edge_tts_fallback.synthesize_edge_tts", side_effect=RuntimeError("edge_down")
            ), self.assertLogs("pipeline.tts_google", level="WARNING") as cm:
                with self.assertRaises(RuntimeError):
                    tts_google.synthesize_narration(
                        "x",
                        out,
                        language_hint="en",
                        google_api_keys=keys,
                        allow_idempotent_edge_fallback=False,
                        max_retries_per_key=1,
                    )
            joined = "\n".join(cm.output)
            self.assertNotIn("Google TTS exhausted", joined)
            self.assertIn("Google TTS unavailable", joined)

    def test_09_403_suspended_failsover_without_retry_spam(self):
        from pipeline import tts_google

        keys = ["susp_KEY20hY", "good_KEY3333"]
        calls = []

        def fake_sdk(api_key, prompt, *, model, voice_name):
            calls.append(api_key[-4:])
            if api_key.endswith("20hY"):
                raise RuntimeError(
                    "403 PERMISSION_DENIED. Consumer 'api_key:AIzaSyFAKESECRET_REDACTED20hY' has been suspended."
                )
            return b"\x00\x00" * 8000

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "n.m4a"
            with mock.patch.object(tts_google, "_tts_via_sdk", side_effect=fake_sdk), mock.patch.object(
                tts_google, "_tts_via_rest", return_value=None
            ), mock.patch.object(tts_google, "_pcm_to_wav"), mock.patch.object(
                tts_google, "_wav_to_m4a", return_value=True
            ), mock.patch("pipeline.google_api_gate._record_call"), mock.patch(
                "pipeline.tts_key_map.on_tts_success"
            ), self.assertLogs("pipeline.tts_google", level="WARNING") as cm:
                tts_google.synthesize_narration(
                    "Hello",
                    out,
                    language_hint="en",
                    google_api_keys=keys,
                    allow_idempotent_edge_fallback=False,
                )
            joined = "\n".join(cm.output)
            self.assertNotIn("AIzaSy", joined)
        self.assertEqual(calls.count("20hY"), 1)
        self.assertIn("3333", calls)


class BnRemuxSrtPathTests(unittest.TestCase):
    def test_07_remux_uses_provided_subtitles_srt_not_missing_video_srt(self):
        from pipeline.localization import remux_replace_audio
        from pipeline.compose import ffmpeg_bin, ffprobe_duration
        import subprocess

        ffmpeg = ffmpeg_bin()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            video = td / "en_scene.mp4"
            audio = td / "bn_narr.m4a"
            # tiny silent video + audio via ffmpeg
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=f=440:d=1", "-c:a", "aac", str(audio)],
                capture_output=True,
                check=True,
            )
            lang_dir = td / "SCENE_LOCAL" / "00" / "bn"
            lang_dir.mkdir(parents=True)
            srt = lang_dir / "subtitles.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nপরীক্ষা\n", encoding="utf-8")
            dest = lang_dir / "video.mp4"
            # Intentionally do NOT create video.srt — old bug expected this path
            out = remux_replace_audio(
                video_src=video,
                audio_src=audio,
                dest=dest,
                subtitle_text="পরীক্ষা",
                subtitle_file=srt,
                lang_code="bn",
                size="320x240",
            )
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 1000)
            self.assertGreater(ffprobe_duration(out), 0.3)
            # Remux must succeed without sibling video.srt (old bug required it)
            self.assertFalse(dest.with_suffix(".srt").exists())
            self.assertTrue(srt.is_file())

    def test_08_idempotent_reuse_path_is_honored(self):
        from pipeline.localization import remux_replace_audio, write_srt
        from pipeline.compose import ffmpeg_bin
        import subprocess

        ffmpeg = ffmpeg_bin()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = td / "job"
            work.mkdir()
            video = td / "en.mp4"
            audio = td / "a.m4a"
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=f=880:d=1", "-c:a", "aac", str(audio)],
                capture_output=True,
                check=True,
            )
            lang = td / "bn"
            lang.mkdir()
            first = write_srt(
                "বাংলা সাবটাইটেল",
                audio,
                lang / "subtitles.srt",
                work_dir=work,
                job_id="job",
                scene_id="0",
                dialogue_id="loc-00-bn",
                language="bn",
            )
            # Second write with different candidate should reuse first via idempotency
            second = write_srt(
                "বাংলা সাবটাইটেল",
                audio,
                lang / "video.srt",
                work_dir=work,
                job_id="job",
                scene_id="0",
                dialogue_id="loc-00-bn",
                language="bn",
            )
            self.assertEqual(first.resolve(), second.resolve())
            dest = lang / "video.mp4"
            out = remux_replace_audio(
                video_src=video,
                audio_src=audio,
                dest=dest,
                subtitle_text="বাংলা সাবটাইটেল",
                subtitle_file=second,
                lang_code="bn",
                size="320x240",
                work_dir=work,
                scene_id="0",
                dialogue_id="loc-00-bn",
            )
            self.assertTrue(out.is_file() and out.stat().st_size > 1000)


if __name__ == "__main__":
    unittest.main()
