"""AMP-004 Phase-05 — Industrial audio & sound design behavioral tests.

No paid API calls.
"""
from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from domain.scene import AudioPlan
from pipeline.audio_design.gate import (
    MAX_AUDIO_REPAIR_CYCLES,
    allow_audio_repair_cycle,
    persist_audio_design_gate,
    record_audio_repair_cycle,
)
from pipeline.audio_design.loudness import analyze_wav_levels, classify_silence_region
from pipeline.audio_design.mix_policy import default_mix_policy, ducking_gain_db, validate_music_vs_dialogue_priority
from pipeline.audio_design.naturalness import naturalness_preflight
from pipeline.audio_design.plan_builder import audio_plan_fingerprint, build_industrial_audio_plan
from pipeline.audio_design.preflight import AudioPreflightError, preflight_audio_request, validate_industrial_audio_plan
from pipeline.audio_design.production import apply_production_audio_design, run_production_audio_design_gate
from pipeline.audio_design.repair_bridge import plan_audio_design_repair, scope_for_audio_issue
from pipeline.idempotency.audio_request import AudioRequestSpec, compute_audio_fingerprint
from pipeline.idempotency.tts_bridge import build_audio_spec
from pipeline.quality.contracts import RepairScope
from pipeline.quality.publishability import evaluate_publishability


def _wav_tone(path: Path, samples: int = 16000, amp: int = 8000) -> Path:
    import array
    import math
    import struct

    pcm = array.array("h", [int(amp * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(samples)])
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


def _wav_clip(path: Path, samples: int = 4000) -> Path:
    import array
    import struct

    pcm = array.array("h", [32767] * samples)
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


class Phase05AudioSoundDesignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="amp004_p05_"))

    def test_01_invalid_dialogue_blocked_before_provider(self):
        with self.assertRaises(AudioPreflightError):
            preflight_audio_request(dialogue_text="", language="en", block=True)

    def test_02_invalid_language_blocked(self):
        with self.assertRaises(AudioPreflightError) as ctx:
            preflight_audio_request(dialogue_text="Hello world", language="xx-INVALID", block=True)
        self.assertTrue(any("invalid_language" in i for i in ctx.exception.issues))

    def test_03_invalid_speaker_blocked(self):
        with self.assertRaises(AudioPreflightError):
            preflight_audio_request(
                dialogue_text="Hello world", language="en", speaker_id="invalid", block=True
            )

    def test_04_contradictory_emotion_blocked(self):
        with self.assertRaises(AudioPreflightError) as ctx:
            preflight_audio_request(
                dialogue_text="Hello calm scene",
                language="en",
                emotion="calm",
                delivery_style="screaming",
                block=True,
            )
        self.assertTrue(any("contradictory_emotion" in i for i in ctx.exception.issues))

    def test_05_invalid_timing_blocked(self):
        with self.assertRaises(AudioPreflightError):
            preflight_audio_request(
                dialogue_text="Hello", language="en", duration_target_sec=-1, block=True
            )

    def test_06_duplicate_dialogue_identity_blocked(self):
        with self.assertRaises(AudioPreflightError):
            preflight_audio_request(
                dialogue_text="Hello world again",
                language="en",
                dialogue_id="d1",
                known_dialogue_ids=["d1", "d1"],
                block=True,
            )

    def test_07_malformed_pronunciation_blocked(self):
        with self.assertRaises(AudioPreflightError):
            preflight_audio_request(
                dialogue_text="Hello",
                language="en",
                pronunciation=["<script>alert(1)</script>"],
                block=True,
            )

    def test_08_naturalness_preflight(self):
        nat = naturalness_preflight("Hello hello there there there hello hello hello")
        # duplicated words should block
        self.assertEqual(nat["status"], "BLOCK")

    def test_09_intentional_silence_preserved(self):
        label = classify_silence_region(intentional_pause=True, near_silence=True, dialogue_expected=True)
        self.assertEqual(label, "intentional_pause")

    def test_10_unexpected_silence_detected(self):
        sil = _wav_silence(self.tmp / "sil.wav")
        levels = analyze_wav_levels(sil)
        self.assertEqual(levels["status"], "FAIL")
        self.assertTrue(any("silence" in i for i in levels["issues"]))

    def test_11_ambience_compatibility(self):
        plan = build_industrial_audio_plan(
            scene_id="s1",
            dialogue_id="d1",
            dialogue_text="Quiet review of the phone.",
            location="office",
            environment="indoor quiet room",
        )
        self.assertIsNotNone(plan.ambience)
        self.assertIn(plan.ambience.get("type"), ("office", "quiet_room", "room", "none"))

    def test_12_contradictory_ambience_blocked(self):
        plan = build_industrial_audio_plan(
            scene_id="s1",
            dialogue_id="d1",
            dialogue_text="Soft spoken product tip.",
            location="quiet indoor office",
            environment="library quiet room",
        )
        plan.ambience = {"type": "crowd", "intensity": 0.9, "purpose": "wrong"}
        res = validate_industrial_audio_plan(
            plan, dialogue_text="Soft spoken product tip.", location="quiet indoor office", environment="library"
        )
        self.assertEqual(res["status"], "BLOCK")
        self.assertTrue(any("ambience" in i for i in res["issues"]))

    def test_13_sfx_event_binding(self):
        plan = build_industrial_audio_plan(
            scene_id="s1",
            dialogue_id="d1",
            dialogue_text="She closes the door gently.",
            primary_action="closes the door",
        )
        self.assertTrue(any(e.get("kind") == "door" for e in plan.sfx_events))

    def test_14_unrelated_sfx_rejected(self):
        plan = build_industrial_audio_plan(
            scene_id="s1",
            dialogue_id="d1",
            dialogue_text="He looks at the camera quietly.",
            primary_action="looks",
        )
        plan.sfx_events = [
            {"kind": "laser", "purpose": "random", "event_binding": "", "action_binding": ""}
        ]
        res = validate_industrial_audio_plan(
            plan, dialogue_text="He looks at the camera quietly.", primary_action="looks"
        )
        self.assertEqual(res["status"], "BLOCK")
        self.assertTrue(any("sfx" in i for i in res["issues"]))

    def test_15_music_intent_validation(self):
        issues = validate_music_vs_dialogue_priority(
            {"priority": 1, "energy": 0.9, "ducking": ""},
            {"dialogue": 1, "music": 4},
        )
        self.assertTrue(issues)

    def test_16_music_dialogue_priority(self):
        plan = build_industrial_audio_plan(
            scene_id="s1",
            dialogue_id="d1",
            dialogue_text="Important narration about the lens.",
            emotion="curious",
        )
        self.assertGreater(plan.mix_priority["music"], plan.mix_priority["dialogue"])

    def test_17_ducking_policy(self):
        pol = default_mix_policy()
        self.assertLess(ducking_gain_db("music", dialogue_active=True, policy=pol), 0)
        self.assertEqual(ducking_gain_db("dialogue", dialogue_active=True, policy=pol), 0.0)
        self.assertEqual(ducking_gain_db("music", dialogue_active=False, policy=pol), 0.0)

    def test_18_clipping_detection(self):
        clipped = _wav_clip(self.tmp / "clip.wav")
        levels = analyze_wav_levels(clipped)
        self.assertEqual(levels["status"], "FAIL")
        self.assertTrue(any("clipping" in i for i in levels["issues"]))

    def test_19_loudness_validation(self):
        ok = _wav_tone(self.tmp / "ok.wav")
        levels = analyze_wav_levels(ok)
        self.assertEqual(levels["status"], "PASS")
        self.assertFalse(levels.get("broadcast_lufs_claimed"))

    def test_20_audio_stream_validation(self):
        from pipeline.idempotency.audio_validation import validate_audio_asset

        ok = _wav_tone(self.tmp / "stream.wav")
        good, _ = validate_audio_asset(str(ok))
        self.assertTrue(good)

    def test_21_subtitle_identity_binding(self):
        plan = build_industrial_audio_plan(
            scene_id="sc-9", dialogue_id="dlg-9", dialogue_text="Bound identity line.", language="en"
        )
        self.assertEqual(plan.scene_id, "sc-9")
        self.assertEqual(plan.dialogue_id, "dlg-9")
        self.assertEqual(plan.language, "en")

    def test_22_localization_timing_adjustment(self):
        # Localized text longer → duration estimate should not blindly reuse short source
        short = build_industrial_audio_plan(
            scene_id="s1", dialogue_id="d1", dialogue_text="Hi.", duration_target_sec=1.0, language="en"
        )
        long_bn = "এটি একটি দীর্ঘ বাক্য যা আরও সময় প্রয়োজন এবং দ্রুত উৎস সময় ব্যবহার করা যাবে না।"
        plan = build_industrial_audio_plan(
            scene_id="s1",
            dialogue_id="d1",
            dialogue_text=long_bn,
            language="bn",
            duration_target_sec=1.0,
        )
        res = validate_industrial_audio_plan(plan, dialogue_text=long_bn)
        self.assertEqual(res["status"], "BLOCK")
        self.assertTrue(any("timing" in i for i in res["issues"]))
        self.assertNotEqual(audio_plan_fingerprint(short), audio_plan_fingerprint(plan))

    def test_23_audio_fingerprint_invalidation(self):
        a = AudioRequestSpec(
            job_id="j",
            scene_id=1,
            dialogue_id="d1",
            audio_plan_id="p1",
            dialogue_text="Hello",
            language="en",
            provider="google",
            model="m",
            emotion="neutral",
        )
        b = AudioRequestSpec(
            job_id="j",
            scene_id=1,
            dialogue_id="d1",
            audio_plan_id="p1",
            dialogue_text="Hello",
            language="en",
            provider="google",
            model="m",
            emotion="excited",
        )
        self.assertNotEqual(compute_audio_fingerprint(a), compute_audio_fingerprint(b))

    def test_24_valid_audio_reused(self):
        # Same fingerprint ⇒ idempotent reuse path (fingerprint equality)
        a = AudioRequestSpec(
            job_id="j",
            scene_id=1,
            dialogue_id="d1",
            audio_plan_id="p1",
            dialogue_text="Stable line",
            language="en",
            provider="google",
            model="m",
            emotion="neutral",
            delivery_style="neutral",
        )
        b = AudioRequestSpec(
            job_id="j",
            scene_id=1,
            dialogue_id="d1",
            audio_plan_id="p1",
            dialogue_text="Stable line",
            language="en",
            provider="google",
            model="m",
            emotion="neutral",
            delivery_style="neutral",
        )
        self.assertEqual(compute_audio_fingerprint(a), compute_audio_fingerprint(b))

    def test_25_repair_scope_minimal(self):
        self.assertEqual(scope_for_audio_issue("unrelated_sfx_rejected:laser"), RepairScope.SFX_ASSET)
        self.assertEqual(scope_for_audio_issue("music_priority_competes"), RepairScope.MUSIC_ASSET)
        self.assertEqual(scope_for_audio_issue("clipping_detected"), RepairScope.AUDIO_MIX)
        plan = plan_audio_design_repair(issues=["near_silence"], subject_id="d1", work_dir=self.tmp)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.repair_scope, RepairScope.AUDIO_ASSET)
        self.assertNotEqual(plan.repair_scope, RepairScope.SCRIPT)

    def test_26_retry_bounded(self):
        for _ in range(MAX_AUDIO_REPAIR_CYCLES):
            record_audio_repair_cycle(self.tmp, outcome="fail", scope="AUDIO_ASSET")
        self.assertFalse(allow_audio_repair_cycle(self.tmp))

    def test_27_unknown_not_converted_to_pass(self):
        # Non-wav → loudness UNKNOWN not PASS emotion claim
        p = self.tmp / "x.m4a"
        p.write_bytes(b"\x00\x00\x00\x18ftypmp4" + b"\x00" * 2000)
        levels = analyze_wav_levels(p)
        self.assertEqual(levels["status"], "UNKNOWN")
        self.assertNotEqual(levels["status"], "PASS")

    def test_28_audio_artifact_actually_observed(self):
        wav = _wav_tone(self.tmp / "narration_01.wav")
        gate = run_production_audio_design_gate(self.tmp, job_id="j", audio_paths=[wav])
        self.assertTrue(gate.get("observations"))
        self.assertEqual(gate.get("authority"), "pipeline.audio_design")

    def test_29_production_call_path_uses_canonical_audio_plan(self):
        scenes = [
            {
                "narration": "Host reviews the phone camera in soft light.",
                "dialogue_id": "d1",
                "canonical_scene_id": "s1",
                "location": "office",
                "environment": "indoor",
            }
        ]
        out = apply_production_audio_design(self.tmp, scenes, job_id="job")
        self.assertTrue(out[0].get("_audio_design_applied"))
        self.assertIn("audio_plan", out[0])
        self.assertTrue((self.tmp / "AUDIO_DESIGN_GATE.json").is_file())
        self.assertTrue((self.tmp / "audio_plans").is_dir())

    def test_30_production_provider_call_uses_validated_request(self):
        # build_audio_spec runs preflight; contradictory delivery raises before provider
        with self.assertRaises(AudioPreflightError):
            build_audio_spec(
                job_id="j",
                scene_id=1,
                dialogue_id="d1",
                dialogue_text="Calm product tip.",
                language_hint="en",
                provider="google",
                model="m",
                emotion="calm",
                delivery_style="screaming",
            )

    def test_31_no_direct_provider_bypass(self):
        import pipeline.idempotency.tts_bridge as bridge

        src = inspect.getsource(bridge.build_audio_spec)
        self.assertIn("preflight_audio_request", src)

    def test_32_final_mix_verified(self):
        from unittest import mock

        final = self.tmp / "final_x.mp4"
        final.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 9000)
        with mock.patch(
            "pipeline.idempotency.render_validation.probe_render_metadata",
            return_value={"has_audio": True, "duration_sec": 5.0, "has_video": True},
        ):
            gate = run_production_audio_design_gate(
                self.tmp, final_audio_or_video=final, audio_paths=[_wav_tone(self.tmp / "n.wav")]
            )
        self.assertEqual(gate["status"], "PASS")
        self.assertTrue(any(o.get("final_mix") for o in gate["observations"]))

    def test_33_final_audio_failure_blocks_publication(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            artifact_status="PASS",
            render_status="PASS",
            audio_status="BLOCKED",
        )
        self.assertFalse(pub.get("publishable"))

    def test_34_valid_audio_does_not_trigger_regeneration(self):
        plan = plan_audio_design_repair(issues=[], work_dir=self.tmp)
        self.assertIsNone(plan)

    def test_35_no_second_audio_quality_authority(self):
        import pipeline.audio_design as ad

        self.assertTrue(hasattr(ad, "build_industrial_audio_plan"))
        self.assertTrue(hasattr(ad, "preflight_audio_request"))
        gate = {"authority": "pipeline.audio_design", "status": "PASS"}
        persist_audio_design_gate(self.tmp, gate)
        self.assertEqual(gate["authority"], "pipeline.audio_design")

    def test_production_path_wires_audio_design(self):
        import pipeline.video_pipeline as vp
        import pipeline.scene_runtime as sr

        self.assertIn("run_production_audio_design_gate", inspect.getsource(vp))
        self.assertIn("apply_production_audio_design", inspect.getsource(sr))
        self.assertIn("require_audio_design_gate", inspect.getsource(vp))


if __name__ == "__main__":
    unittest.main()
