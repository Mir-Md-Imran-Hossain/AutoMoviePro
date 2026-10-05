"""Phase 6I — acoustic voice identity & delivery verification tests (Option A)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EV = ROOT / "docs" / "marathon" / "customer_product" / "phase6i_evidence"
AUDIO = ROOT / "docs" / "marathon" / "customer_product" / "phase6h_evidence" / "_gen" / "narration_positive.mp3"


class ArtifactFeatureTests(unittest.TestCase):
    def test_01_03_artifact(self):
        from pipeline.observation.audio_evidence import observe_audio_artifact

        if AUDIO.exists():
            r = observe_audio_artifact(AUDIO, customer_id="c11", channel_id="4")
            self.assertIn(r["observation_status"], ("PASS", "UNKNOWN"))
        miss = observe_audio_artifact(ROOT / "missing_6i.mp3")
        self.assertEqual(miss["observation_status"], "FAIL")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.mp3"
            p.write_bytes(b"zz")
            self.assertEqual(observe_audio_artifact(p)["observation_status"], "FAIL")

    def test_04_06_acoustic_features_unknown_embedding(self):
        from pipeline.observation.audio_evidence import observe_acoustic_features

        if not AUDIO.exists():
            self.skipTest("phase6h audio missing")
        f = observe_acoustic_features(AUDIO, customer_id="c11", channel_id="4", job_id="j")
        self.assertEqual(f["speaker_embedding"], "UNKNOWN")
        self.assertEqual(f["VOICE_IDENTITY_OBSERVATION"], "UNKNOWN")
        self.assertEqual(f["NATURALNESS_OBSERVATION"], "UNKNOWN")
        self.assertFalse(f["embedding_integrated"])
        self.assertTrue(f["technical_is_not_voice_identity_pass"])

    def test_05_unavailable_provider(self):
        from pipeline.observation.audio_evidence.acoustic import compare_acoustic_voice_identity

        r = compare_acoustic_voice_identity(candidate={"customer_id": "c11"}, generation_voice_hint="")
        self.assertEqual(r["acoustic_status"], "UNKNOWN")
        self.assertFalse(r["embedding_integrated"])


class VoiceConsistencyTests(unittest.TestCase):
    def test_07_canonical_binding(self):
        from pipeline.observation.audio_evidence import bind_voice_identity_contract
        from pipeline.production_consistency import resolve_canonical_voice_identity

        v = resolve_canonical_voice_identity(voice_profile="male", voice_identity_id="voice:male")
        b = bind_voice_identity_contract(voice_identity=v, dialogue_id="d1", scene_id="s1")
        self.assertEqual(b["VOICE_IDENTITY_OBSERVATION"], "UNKNOWN")

    def test_08_same_voice_scenes(self):
        from pipeline.observation.audio_evidence import evaluate_cross_scene_voice_consistency

        rows = [
            {"customer_id": "c11", "channel_id": "4", "voice_identity_id": "voice:male", "emotion": "neutral"},
            {"customer_id": "c11", "channel_id": "4", "voice_identity_id": "voice:male", "emotion": "concerned"},
        ]
        c = evaluate_cross_scene_voice_consistency(rows, generation_voice_hints=["guy", "guy"])
        self.assertEqual(c["acoustic_consistency"], "UNKNOWN")
        self.assertEqual(c["hint_consistency"], "CONSISTENT")
        self.assertTrue(c["emotion_change_is_not_identity_failure"])

    def test_09_different_voice_negative_heuristic(self):
        from pipeline.observation.audio_evidence import evaluate_cross_scene_voice_consistency

        c = evaluate_cross_scene_voice_consistency(
            [
                {"customer_id": "c11", "channel_id": "4", "voice_identity_id": "voice:male"},
                {"customer_id": "c11", "channel_id": "4", "voice_identity_id": "voice:male"},
            ],
            generation_voice_hints=["en-us-guyneural", "en-us-jennyneural"],
        )
        self.assertTrue(c["heuristic_mismatch_detected"])
        self.assertEqual(c["hint_consistency"], "INCONSISTENT")
        self.assertEqual(c["acoustic_consistency"], "UNKNOWN")  # not fake acoustic PASS/FAIL

    def test_10_emotion_same_voice(self):
        from pipeline.observation.audio_evidence import evaluate_voice_continuity_evidence

        c = evaluate_voice_continuity_evidence(
            [
                {"voice_identity_id": "voice:male", "emotion": "neutral"},
                {"voice_identity_id": "voice:male", "emotion": "relieved"},
            ]
        )
        self.assertEqual(c["status"], "PASS")
        self.assertTrue(c["emotion_change_is_not_identity_failure"])

    def test_11_12_low_confidence_no_reference(self):
        from pipeline.observation.audio_evidence.acoustic import compare_acoustic_voice_identity

        r = compare_acoustic_voice_identity(candidate={}, reference=None)
        self.assertEqual(r["VOICE_IDENTITY_OBSERVATION"], "UNKNOWN")
        self.assertEqual(r["acoustic_status"], "UNKNOWN")

    def test_13_14_cross_language_master_localized(self):
        from pipeline.observation.audio_evidence import observe_master_localized_voice
        from pipeline.production_consistency import resolve_canonical_voice_identity

        m = resolve_canonical_voice_identity(voice_profile="male", voice_identity_id="voice:male", language="en")
        loc = resolve_canonical_voice_identity(voice_profile="male", voice_identity_id="voice:male", language="bn")
        r = observe_master_localized_voice(master_contract=m, localized_contract=loc)
        self.assertEqual(r["acoustic_cross_language_status"], "UNKNOWN")


class DeliveryTimingJoinTests(unittest.TestCase):
    def test_15_17_delivery(self):
        from pipeline.observation.audio_evidence import observe_speech_delivery_integrity

        unk = observe_speech_delivery_integrity(
            planned_dialogues=[{"text": "hello world"}],
            speech_observation={"status": "UNKNOWN", "provider_verified": False},
        )
        self.assertEqual(unk["class"], "UNKNOWN")

        trunc = observe_speech_delivery_integrity(
            planned_dialogues=[{"text": "one two three four five six seven eight nine ten"}],
            speech_observation={"status": "PASS", "provider_verified": True, "transcript": "one two", "segments": []},
        )
        self.assertEqual(trunc["class"], "ANOMALOUS")
        self.assertIn("truncated_speech", trunc["issues"])

        silence = observe_speech_delivery_integrity(
            planned_dialogues=[{"text": "hi", "end": 5}],
            speech_observation={
                "status": "PASS",
                "provider_verified": True,
                "transcript": "hi there friend",
                "segments": [{"start": 0, "end": 0.5, "duration": 0.5}],
            },
            acoustic_features={
                "duration": 8.0,
                "speech_ratio": 0.05,
                "silence_intervals": [{"start": 1.0, "end": 5.0, "duration": 4.0}],
                "pause_distribution": {"max_gap_sec": 4.0},
            },
        )
        self.assertEqual(silence["class"], "ANOMALOUS")

    def test_18_19_timing_join(self):
        from pipeline.observation.audio_evidence import align_dialogue_audio_visual, classify_dialogue_speech_coverage

        cov = classify_dialogue_speech_coverage(
            {"dialogue_id": "d1", "start": 0, "end": 2},
            [{"start": 0, "end": 2, "text": "x", "segment_id": "s"}],
        )
        self.assertEqual(cov["coverage"], "FULL")
        join = align_dialogue_audio_visual(
            dialogue={"dialogue_id": "d1", "text": "She enters the hospital."},
            speech_observation={"transcript": "She enters the hospital.", "provider_verified": True, "status": "PASS"},
            frame_observation=None,
        )
        self.assertEqual(join["status"], "UNKNOWN")


class UnknownRepairAuthorityTests(unittest.TestCase):
    def test_20_21_unknown_blocks_no_repair(self):
        from pipeline.observation.audio_evidence import repair_handoff_from_audio_evidence
        from pipeline.semantic_coverage import attach_frame_evidence_to_semantic_report

        sem = attach_frame_evidence_to_semantic_report(
            {"overall": "PASS", "issues": [], "blocking": False},
            {"observations": [{"observation_status": "UNKNOWN"}], "audio": {"status": "UNKNOWN", "VOICE_IDENTITY_OBSERVATION": "UNKNOWN"}},
        )
        self.assertNotEqual(sem["overall"], "PASS")
        self.assertTrue(sem["blocking"])
        h = repair_handoff_from_audio_evidence(subject_id="a", audio_bridge={"status": "UNKNOWN"})
        self.assertFalse(h["repair_triggered"])

    def test_22_24_repair_structure(self):
        from pipeline.observation.audio_evidence import repair_handoff_from_audio_evidence

        h = repair_handoff_from_audio_evidence(
            subject_id="aud-6i",
            audio_bridge={"status": "FAIL", "issues": ["truncated_speech"]},
        )
        self.assertTrue(h["repair_triggered"])
        self.assertEqual(h["repair_scope"], "AUDIO_ASSET")
        self.assertFalse(h["whole_video_regeneration"])
        p = EV / "05_repair.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertFalse(data.get("whole_video_regeneration", True))

    def test_25_36_authorities(self):
        from pipeline.generation_payload import idempotent_image_clip_via_build03
        from pipeline.observation.audio_evidence.acoustic import compare_acoustic_voice_identity
        from pipeline.retrieval.common import strip_secrets
        from pipeline.story_visual_direction import architecture_integrity_snapshot

        snap = architecture_integrity_snapshot()
        self.assertTrue(snap["acoustic_voice_identity_defaults_to_unknown"])
        self.assertFalse(snap["acoustic_embedding_integrated"])
        self.assertTrue(snap["audio_evidence_is_not_voice_identity_authority"])
        self.assertFalse(snap["openmontage_agpl_imported"])
        self.assertTrue(callable(idempotent_image_clip_via_build03))
        iso = compare_acoustic_voice_identity(
            reference={"customer_id": "A"},
            candidate={"customer_id": "B"},
        )
        self.assertEqual(iso["status"], "FAIL")
        self.assertIn("cross_customer", iso["reason"])
        blob = json.dumps(strip_secrets({"token": "SECRET", "x": 1}))
        self.assertNotIn("SECRET", blob)
        for rel in (
            "pipeline/observation/audio_evidence/acoustic.py",
            "pipeline/observation/audio_evidence/observe.py",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"^\s*(from|import)\s+pyannote")
            self.assertNotRegex(text, r"^\s*(from|import)\s+.*OpenMontage")
            self.assertNotIn("third_party.OpenMontage", text)


if __name__ == "__main__":
    unittest.main()
