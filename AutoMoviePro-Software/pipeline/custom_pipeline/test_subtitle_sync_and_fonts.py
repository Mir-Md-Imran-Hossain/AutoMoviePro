"""Comprehensive test suite for Subtitle Synchronization, Bengali Conjuncts & Typography."""

import tempfile
from pathlib import Path
import pytest

from pipeline.subtitle_burn import (
    font_size_for_canvas,
    margin_v_for_canvas,
    preferred_font,
    get_fonts_dir,
    burn_subtitles_filter,
    ass_force_style,
    srt_to_styled_ass,
    wrap_cue_text,
)
from pipeline.custom_pipeline.media_compose import (
    _phrase_cues,
    _write_simple_ass,
)


def test_phrase_cues_short_pacing_bounds():
    """Short-form (9:16) must split sentences into punchy 2-4 word speech-synchronized cues."""
    long_bn_sentence = "হাজার বছর আগের এই প্রাচীন রহস্যময় মন্দিরের গভীরে লুকিয়ে ছিল এক অবিশ্বাস্য গোপন সত্য যা কেউ জানত না।"
    cues = _phrase_cues(long_bn_sentence, audio_sec=8.0, lead_in=0.0, is_short=True)
    
    # Must produce multiple cues, never a single wall of text
    assert len(cues) >= 4
    assert cues[0]["start"] == 0.0
    assert abs(cues[-1]["end"] - 7.98) < 0.1 or cues[-1]["end"] <= 8.0

    for cue in cues:
        words = cue["text"].split()
        # Max 4 words per cue in short mode for rapid mobile scanning
        assert len(words) <= 4, f"Cue exceeded 4 words in short mode: {cue['text']}"
        # Start and end must be monotonic
        assert cue["end"] > cue["start"]
        dur = cue["end"] - cue["start"]
        assert 0.3 <= dur <= 3.0, f"Unreasonable cue duration: {dur}s for {cue['text']}"


def test_phrase_cues_long_pacing_bounds():
    """Long-form (16:9) must split into 3-6 word cinematic cues."""
    narr = "The entire universe is governed by mathematical principles and timeless laws of physics."
    cues = _phrase_cues(narr, audio_sec=6.0, lead_in=0.0, is_short=False)
    
    assert len(cues) >= 2
    assert cues[0]["start"] == 0.0
    for cue in cues:
        words = cue["text"].split()
        assert len(words) <= 6, f"Cue exceeded 6 words in long mode: {cue['text']}"


def test_phrase_cues_with_lead_in_timing():
    """Lead-in delay (e.g. 250ms for shot 1) must shift all cues accurately."""
    text = "রোবট বিপ্লব শুরু হয়েছে। আপনি কি প্রস্তুত?"
    cues = _phrase_cues(text, audio_sec=5.0, lead_in=0.25, is_short=True)
    assert cues[0]["start"] == 0.25
    assert cues[-1]["end"] <= 5.25


def test_preferred_font_all_languages():
    """Font resolver must pick scripts with full complex conjunct & shaping support."""
    # Bengali must use Kalpurush or Potro Sans
    bn_font = preferred_font("bn")
    assert bn_font in ("Kalpurush", "Potro Sans Bangla", "PotroSansBangla-Bold", "Nirmala UI")
    
    # Hindi must use Nirmala UI or Mangal
    hi_font = preferred_font("hi")
    assert hi_font in ("Nirmala UI", "Mangal", "Nirmala")

    # Telugu & Malayalam
    te_font = preferred_font("te")
    assert te_font in ("Nirmala UI", "Gautami", "Nirmala")
    ml_font = preferred_font("ml")
    assert ml_font in ("Nirmala UI", "Kartika", "Nirmala")

    # Urdu
    ur_font = preferred_font("ur")
    assert ur_font in ("Nirmala UI", "Segoe UI", "Arial")

    # English
    en_font = preferred_font("en")
    assert en_font in ("Arial", "Segoe UI")


def test_fonts_dir_contains_bengali_fonts():
    """Assets fonts directory must contain bundled Bengali fonts."""
    fonts_dir = Path(get_fonts_dir())
    assert fonts_dir.is_dir()
    assert (fonts_dir / "Kalpurush.ttf").is_file()
    assert (fonts_dir / "PotroSansBangla-Bold.ttf").is_file()


def test_font_size_and_canvas_typography_scaling():
    """Subtitles must be bold, large, and readable on both 9:16 and 16:9 canvas."""
    # 9:16 Short (1080x1920)
    short_fs = font_size_for_canvas(1080, 1920, is_short=True)
    short_mv = margin_v_for_canvas(1920, is_short=True)
    assert short_fs >= 72, f"Short font size too small: {short_fs}pt"
    assert short_mv >= 240, f"Short margin too low: {short_mv}px"

    # 16:9 Long (1920x1080)
    long_fs = font_size_for_canvas(1920, 1080, is_short=False)
    long_mv = margin_v_for_canvas(1080, is_short=False)
    assert long_fs >= 50, f"Long font size too small: {long_fs}pt"
    assert long_mv >= 70, f"Long margin too low: {long_mv}px"


def test_bengali_conjunct_preservation_in_ass():
    """Complex Bengali conjuncts (ক্ত, ঙ্গ, ক্ষ, ণ্ড, ত্ত, ঙ্ক) must be preserved in ASS files."""
    complex_text = "বিজ্ঞান ও প্রযুক্তি ক্ষেত্রে এক অবিশ্বাস্য আবিষ্কার।"
    cues = [{"start": 0.0, "end": 2.5, "text": complex_text}]
    
    with tempfile.TemporaryDirectory() as td:
        ass_path = Path(td) / "test_bn.ass"
        _write_simple_ass(cues, ass_path, size="1080x1920", lang="bn")
        
        assert ass_path.is_file()
        content = ass_path.read_text(encoding="utf-8")
        assert "PlayResX: 1080" in content
        assert "PlayResY: 1920" in content
        assert "ScaledBorderAndShadow: yes" in content
        assert "বিজ্ঞান" in content
        assert "প্রযুক্তি" in content
        assert "অবিশ্বাস্য" in content
        assert "আবিষ্কার" in content


def test_burn_subtitles_filter_uses_fonts_dir():
    """FFmpeg burn filter must include fontsdir option to load bundled fonts."""
    with tempfile.TemporaryDirectory() as td:
        ass_path = Path(td) / "sample.ass"
        ass_path.write_text("[Script Info]\nTitle: Test\n", encoding="utf-8")
        flt = burn_subtitles_filter(ass_path, size="1080x1920", lang="bn")
        
        assert "subtitles=" in flt
        assert "fontsdir=" in flt
        # fontsdir must point to the bundled assets/fonts dir
        fonts_dir_str = str(get_fonts_dir()).replace("\\", "/").replace(":", "\\:")
        assert fonts_dir_str in flt
