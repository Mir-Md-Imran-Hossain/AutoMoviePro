import unittest
import tempfile
from pathlib import Path

from pipeline.bgm_ducking import _niche_to_mood, resolve_or_synthesize_bgm, apply_bgm_ducking
from pipeline.audio_design.mix_policy import default_mix_policy, ducking_gain_db
from pipeline.compose import make_color_clip, ffprobe_duration


class TestStep6And7AudioCoherence(unittest.TestCase):
    def test_niche_to_mood_mapping(self):
        """Verify mood mapping covers all niche families."""
        self.assertEqual(_niche_to_mood("Islamic Teachings"), "spiritual")
        self.assertEqual(_niche_to_mood("Space Science"), "tech_ambient")
        self.assertEqual(_niche_to_mood("Personal Finance"), "corporate_pulse")
        self.assertEqual(_niche_to_mood("Health & Fitness"), "calm_nature")
        self.assertEqual(_niche_to_mood("True Crime Forensics"), "noir_tension")
        self.assertEqual(_niche_to_mood("Daily Motivation"), "uplifting")
        self.assertEqual(_niche_to_mood("Unknown Niche"), "cinematic_drone")

    def test_mix_policy_ducking_range(self):
        """User requirement: ducking must be within -14dB to -18dB."""
        policy = default_mix_policy()
        self.assertGreaterEqual(policy.duck_music_db, -18.0)
        self.assertLessEqual(policy.duck_music_db, -14.0)
        gain = ducking_gain_db("music", dialogue_active=True, policy=policy)
        self.assertEqual(gain, policy.duck_music_db)

    def test_synthesize_bgm_and_apply_ducking(self):
        """Synthesize an ambient track and apply sidechain ducking to a clip."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            # Create a short 3-second test clip
            clip = tmp_dir / "test_clip.mp4"
            make_color_clip(clip, seconds=3.0, size="640x360")
            self.assertTrue(clip.is_file())

            # Synthesize BGM
            bgm = resolve_or_synthesize_bgm(tmp_dir, duration_sec=3.0, niche="finance")
            self.assertIsNotNone(bgm)
            self.assertTrue(Path(bgm).is_file())

            # Apply ducking
            mastered = tmp_dir / "mastered.mp4"
            out = apply_bgm_ducking(clip, mastered, niche="finance", duck_db=-16.0)
            self.assertTrue(out.is_file())
            dur = ffprobe_duration(out)
            self.assertGreater(dur, 2.0)


if __name__ == "__main__":
    unittest.main()
