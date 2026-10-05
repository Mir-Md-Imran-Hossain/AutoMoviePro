#!/usr/bin/env python3
"""RCP-06D — Voice Identity Continuity (extend VoiceIdentity / AudioPlan only; paid API = 0)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.lang_config import MASTER_VOICE_NAME
from pipeline.production_consistency import (
    OBS_HEURISTIC,
    OBS_PROVIDER_VERIFIED,
    apply_voice_identity_to_audio_plan,
    assert_voice_identity_continuity_or_raise,
    create_voice_identity,
    evaluate_voice_identity_continuity,
    resolve_canonical_voice_identity,
    resolve_locked_tts_voice_name,
    voice_identity_preserved,
)
from pipeline.audio_design.plan_builder import build_industrial_audio_plan
from pipeline.audio_design.preflight import AudioPreflightError
from pipeline.audio_design.production import apply_production_audio_design


class Rcp06dVoiceIdentityTests(unittest.TestCase):
    def test_01_canonical_voice_resolves(self):
        v = resolve_canonical_voice_identity(language="en", speaker_id="Narrator")
        self.assertTrue(v.voice_identity_id)
        self.assertEqual(v.vocal_profile, MASTER_VOICE_NAME)

    def test_02_all_scenes_share_canonical(self):
        v = resolve_canonical_voice_identity(language="en")
        refs = []
        for i in range(3):
            ap = build_industrial_audio_plan(
                scene_id=f"s{i}",
                dialogue_id=f"d{i}",
                dialogue_text="hello",
                voice_profile=v.vocal_profile,
            )
            ap = apply_voice_identity_to_audio_plan(ap, v)
            refs.append({"audio_plan": ap.model_dump(), "voice_identity_id": v.voice_identity_id})
        gate = evaluate_voice_identity_continuity(canonical=v, scene_refs=refs)
        self.assertTrue(gate["ok"])
        self.assertEqual(gate["confidence"], OBS_HEURISTIC)
        self.assertFalse(gate["provider_verified"])

    def test_03_mismatch_blocks(self):
        v = resolve_canonical_voice_identity(language="en", voice_profile="Charon")
        bad = {
            "voice_identity_id": "voice:orus",
            "voice_profile": "Orus",
            "audio_plan": {"voice_profile": "Orus", "metadata": {"voice_identity_id": "voice:orus"}},
        }
        good = {
            "voice_identity_id": v.voice_identity_id,
            "voice_profile": v.vocal_profile,
            "audio_plan": {"voice_profile": v.vocal_profile, "metadata": {"voice_identity_id": v.voice_identity_id}},
        }
        gate = evaluate_voice_identity_continuity(canonical=v, scene_refs=[good, bad])
        self.assertFalse(gate["ok"])
        self.assertEqual(gate["status"], "BLOCKED")
        self.assertTrue(any("MISMATCH" in b for b in gate["blocks"]))

    def test_04_missing_canonical_not_pass(self):
        gate = evaluate_voice_identity_continuity(canonical=None, scene_refs=[{"voice_profile": "Charon"}])
        self.assertFalse(gate["ok"])
        self.assertNotEqual(gate["status"], "PASS")
        self.assertIn("VOICE_IDENTITY_MISSING:canonical", gate["blocks"])

    def test_05_voice_identity_preserved_not_provider_verified(self):
        master = create_voice_identity(voice_identity_id="voice:charon", vocal_profile="Charon", multilingual_consistent=True)
        loc = create_voice_identity(
            voice_identity_id="voice:charon",
            speaker_id=master.speaker_id,
            vocal_profile="Charon",
            language="bn",
            multilingual_consistent=True,
        )
        r = voice_identity_preserved(master, loc, language_changed=True)
        self.assertTrue(r["preserved"])
        self.assertEqual(r["confidence"], OBS_HEURISTIC)
        self.assertNotEqual(r["confidence"], OBS_PROVIDER_VERIFIED)
        self.assertFalse(r.get("provider_verified"))
        self.assertFalse(r.get("acoustic_verification"))

    def test_06_master_localized_same_contract(self):
        from pipeline.localization import assert_master_localized_voice_identity

        check = assert_master_localized_voice_identity(language="bn", voice_name=MASTER_VOICE_NAME)
        self.assertTrue(check["ok"])
        self.assertEqual(check["confidence"], OBS_HEURISTIC)

    def test_07_production_plan_binds_one_voice(self):
        from app import customer_production_plan as pp

        audio = pp._bind_audio_plans(
            [
                {"dialogue_id": "d1", "scene_id": "s1", "text": "one", "speaker": "Narrator", "emotion": "calm", "duration_sec": 3, "start_sec": 0, "end_sec": 3},
                {"dialogue_id": "d2", "scene_id": "s2", "text": "two", "speaker": "Narrator", "emotion": "calm", "duration_sec": 3, "start_sec": 3, "end_sec": 6},
            ],
            language="en",
            revision="r",
        )
        self.assertEqual(audio["status"], "BOUND")
        self.assertTrue(audio.get("voice_identity", {}).get("voice_identity_id"))
        ids = {s["voice_identity_id"] for s in audio["segments"]}
        self.assertEqual(len(ids), 1)
        self.assertTrue(audio["voice_identity_continuity"]["ok"])
        self.assertNotEqual(audio["voice_identity_continuity"].get("confidence"), OBS_PROVIDER_VERIFIED)

    def test_08_readiness_blocks_voice_mismatch(self):
        from app import customer_production_plan as pp

        v = resolve_canonical_voice_identity(language="en")
        plan = {
            "owner_login_id": "a",
            "script_revision": "r",
            "dialogue_segments": [
                {"dialogue_id": "d1", "beat_id": "b1", "scene_id": "s1", "duration_sec": 2},
                {"dialogue_id": "d2", "beat_id": "b2", "scene_id": "s2", "duration_sec": 2},
            ],
            "visual_beats": [
                {"beat_id": "v1", "dialogue_ids": ["d1"], "timing": {"duration_sec": 2}},
                {"beat_id": "v2", "dialogue_ids": ["d2"], "timing": {"duration_sec": 2}},
            ],
            "language": "en",
            "world_state": {"locations": {"x": {}}, "characters": {"n": {}}},
            "voice_identity": v.to_dict(),
            "audio_plan": {
                "status": "BOUND",
                "voice_identity": v.to_dict(),
                "segments": [
                    {
                        "dialogue_id": "d1",
                        "voice_identity_id": v.voice_identity_id,
                        "voice_profile": v.vocal_profile,
                        "audio_plan": {"voice_profile": v.vocal_profile, "metadata": {"voice_identity_id": v.voice_identity_id}},
                    },
                    {
                        "dialogue_id": "d2",
                        "voice_identity_id": "voice:other",
                        "voice_profile": "Orus",
                        "audio_plan": {"voice_profile": "Orus", "metadata": {"voice_identity_id": "voice:other"}},
                    },
                ],
            },
            "localization_plan": {"status": "BOUND"},
            "generation_modes": {"modes": ["IMAGE"]},
            "continuity": {"authority": "ContinuityTracker"},
        }
        gate = pp.evaluate_generation_readiness(plan)
        self.assertFalse(gate["ready"])
        self.assertTrue(any("VOICE_IDENTITY" in str(b) for b in gate["blocks"]))

    def test_09_audio_design_rejects_conflicting_profiles(self):
        tmp = Path(tempfile.mkdtemp())
        scenes = [
            {"narration": "a", "dialogue_id": "d1", "canonical_scene_id": "s1", "voice_profile": "Charon"},
            {"narration": "b", "dialogue_id": "d2", "canonical_scene_id": "s2", "voice_profile": "Orus"},
        ]
        with self.assertRaises(AudioPreflightError):
            apply_production_audio_design(tmp, scenes, job_id="t", block_on_critical=True)

    def test_10_audio_design_locks_same_voice(self):
        tmp = Path(tempfile.mkdtemp())
        scenes = [
            {"narration": "a", "dialogue_id": "d1", "canonical_scene_id": "s1", "language": "en"},
            {"narration": "b", "dialogue_id": "d2", "canonical_scene_id": "s2", "language": "en"},
        ]
        out = apply_production_audio_design(tmp, scenes, job_id="t", block_on_critical=True)
        profiles = {o["voice_profile"] for o in out}
        self.assertEqual(profiles, {MASTER_VOICE_NAME})
        ids = {o["voice_identity"]["voice_identity_id"] for o in out}
        self.assertEqual(len(ids), 1)

    def test_11_tts_lock_uses_canonical(self):
        v = resolve_canonical_voice_identity(language="en", voice_profile="Charon")
        name = resolve_locked_tts_voice_name({"voice_profile": "Orus"}, canonical=v)
        self.assertEqual(name, "Charon")

    def test_12_assert_raises_on_mismatch(self):
        v = resolve_canonical_voice_identity(language="en")
        with self.assertRaises(RuntimeError) as ctx:
            assert_voice_identity_continuity_or_raise(
                canonical=v,
                scene_refs=[{"voice_profile": "Orus", "voice_identity_id": "voice:orus"}],
            )
        self.assertIn("VOICE_IDENTITY_CONTINUITY_BLOCKED", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
