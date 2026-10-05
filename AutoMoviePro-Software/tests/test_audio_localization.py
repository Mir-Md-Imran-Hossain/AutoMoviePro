"""Comprehensive unit & integration tests for Step 7: Audio & Multi-Dialect Localization.
Standard library unittest implementation (zero external dependency).

Tests:
- Native contextual dialect adaptation (bn, hi, ur, en)
- Real audio file generation (valid container, non-zero duration & size, valid sample rate)
- Local agent speech rate and word-by-word pacing inspection
- Strict QA rejection on empty (0-byte) or corrupted audio files
- Audio file format & stream inspection (inspect_audio_file)
- Quota guard caching (re-using identical synthesized audio)
- Surgical dialogue regeneration
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.audio_localization_engine import (
    AudioLocalizationEngine,
    LocalizedDialogue,
    inspect_audio_file,
)


class TestAudioLocalization(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.engine = AudioLocalizationEngine(audio_dir=Path(self.tmp_dir.name))

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_contextual_dialect_adaptation(self):
        """Verifies culturally resonant translation and dialect phrases."""
        bn_hook = self.engine.localize_dialogue(
            scene_index=1,
            source_text="Look at the universe",
            target_lang="bn",
            hook_type="greeting_hook",
        )
        self.assertIn("আসসালামু আলাইকুম", bn_hook)

        ur_hook = self.engine.localize_dialogue(
            scene_index=1,
            source_text="Look at the universe",
            target_lang="ur",
            hook_type="greeting_hook",
        )
        self.assertIn("السلام علیکم", ur_hook)

    def test_speech_synthesis_generates_real_audio(self):
        """Tests that speech synthesis produces a genuine, playable audio file (not an empty placeholder)."""
        diag = self.engine.synthesize_speech(
            scene_index=1,
            text="Artificial intelligence is transforming every sector in twenty twenty six.",
            target_lang="en",
            expected_duration_sec=3.0,
        )
        self.assertTrue(diag.passed_qa)
        audio_path = Path(diag.audio_file_path)
        self.assertTrue(audio_path.exists())
        self.assertGreater(audio_path.stat().st_size, 1000)
        self.assertGreater(diag.file_size_bytes, 1000)
        self.assertGreater(diag.duration_sec, 1.0)
        self.assertGreaterEqual(diag.sample_rate, 16000)
        self.assertIn(diag.audio_codec.lower(), ("mp3", "aac", "pcm_s16le"))
        self.assertEqual(diag.lang_code, "en")

    def test_qa_rejects_empty_audio_file(self):
        """Validates that local agent QA strictly rejects 0-byte or touch() placeholders."""
        empty_file = Path(self.tmp_dir.name) / "empty_scene.mp3"
        empty_file.touch()

        dummy_diag = LocalizedDialogue(
            scene_index=1,
            lang_code="en",
            original_text="Hello world",
            localized_text="Hello world",
            audio_file_path=str(empty_file),
            duration_sec=3.0,
            passed_qa=True,  # Initially set to True
        )

        inspected = self.engine.inspect_audio_quality(dummy_diag, "Hello world")
        self.assertFalse(inspected.passed_qa)
        self.assertEqual(inspected.duration_sec, 0.0)
        self.assertIn("Audio QA Failure", inspected.qa_notes)

    def test_qa_rejects_corrupted_audio_file(self):
        """Validates that local agent QA strictly rejects non-audio corrupted files."""
        corrupt_file = Path(self.tmp_dir.name) / "corrupt_scene.mp3"
        corrupt_file.write_bytes(b"NOT_A_VALID_AUDIO_FILE_DATA_CORRUPTED")

        dummy_diag = LocalizedDialogue(
            scene_index=2,
            lang_code="bn",
            original_text="Test",
            localized_text="Test",
            audio_file_path=str(corrupt_file),
            duration_sec=2.0,
            passed_qa=True,
        )

        inspected = self.engine.inspect_audio_quality(dummy_diag, "Test")
        self.assertFalse(inspected.passed_qa)
        self.assertIn("Audio QA Failure", inspected.qa_notes)

    def test_inspect_audio_file_metrics(self):
        """Tests ffprobe audio inspection function on valid vs invalid files."""
        # Generate valid audio
        diag = self.engine.synthesize_speech(
            scene_index=10,
            text="Testing audio inspector",
            target_lang="en",
            expected_duration_sec=2.0,
        )
        info = inspect_audio_file(Path(diag.audio_file_path))
        self.assertTrue(info["valid"])
        self.assertTrue(info["has_audio"])
        self.assertGreaterEqual(info["sample_rate"], 16000)
        self.assertGreater(info["duration_sec"], 0.5)
        self.assertGreater(info["file_size_bytes"], 1000)

        # Inspect missing file
        missing_info = inspect_audio_file(Path(self.tmp_dir.name) / "missing.mp3")
        self.assertFalse(missing_info["valid"])
        self.assertEqual(missing_info["file_size_bytes"], 0)

    def test_audio_quota_guard_caching(self):
        """Re-requesting exact dialogue uses cache without calling synthesis again."""
        diag1 = self.engine.synthesize_speech(
            scene_index=2,
            text="Hello world test",
            target_lang="bn",
            expected_duration_sec=3.0,
        )
        diag2 = self.engine.synthesize_speech(
            scene_index=2,
            text="Hello world test",
            target_lang="bn",
            expected_duration_sec=3.0,
        )
        self.assertEqual(diag1.audio_file_path, diag2.audio_file_path)
        self.assertIn("cache", diag2.qa_notes)
        self.assertTrue(diag2.passed_qa)
        self.assertGreater(diag2.file_size_bytes, 1000)

    def test_surgical_dialogue_regeneration(self):
        """Locally re-generates single dialogue line upon agent recommendation."""
        diag = self.engine.regenerate_dialogue(
            scene_index=3,
            revised_text="Revised engaging line for scene three",
            target_lang="bn",
            expected_duration_sec=4.0,
        )
        self.assertTrue(diag.passed_qa)
        self.assertEqual(diag.localized_text, "Revised engaging line for scene three")
        self.assertGreater(diag.file_size_bytes, 1000)
        self.assertGreater(diag.duration_sec, 1.0)

    def test_qa_rejects_mock_audio_marker(self):
        """Validates that local agent QA strictly rejects audio containing mock/placeholder markers."""
        mock_file = Path(self.tmp_dir.name) / "mock_audio.wav"
        mock_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEmock_audio_payload_bytes_here" * 10)

        info = inspect_audio_file(mock_file)
        self.assertFalse(info["valid"])
        self.assertIn("Mock artifact marker detected", info["error"])

        dummy_diag = LocalizedDialogue(
            scene_index=1,
            lang_code="en",
            original_text="Hello mock test",
            localized_text="Hello mock test",
            audio_file_path=str(mock_file),
            duration_sec=2.0,
            passed_qa=True,
        )
        inspected = self.engine.inspect_audio_quality(dummy_diag, "Hello mock test")
        self.assertFalse(inspected.passed_qa)
        self.assertIn("Audio QA Failure", inspected.qa_notes)

    def test_qa_rejects_undecodable_audio_packets(self):
        """Validates that local agent QA strictly rejects audio whose packets fail FFmpeg decode."""
        corrupt_mp3 = Path(self.tmp_dir.name) / "corrupt_packets.mp3"
        # Has valid ID3 tag header but garbage packets that fail decode
        corrupt_mp3.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x0aTIT2\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x44" + b"\x00\x11\x22\x33\x44\x55\x66\x77" * 50)

        info = inspect_audio_file(corrupt_mp3)
        self.assertFalse(info["valid"])
        self.assertTrue("decode" in info["error"].lower() or "error" in info["error"].lower())

    def test_qa_rejects_invalid_duration_bounds(self):
        """Validates that local agent QA rejects audio with invalid or wildly deviant duration."""
        # Generate valid clip first
        diag = self.engine.synthesize_speech(
            scene_index=4,
            text="Duration bounds verification test",
            target_lang="en",
            expected_duration_sec=2.0,
        )
        # Test with expected_duration_sec=20.0 (actual is ~2s, which is < 25% of expected)
        inspected = self.engine.inspect_audio_quality(diag, "Duration bounds verification test", expected_duration_sec=20.0)
        self.assertFalse(inspected.passed_qa)
        self.assertIn("too short", inspected.qa_notes.lower())


if __name__ == "__main__":
    unittest.main()
