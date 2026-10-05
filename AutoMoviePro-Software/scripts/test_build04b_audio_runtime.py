#!/usr/bin/env python3
"""BUILD-04B audio/TTS runtime tests (offline, mock provider)."""
from __future__ import annotations

import json
import shutil
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.idempotency.audio_provenance import load_audio_provenance
from pipeline.idempotency.audio_request import AudioRequestSpec, compute_audio_fingerprint
from pipeline.idempotency.audio_runtime import execute_audio_request
from pipeline.idempotency.embedded_audio import should_skip_english_tts_generation
from pipeline.idempotency.mock_audio_provider import MockAudioBehavior, MockAudioProvider, reset_mock_audio_provider
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyRecord, IdempotencyStore


def _spec(**kw) -> AudioRequestSpec:
    base = dict(
        job_id="job-1",
        scene_id=3,
        dialogue_id="d03",
        audio_plan_id="plan-d03",
        dialogue_text="This is the original dialogue.",
        language="en",
        provider="google",
        model="gemini-2.5-flash-preview-tts",
        voice_id="Charon",
        emotion="neutral",
        speaking_speed=1.0,
    )
    base.update(kw)
    return AudioRequestSpec(**base)


class Build04BAudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mock = MockAudioProvider()
        self.mock.reset()
        reset_mock_audio_provider()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, spec=None, **kw):
        spec = spec or _spec()
        out = self.tmp / "narration.wav"
        return execute_audio_request(
            self.tmp, spec, out, use_mock=True, mock_provider=self.mock, **kw
        )

    def test_01_same_request_twice(self):
        r1 = self._run()
        r2 = self._run()
        self.assertEqual(r1.action, "execute")
        self.assertEqual(r2.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 1)

    def test_02_dialogue_changed(self):
        self.assertNotEqual(_spec().fingerprint(), _spec(dialogue_text="Modified dialogue.").fingerprint())

    def test_03_language_changed(self):
        self.assertNotEqual(_spec(language="en").fingerprint(), _spec(language="es").fingerprint())
        self._run()
        self._run(_spec(language="es"))
        self.assertEqual(self.mock.invocation_count, 2)

    def test_04_voice_changed(self):
        self.assertNotEqual(_spec(voice_id="Charon").fingerprint(), _spec(voice_id="Puck").fingerprint())

    def test_05_emotion_changed(self):
        self.assertNotEqual(_spec(emotion="neutral").fingerprint(), _spec(emotion="excited").fingerprint())

    def test_06_speed_changed(self):
        self.assertNotEqual(_spec(speaking_speed=1.0).fingerprint(), _spec(speaking_speed=1.05).fingerprint())

    def test_07_provider_model_changed(self):
        self.assertNotEqual(
            _spec(provider="google", model="m1").fingerprint(),
            _spec(provider="edge", model="m2").fingerprint(),
        )

    def test_08_retry_same_fingerprint(self):
        self.assertEqual(_spec().fingerprint(), _spec().fingerprint())

    def test_09_concurrent_duplicate(self):
        spec = _spec()
        out = self.tmp / "conc.wav"
        lock = threading.Lock()
        calls = {"n": 0}
        results = []

        def worker():
            def gen():
                if not lock.acquire(blocking=False):
                    raise AssertionError("duplicate provider")
                calls["n"] += 1
                time.sleep(0.2)
                m = MockAudioProvider()
                return m.synthesize(out_path=out)

            r = execute_audio_request(self.tmp, spec, out, provider_fn=gen)
            results.append(r.action)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        self.assertEqual(calls["n"], 1)

    def test_10_valid_reuse(self):
        self._run()
        self.mock.invocation_count = 0
        r = self._run()
        self.assertEqual(r.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 0)

    def test_11_invalid_rejected(self):
        spec = _spec()
        fp = spec.fingerprint()
        bad = self.tmp / "bad.wav"
        bad.write_bytes(b"")
        store = IdempotencyStore(self.tmp / "idempotency")
        store.put(
            IdempotencyRecord(
                fingerprint=fp,
                job_id=spec.job_id,
                stage="audio",
                entity_id=spec.entity_id,
                request_state=IdempotencyState.SUCCEEDED,
                result_reference=str(bad),
            )
        )
        self._run(spec)
        self.assertEqual(self.mock.invocation_count, 1)

    def test_12_crash_before_provider(self):
        spec = _spec()
        store = IdempotencyStore(self.tmp / "idempotency")
        store.put(
            IdempotencyRecord(
                fingerprint=spec.fingerprint(),
                job_id=spec.job_id,
                stage="audio",
                entity_id=spec.entity_id,
                request_state=IdempotencyState.IN_PROGRESS,
            )
        )
        r = self._run(spec)
        self.assertIn(r.action, ("duplicate_prevented", "execute", "reuse"))

    def test_13_unknown_no_blind_duplicate(self):
        self.mock.behavior = MockAudioBehavior.UNKNOWN
        spec = _spec()
        r = self._run(spec)
        self.assertEqual(r.action, "unknown")
        n = self.mock.invocation_count
        r2 = self._run(spec)
        self.assertIn(r2.action, ("unknown", "duplicate_prevented", "failed"))
        self.assertEqual(self.mock.invocation_count, n)

    def test_14_crash_after_persistence(self):
        self._run()
        self.mock.invocation_count = 0
        r = self._run()
        self.assertEqual(r.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 0)

    def test_15_bounded_retry(self):
        self.mock.behavior = MockAudioBehavior.NETWORK
        spec = _spec()
        for _ in range(4):
            execute_audio_request(self.tmp, spec, self.tmp / "r.wav", use_mock=True, mock_provider=self.mock)
        rec = IdempotencyStore(self.tmp / "idempotency").get(spec.fingerprint())
        self.assertIsNotNone(rec)

    def test_16_permanent_failure(self):
        self.mock.behavior = MockAudioBehavior.REJECTION
        r = self._run()
        self.assertEqual(r.action, "failed")
        n = self.mock.invocation_count
        r2 = self._run()
        self.assertIn(r2.action, ("failed", "duplicate_prevented"))
        self.assertEqual(self.mock.invocation_count, n)

    def test_17_embedded_english_skip(self):
        agnes = self.tmp / "narration_en_from_agnes.m4a"
        agnes.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 900)
        skip, reason, ref = should_skip_english_tts_generation(self.tmp, 3)
        self.assertTrue(skip)
        self.assertIsNotNone(ref)
        r = execute_audio_request(
            self.tmp,
            _spec(),
            self.tmp / "out.wav",
            use_mock=True,
            mock_provider=self.mock,
            skip_generation=True,
            skip_reference=str(agnes),
        )
        self.assertEqual(r.action, "embedded_reuse")
        self.assertEqual(self.mock.invocation_count, 0)

    def test_18_two_languages(self):
        self._run(_spec(language="en"))
        self._run(_spec(language="bn", dialogue_id="d03-bn"))
        self.assertEqual(self.mock.invocation_count, 2)

    def test_19_split_parts_no_collision(self):
        fp1 = _spec(part_index=1, dialogue_id="d03", audio_plan_id="plan-p1").fingerprint()
        fp2 = _spec(part_index=2, dialogue_id="d03", audio_plan_id="plan-p2").fingerprint()
        self.assertNotEqual(fp1, fp2)

    def test_20_traceability(self):
        r = self._run()
        prov = load_audio_provenance(self.tmp, r.fingerprint)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["scene_id"], "3")
        self.assertTrue(prov["file_path"])
        self.assertEqual(prov["provenance"]["metadata"]["dialogue_id"], "d03")
        self.assertEqual(prov["language"], "en")

    def test_invalid_audio_rejected(self):
        self.mock.behavior = MockAudioBehavior.EMPTY
        r = self._run()
        self.assertNotEqual(r.action, "reuse")
        self.assertFalse(r.success)


if __name__ == "__main__":
    unittest.main(verbosity=2)
