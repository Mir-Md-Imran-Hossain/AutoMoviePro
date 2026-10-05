import unittest
import tempfile
from pathlib import Path

from pipeline.subtitle_burn import (
    font_size_for_canvas,
    margin_v_for_canvas,
    ass_force_style,
    srt_to_styled_ass,
    burn_subtitles_filter,
    chunk_words_for_cues,
)
from pipeline.subtitle_align import (
    proportional_cues,
    cues_to_srt,
    validate_cues,
)


class TestStep9Subtitles(unittest.TestCase):
    def test_canvas_typography_and_safe_margins(self):
        """Short-form (9:16) must have larger bold font and elevated safe margin above TikTok UI."""
        # 9:16 vertical shorts (1080x1920)
        short_fs = font_size_for_canvas(1080, 1920, is_short=True)
        short_mv = margin_v_for_canvas(1920, is_short=True)
        self.assertGreaterEqual(short_fs, 48)
        self.assertGreaterEqual(short_mv, 180)  # Must be >= 180px safe margin above TikTok handle/sound

        # 16:9 horizontal landscape (1920x1080)
        long_fs = font_size_for_canvas(1920, 1080, is_short=False)
        long_mv = margin_v_for_canvas(1080, is_short=False)
        self.assertLess(long_fs, short_fs)
        self.assertLess(long_mv, 120)

    def test_ass_force_style_presets(self):
        """ASS style must use high-contrast bold yellow & thick outline for shorts."""
        style_short = ass_force_style(size="1080x1920", lang="en", is_short=True)
        self.assertIn("Bold=1", style_short)
        self.assertIn("Outline=4.2", style_short)
        self.assertIn("&H0000FFFF", style_short)  # Yellow
        self.assertIn("MarginR=80", style_short)  # Safe from right-side interaction icons

        style_long = ass_force_style(size="1920x1080", lang="en", is_short=False)
        self.assertIn("Bold=1", style_long)
        self.assertIn("&H00FFFFFF", style_long)  # White

    def test_proportional_cues_short_chunking(self):
        """Shorts mode in proportional_cues must break text into punchy 1-3 word cues."""
        narration = "The greatest secret to wealth is relentless discipline and extreme focus."
        cues = proportional_cues(narration, duration_sec=6.0, is_short=True)
        
        self.assertGreater(len(cues), 3)  # Sentence must be broken into multiple micro-cues
        for cue in cues:
            words = cue["text"].split()
            self.assertLessEqual(len(words), 3)  # Max 3 words per cue
            self.assertGreaterEqual(cue["end"], cue["start"])

        val = validate_cues(cues, duration_sec=6.0, spoken_text=narration)
        self.assertTrue(val["passed"], f"Validation failed: {val.get('issues')}")

    def test_srt_to_styled_ass_dynamic_short_conversion(self):
        """srt_to_styled_ass must parse SRT and output dynamic 1-3 word cues in ASS for 9:16 canvas."""
        srt_content = """1
00:00:00,000 --> 00:00:04,000
Every single morning before the sun rises champions are already working.

2
00:00:04,000 --> 00:00:08,000
They do not wait for motivation because discipline creates momentum.
"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            srt_file = tmp_path / "test.srt"
            ass_file = tmp_path / "test.ass"
            srt_file.write_text(srt_content, encoding="utf-8")

            res_ass = srt_to_styled_ass(srt_file, ass_file, size="1080x1920", lang="en", is_short=True)
            self.assertTrue(res_ass.is_file())
            content = res_ass.read_text(encoding="utf-8")

            self.assertIn("[Script Info]", content)
            self.assertIn("PlayResX: 1080", content)
            self.assertIn("PlayResY: 1920", content)
            self.assertIn("MarginV", content)
            self.assertIn(",60,80,", content)  # MarginL=60, MarginR=80

            dialogue_lines = [ln for ln in content.splitlines() if ln.startswith("Dialogue:")]
            # Original SRT had 2 sentences with 20 total words. Short mode should produce >= 6 micro-cues!
            self.assertGreaterEqual(len(dialogue_lines), 6)

    def test_burn_subtitles_filter_generation(self):
        """burn_subtitles_filter must produce valid FFmpeg subtitles filter syntax."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            srt_file = tmp_path / "caption.srt"
            srt_file.write_text("1\n00:00:00,000 --> 00:00:02,000\nStay hungry.\n", encoding="utf-8")

            vf = burn_subtitles_filter(srt_file, size="1080x1920", lang="en")
            self.assertIn("subtitles=", vf)
            self.assertTrue((tmp_path / "caption.ass").is_file())


if __name__ == "__main__":
    unittest.main()
