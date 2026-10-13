"""Tests auditing subtitle synchronization, multi-language translation, and AV pacing."""
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from pipeline.dialogue_sync import DIALOGUE_TAIL_PAD_SEC
from pipeline.localization import _srt_ts, write_srt
from pipeline.subtitle_burn import (
    burn_subtitles_filter,
    chunk_words_for_cues,
    font_size_for_canvas,
    margin_v_for_canvas,
    preferred_font,
)


class TestPipelineSyncAudit(unittest.TestCase):
    def test_preferred_font_localization(self):
        # Bengali should get Kalpurush or Nirmala UI on Windows
        self.assertIn(preferred_font("bn"), ["Kalpurush", "Nirmala UI"])
        # Hindi should get Nirmala UI
        self.assertEqual(preferred_font("hi"), "Nirmala UI")
        # Urdu should get Segoe UI
        self.assertEqual(preferred_font("ur"), "Segoe UI")
        # English defaults to Arial
        self.assertEqual(preferred_font("en"), "Arial")

    def test_srt_timestamp_formatting(self):
        self.assertEqual(_srt_ts(0.0), "00:00:00,000")
        self.assertEqual(_srt_ts(1.5), "00:00:01,500")
        self.assertEqual(_srt_ts(65.123), "00:01:05,123")
        self.assertEqual(_srt_ts(3605.050), "01:00:05,050")

    def test_subtitles_timing_coverage(self):
        """Verify write_srt creates cues accurately spanning the audio duration."""
        with tempfile.TemporaryDirectory() as td:
            srt_path = Path(td) / "test.srt"
            dummy_audio = Path(td) / "test.m4a"
            dummy_audio.write_bytes(b"dummy")

            text = "এটি একটি অত্যন্ত শক্তিশালী এবং সুন্দর এআই ভিডিও ফ্যাক্টরি যা প্রতিদিন স্বয়ংক্রিয়ভাবে ভিডিও তৈরি করে।"
            # With mock duration of 5.0 seconds
            with unittest.mock.patch("pipeline.localization.ffprobe_duration", return_value=5.0):
                write_srt(text, dummy_audio, srt_path, language="bn", is_short=False)

            self.assertTrue(srt_path.is_file())
            content = srt_path.read_text(encoding="utf-8")
            self.assertIn("00:00:00,000 -->", content)
            self.assertIn("00:00:05,000", content)
            self.assertIn("ভিডিও", content)

    def test_short_form_vs_long_form_chunking(self):
        """Shorts should have punchy 1-3 word cues; longs can have up to 6 words."""
        text = "The quick brown fox jumps over the lazy dog in the bright morning sunlight"
        
        # Long form
        long_chunks = chunk_words_for_cues(text, words_per_chunk=6, is_short=False)
        # Short form
        short_chunks = chunk_words_for_cues(text, words_per_chunk=2, is_short=True)

        self.assertGreater(len(short_chunks), len(long_chunks))
        for sc in short_chunks:
            words = sc.split()
            self.assertLessEqual(len(words), 3)

    def test_canvas_typography_and_safe_zone(self):
        """Verify 9:16 vertical shorts elevate captions above platform navigation."""
        # 1080x1920 short
        fs_short = font_size_for_canvas(1080, 1920, is_short=True)
        mv_short = margin_v_for_canvas(1920, is_short=True)
        self.assertGreaterEqual(fs_short, 50)
        self.assertGreaterEqual(mv_short, 180)  # Elevated above TikTok bottom nav

        # 1920x1080 long
        fs_long = font_size_for_canvas(1920, 1080, is_short=False)
        mv_long = margin_v_for_canvas(1080, is_short=False)
        self.assertGreaterEqual(fs_long, 50)
        self.assertLess(fs_long, fs_short)
        self.assertLessEqual(mv_long, 120)

    def test_dialogue_tail_pad_constant(self):
        """Dialogue tail pad must be positive and within safe silencedetect bounds (0.5 - 1.0s)."""
        self.assertGreaterEqual(DIALOGUE_TAIL_PAD_SEC, 0.5)
        self.assertLessEqual(DIALOGUE_TAIL_PAD_SEC, 1.0)

    def test_burn_subtitles_filter_generation(self):
        """Verify ASS subtitle filter syntax for both English and Bengali."""
        with tempfile.TemporaryDirectory() as td:
            srt_path = Path(td) / "test.srt"
            srt_path.write_text(
                "1\n00:00:00,000 --> 00:00:02,500\nHello world\n\n"
                "2\n00:00:02,500 --> 00:00:05,000\nThis is AutoMovie Pro\n",
                encoding="utf-8"
            )
            flt_en = burn_subtitles_filter(srt_path, size="1080x1920", lang="en")
            self.assertIn("subtitles=", flt_en)

            srt_bn = Path(td) / "test_bn.srt"
            srt_bn.write_text(
                "1\n00:00:00,000 --> 00:00:02,500\nহ্যালো বিশ্ব\n\n"
                "2\n00:00:02,500 --> 00:00:05,000\nঅটোমুভি প্রো\n",
                encoding="utf-8"
            )
            flt_bn = burn_subtitles_filter(srt_bn, size="1080x1920", lang="bn")
            self.assertTrue("subtitles=" in flt_bn or "overlay=" in flt_bn or "movie=" in flt_bn)


if __name__ == "__main__":
    unittest.main()
