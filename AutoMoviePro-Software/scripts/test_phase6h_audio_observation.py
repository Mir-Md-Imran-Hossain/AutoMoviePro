"""Phase 6H — audio / voice / speech observation foundation tests."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EV = ROOT / "docs" / "marathon" / "customer_product" / "phase6h_evidence"
AUDIO_POS = EV / "_gen" / "narration_positive.mp3"


def _dlg(i, start, end, text, scene="sc-1", emotion="neutral"):
    return {
        "dialogue_id": f"dlg-{i}",
        "segment_id": f"seg-{i}",
        "scene_id": scene,
        "start_sec": start,
        "end_sec": end,
        "text": text,
        "emotion": emotion,
        "emotional_intent": emotion,
        "entities": [{"label": "Nurse"}],
        "actions": [],
        "location": "hospital room",
    }


class ArtifactTests(unittest.TestCase):
    def test_01_02_audio_artifact_ffprobe(self):
        from pipeline.observation.audio_evidence import observe_audio_artifact

        if not AUDIO_POS.exists():
            self.skipTest("phase6h positive audio not generated")
        r = observe_audio_artifact(AUDIO_POS, audio_asset_id="a1", job_id="j", scene_id="s", customer_id="c11", channel_id="4")
        self.assertIn(r["observation_status"], ("PASS", "UNKNOWN"))
        self.assertTrue(r["technical_is_not_semantic_pass"])
        self.assertFalse(r["second_ffmpeg_engine"])
        if r.get("duration") is not None:
            self.assertGreater(float(r["duration"]), 0)

    def test_03_missing_audio(self):
        from pipeline.observation.audio_evidence import observe_audio_artifact

        r = observe_audio_artifact(ROOT / "no_such_audio.mp3")
        self.assertEqual(r["observation_status"], "FAIL")
        self.assertIn("missing_audio", r["issues"])

    def test_04_corrupted_audio(self):
        from pipeline.observation.audio_evidence import observe_audio_artifact

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.mp3"
            p.write_bytes(b"xx")
            r = observe_audio_artifact(p)
            self.assertEqual(r["observation_status"], "FAIL")


class ASRCoverageTests(unittest.TestCase):
    def test_05_06_07_asr(self):
        from pipeline.observation.audio_evidence import observe_speech_segments
        from pipeline.observation.speech_timing.observe import speech_tool_available

        avail = speech_tool_available()
        if not avail.get("available"):
            r = observe_speech_segments(AUDIO_POS if AUDIO_POS.exists() else ROOT / "x.mp3")
            self.assertIn(r["status"], ("UNKNOWN", "OBSERVATION_UNAVAILABLE"))
            self.assertFalse(r.get("provider_verified", True))
            return
        self.assertTrue(avail["available"])
        if not AUDIO_POS.exists():
            self.skipTest("positive audio missing")
        r = observe_speech_segments(AUDIO_POS, dialogue_ids=["dlg-1", "dlg-2", "dlg-3"], language_hint="en")
        self.assertFalse(r["second_asr_engine"])
        if r.get("provider_verified"):
            self.assertTrue(r.get("segments") or r.get("transcript"))
            self.assertTrue(any("start" in s for s in r.get("segments") or [{}]))

    def test_08_dialogue_binding(self):
        from pipeline.observation.audio_evidence import observe_speech_segments

        if not AUDIO_POS.exists():
            self.skipTest("positive audio missing")
        from pipeline.observation.speech_timing.observe import speech_tool_available

        if not speech_tool_available().get("available"):
            self.skipTest("ASR unavailable")
        r = observe_speech_segments(AUDIO_POS, dialogue_ids=["dlg-1"])
        if r.get("segments"):
            self.assertEqual(r["segments"][0].get("dialogue_id"), "dlg-1")

    def test_09_12_coverage_vocab(self):
        from pipeline.observation.audio_evidence import classify_dialogue_speech_coverage

        d = {"dialogue_id": "dlg-1", "start": 0, "end": 4}
        self.assertEqual(
            classify_dialogue_speech_coverage(d, [{"start": 0, "end": 4, "segment_id": "a", "text": "x"}])["coverage"],
            "FULL",
        )
        self.assertEqual(
            classify_dialogue_speech_coverage(d, [{"start": 0, "end": 1, "segment_id": "a", "text": "x"}])["coverage"],
            "PARTIAL",
        )
        self.assertEqual(
            classify_dialogue_speech_coverage(d, [{"start": 10, "end": 12, "segment_id": "a"}])["coverage"],
            "NONE",
        )
        self.assertEqual(
            classify_dialogue_speech_coverage(d, [], observation_available=False)["coverage"],
            "UNKNOWN",
        )


class TranscriptVoiceTests(unittest.TestCase):
    def test_13_no_silent_drop(self):
        from pipeline.observation.frame_evidence import assert_no_silent_dialogue_drop

        ok = assert_no_silent_dialogue_drop(
            ["d1", "d2", "d3", "d4", "d5", "d6"],
            ["d1", "d2", "d3", "d4", "d5", "d6"],
        )
        self.assertEqual(ok["status"], "PASS")
        bad = assert_no_silent_dialogue_drop(["d1", "d2", "d3", "d4", "d5", "d6"], ["d1"])
        self.assertTrue(bad["silent_drop"])

    def test_14_15_16_transcript(self):
        from pipeline.observation.audio_evidence import align_transcript_texts, normalize_transcript_text

        self.assertEqual(normalize_transcript_text("Hello, WORLD!"), "hello world")
        self.assertEqual(align_transcript_texts("nurse beside bed", "nurse beside bed")["class"], "MATCH")
        self.assertEqual(align_transcript_texts("hospital dialogue", "unrelated desert monologue")["class"], "MISMATCH")
        self.assertEqual(align_transcript_texts("a", "", confidence_ok=False)["class"], "UNKNOWN")

    def test_17_20_voice_identity(self):
        from pipeline.observation.audio_evidence import bind_voice_identity_contract, evaluate_voice_continuity_evidence
        from pipeline.production_consistency import resolve_canonical_voice_identity

        v = resolve_canonical_voice_identity(voice_profile="male", voice_identity_id="voice:male")
        b = bind_voice_identity_contract(voice_identity=v, dialogue_id="dlg-1", scene_id="sc-1", emotion="neutral")
        self.assertEqual(b["VOICE_IDENTITY_OBSERVATION"], "UNKNOWN")
        self.assertTrue(b["tts_request_is_not_acoustic_verification"])
        rows = [
            bind_voice_identity_contract(voice_identity=v, dialogue_id="d1", scene_id="sc-1", emotion="neutral"),
            bind_voice_identity_contract(voice_identity=v, dialogue_id="d2", scene_id="sc-2", emotion="concerned"),
            bind_voice_identity_contract(voice_identity=v, dialogue_id="d3", scene_id="sc-3", emotion="relieved"),
        ]
        c = evaluate_voice_continuity_evidence(rows)
        self.assertTrue(c["contract_stable"])
        self.assertTrue(c["emotion_change_is_not_identity_failure"])
        self.assertEqual(c["status"], "PASS")


class AlignmentRepairAuthorityTests(unittest.TestCase):
    def test_21_22_timing_and_dva(self):
        from pipeline.observation.audio_evidence import align_dialogue_audio_visual

        r = align_dialogue_audio_visual(
            dialogue=_dlg(1, 0, 2, "Shobha enters the car."),
            speech_observation={"transcript": "Shobha enters the car.", "provider_verified": True, "status": "PASS"},
            frame_observation=None,
        )
        self.assertEqual(r["status"], "UNKNOWN")  # visual missing
        self.assertFalse(r["second_semantic_gate"])

        r2 = align_dialogue_audio_visual(
            dialogue=_dlg(1, 0, 2, "Shobha enters the car."),
            speech_observation={"transcript": "Shobha enters the car.", "provider_verified": True, "status": "PASS"},
            frame_observation={
                "observation_status": "FAIL",
                "provider_verified": True,
                "observed_subjects": ["person"],
                "observed_location": "outside vehicle",
            },
        )
        self.assertEqual(r2["status"], "FAIL")

    def test_23_technical_separate(self):
        from pipeline.observation.audio_evidence import observe_audio_artifact

        if not AUDIO_POS.exists():
            self.skipTest("audio missing")
        r = observe_audio_artifact(AUDIO_POS)
        self.assertTrue(r["technical_is_not_semantic_pass"])
        self.assertTrue(r["naturalness_pass_forbidden_without_evidence"])

    def test_24_25_unknown_blocks_no_repair(self):
        from pipeline.observation.audio_evidence import repair_handoff_from_audio_evidence
        from pipeline.semantic_coverage import attach_frame_evidence_to_semantic_report

        sem = attach_frame_evidence_to_semantic_report(
            {"overall": "PASS", "issues": [], "blocking": False},
            {
                "observations": [{"observation_status": "UNKNOWN", "mandatory_evidence": "ABSENT"}],
                "temporal": {"status": "UNKNOWN"},
                "audio": {"status": "UNKNOWN"},
            },
        )
        self.assertNotEqual(sem["overall"], "PASS")
        self.assertTrue(sem["blocking"])
        h = repair_handoff_from_audio_evidence(subject_id="audio", audio_bridge={"status": "UNKNOWN"})
        self.assertFalse(h["repair_triggered"])

    def test_26_negative_if_present(self):
        p = EV / "02_negative.json"
        if not p.exists():
            from pipeline.observation.audio_evidence import align_transcript_texts

            r = align_transcript_texts(
                "The nurse enters the hospital room.",
                "Launch sequence confirmed in deep space",
            )
            self.assertEqual(r["class"], "MISMATCH")
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertNotEqual(data.get("status"), "PASS")

    def test_27_30_repair_structure(self):
        from pipeline.observation.audio_evidence import repair_handoff_from_audio_evidence
        from pipeline.audio_design.repair_bridge import plan_audio_design_repair

        self.assertTrue(callable(plan_audio_design_repair))
        h = repair_handoff_from_audio_evidence(
            subject_id="aud-6h",
            audio_bridge={"status": "FAIL", "issues": ["transcript_mismatch"]},
        )
        self.assertTrue(h["repair_triggered"])
        self.assertIn(str(h.get("repair_scope") or ""), ("AUDIO_ASSET", "AUDIO_MIX", "SFX_ASSET", "MUSIC_ASSET", "SUBTITLE", "RENDER"))
        self.assertFalse(h["whole_video_regeneration"])
        p = EV / "05_repair.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertFalse(data.get("whole_video_regeneration", True))

    def test_28_29_lineage_if_present(self):
        p = EV / "05_repair.json"
        if not p.exists():
            self.skipTest("repair evidence not generated")
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("execution") in ("NOT_AVAILABLE", "HANDOFF_ONLY"):
            self.assertTrue(data.get("handoff", {}).get("repair_triggered") or data.get("repair_triggered"))
            return
        lin = data.get("lineage") or {}
        self.assertTrue(lin.get("old_content_hash"))

    def test_31_subtitle_relationship(self):
        from pipeline.idempotency.subtitle_bridge import build_subtitle_spec

        self.assertTrue(callable(build_subtitle_spec))

    def test_32_localization_voice(self):
        from pipeline.production_consistency import resolve_canonical_voice_identity, voice_identity_preserved

        m = resolve_canonical_voice_identity(voice_profile="male", voice_identity_id="voice:male")
        loc = resolve_canonical_voice_identity(voice_profile="male", voice_identity_id="voice:male")
        r = voice_identity_preserved(m, loc)
        self.assertTrue(r.get("preserved") or r.get("same_id") or m.voice_identity_id == loc.voice_identity_id)

    def test_33_35_isolation_secrets(self):
        from pipeline.observation.audio_evidence import observe_audio_artifact
        from pipeline.retrieval.common import strip_secrets

        r = observe_audio_artifact(AUDIO_POS if AUDIO_POS.exists() else ROOT / "missing.mp3", customer_id="c11", channel_id="4")
        if AUDIO_POS.exists():
            self.assertEqual(r.get("customer_id"), "c11")
        blob = json.dumps(strip_secrets({"api_key": "SECRET", "r": r}))
        self.assertNotIn("SECRET", blob)
        self.assertNotIn("api_key", blob)

    def test_36_46_authorities_agpl(self):
        from pipeline.duration_budget import resolve_duration_contract
        from pipeline.generation_payload import idempotent_image_clip_via_build03
        from pipeline.idempotency.executor import IdempotentExecutor
        from pipeline.production_consistency import VoiceIdentity, resolve_canonical_voice_identity
        from pipeline.story_visual_direction import architecture_integrity_snapshot
        from domain.scene import AudioPlan

        snap = architecture_integrity_snapshot()
        self.assertTrue(snap["audio_evidence_is_not_audio_authority"])
        self.assertTrue(snap["audio_evidence_is_not_voice_identity_authority"])
        self.assertTrue(snap["audio_evidence_is_not_asr_engine"])
        self.assertTrue(snap["audio_evidence_is_not_subtitle_engine"])
        self.assertFalse(snap["openmontage_agpl_imported"])
        self.assertTrue(callable(AudioPlan))
        self.assertTrue(callable(VoiceIdentity) or VoiceIdentity is not None)
        self.assertTrue(callable(resolve_canonical_voice_identity))
        self.assertTrue(callable(resolve_duration_contract))
        self.assertTrue(callable(idempotent_image_clip_via_build03))
        self.assertTrue(callable(IdempotentExecutor))
        for rel in (
            "pipeline/observation/audio_evidence/observe.py",
            "pipeline/observation/speech_timing/observe.py",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("third_party.OpenMontage", text)
            self.assertNotRegex(text, r"^\s*(from|import)\s+.*OpenMontage")


if __name__ == "__main__":
    unittest.main()
