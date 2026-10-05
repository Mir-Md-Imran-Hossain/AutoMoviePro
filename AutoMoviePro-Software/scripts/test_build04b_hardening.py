#!/usr/bin/env python3
"""BUILD-04B-H TTS runtime coverage hardening tests (offline)."""
from __future__ import annotations

import ast
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.idempotency.audio_request import AudioRequestSpec, compute_audio_fingerprint
from pipeline.idempotency.audio_runtime import execute_audio_request
from pipeline.idempotency.mock_audio_provider import MockAudioBehavior, MockAudioProvider
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyRecord, IdempotencyStore
from pipeline.idempotency.tts_bridge import (
    GOOGLE_TTS_MODEL,
    build_audio_spec,
    idempotent_edge_tts,
    idempotent_reuse_or_synthesize_tts,
)


def _spec(**kw) -> AudioRequestSpec:
    base = dict(
        job_id="job-h",
        scene_id=5,
        dialogue_id="d05",
        audio_plan_id="plan-d05",
        dialogue_text="Hello world dialogue.",
        language="en",
        provider="google",
        model="gemini-2.5-flash-preview-tts",
        voice_id="Charon",
    )
    base.update(kw)
    return AudioRequestSpec(**base)


class LocalizationHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mock = MockAudioProvider()
        self.mock.reset()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_h01_localization_idempotency(self):
        text = "Localized dialogue for testing."
        dest = self.tmp / "loc" / "es" / "narration.m4a"
        r1 = idempotent_reuse_or_synthesize_tts(
            text, dest, work_dir=self.tmp, job_id="job-h", scene_id=5,
            language_hint="es", dialogue_id="loc-05-es", use_mock=True, mock_provider=self.mock,
        )
        self.assertTrue(r1.exists())
        n = self.mock.invocation_count
        idempotent_reuse_or_synthesize_tts(
            text, dest, work_dir=self.tmp, job_id="job-h", scene_id=5,
            language_hint="es", dialogue_id="loc-05-es", use_mock=True, mock_provider=self.mock,
        )
        self.assertEqual(self.mock.invocation_count, n)

    def test_h02_language_identity(self):
        fps = [
            compute_audio_fingerprint(_spec(language=lang, dialogue_id=f"d-{lang}"))
            for lang in ("en", "es", "bn", "hi")
        ]
        self.assertEqual(len(fps), len(set(fps)))

    def test_h03_localization_retry_fingerprint(self):
        fp = compute_audio_fingerprint(_spec(language="es", dialogue_id="loc-es"))
        self.assertEqual(fp, compute_audio_fingerprint(_spec(language="es", dialogue_id="loc-es")))

    def test_h04_localization_crash_recovery(self):
        self.mock.behavior = MockAudioBehavior.SUCCESS
        dest = self.tmp / "n1.m4a"
        idempotent_reuse_or_synthesize_tts(
            "crash test", dest, work_dir=self.tmp, job_id="j", scene_id=1,
            language_hint="en", use_mock=True, mock_provider=self.mock,
        )
        self.mock.invocation_count = 0
        r = idempotent_reuse_or_synthesize_tts(
            "crash test", dest, work_dir=self.tmp, job_id="j", scene_id=1,
            language_hint="en", use_mock=True, mock_provider=self.mock,
        )
        self.assertEqual(self.mock.invocation_count, 0)
        self.assertTrue(r.exists())


class SplitPathHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mock = MockAudioProvider()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_h05_split_segment_identity(self):
        fp1 = compute_audio_fingerprint(_spec(
            dialogue_id="split-10", segment_id="seg-01", part_index=1,
            dialogue_text="Part one text.",
        ))
        fp2 = compute_audio_fingerprint(_spec(
            dialogue_id="split-10", segment_id="seg-02", part_index=2,
            dialogue_text="Part two text.",
        ))
        self.assertNotEqual(fp1, fp2)

    def test_h06_split_duplicate_prevention(self):
        self.mock.reset()
        text = "Split segment narration."
        dest = self.tmp / "seg1.wav"
        for _ in range(2):
            idempotent_reuse_or_synthesize_tts(
                text, dest, work_dir=self.tmp, job_id="j", scene_id=10,
                dialogue_id="split-10", segment_id="seg-01", part_index=1,
                use_mock=True, mock_provider=self.mock,
            )
        self.assertEqual(self.mock.invocation_count, 1)

    def test_h07_split_collision_prevention(self):
        fp_a = compute_audio_fingerprint(_spec(
            scene_id=1, dialogue_id="split-01", segment_id="seg-01",
            dialogue_text="Hello",
        ))
        fp_b = compute_audio_fingerprint(_spec(
            scene_id=2, dialogue_id="split-01", segment_id="seg-01",
            dialogue_text="Hello",
        ))
        self.assertNotEqual(fp_a, fp_b)

    def test_h08_split_partial_recovery(self):
        self.mock.reset()
        dest1 = self.tmp / "s1.wav"
        dest2 = self.tmp / "s2.wav"
        idempotent_reuse_or_synthesize_tts(
            "seg one", dest1, work_dir=self.tmp, job_id="j", scene_id=10,
            dialogue_id="split-10", segment_id="seg-01", part_index=1,
            use_mock=True, mock_provider=self.mock,
        )
        n = self.mock.invocation_count
        idempotent_reuse_or_synthesize_tts(
            "seg one", dest1, work_dir=self.tmp, job_id="j", scene_id=10,
            dialogue_id="split-10", segment_id="seg-01", part_index=1,
            use_mock=True, mock_provider=self.mock,
        )
        self.assertEqual(self.mock.invocation_count, n)
        idempotent_reuse_or_synthesize_tts(
            "seg two", dest2, work_dir=self.tmp, job_id="j", scene_id=10,
            dialogue_id="split-10", segment_id="seg-02", part_index=2,
            use_mock=True, mock_provider=self.mock,
        )
        self.assertEqual(self.mock.invocation_count, n + 1)


class EdgeTtsHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mock = MockAudioProvider()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_h09_edge_identity(self):
        g = compute_audio_fingerprint(_spec(provider="google", model="gemini-2.5-flash-preview-tts"))
        e = compute_audio_fingerprint(_spec(provider="edge_tts", model="edge-neural"))
        self.assertNotEqual(g, e)

    def test_h10_edge_idempotency(self):
        self.mock.reset()
        dest = self.tmp / "edge.wav"
        idempotent_edge_tts(
            self.tmp, job_id="j", scene_id=1, dialogue_text="edge test",
            out_path=dest, use_mock=True, mock_provider=self.mock,
        )
        idempotent_edge_tts(
            self.tmp, job_id="j", scene_id=1, dialogue_text="edge test",
            out_path=dest, use_mock=True, mock_provider=self.mock,
        )
        self.assertEqual(self.mock.invocation_count, 1)

    def test_h11_edge_concurrency(self):
        self.mock.reset()
        dest = self.tmp / "ec.wav"
        lock = threading.Lock()
        calls = {"n": 0}

        def gen():
            if not lock.acquire(blocking=False):
                raise AssertionError("duplicate edge")
            calls["n"] += 1
            time.sleep(0.15)
            return MockAudioProvider().synthesize(out_path=dest)

        spec = build_audio_spec(
            job_id="j", scene_id=1, dialogue_id="e1", dialogue_text="x",
            language_hint="en", provider="edge_tts", model="edge-neural",
        )
        t1 = threading.Thread(
            target=lambda: execute_audio_request(self.tmp, spec, dest, provider_fn=gen)
        )
        t2 = threading.Thread(
            target=lambda: execute_audio_request(self.tmp, spec, dest, provider_fn=gen)
        )
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        self.assertEqual(calls["n"], 1)

    def test_h12_edge_retry_fingerprint(self):
        fp = compute_audio_fingerprint(_spec(provider="edge_tts", model="edge-neural"))
        self.assertEqual(fp, compute_audio_fingerprint(_spec(provider="edge_tts", model="edge-neural")))

    def test_h13_unknown_no_blind_edge(self):
        self.mock.behavior = MockAudioBehavior.UNKNOWN
        spec = _spec()
        dest = self.tmp / "u.wav"
        with self.assertRaises(RuntimeError):
            idempotent_reuse_or_synthesize_tts(
                "unknown test", dest, work_dir=self.tmp, job_id="j", scene_id=1,
                use_mock=True, mock_provider=self.mock, allow_edge_fallback=True,
            )
        self.mock.behavior = MockAudioBehavior.SUCCESS
        self.mock.reset()
        idempotent_edge_tts(
            self.tmp, job_id="j", scene_id=1, dialogue_text="after unknown",
            out_path=self.tmp / "e2.wav", use_mock=True, mock_provider=self.mock,
        )
        self.assertEqual(self.mock.invocation_count, 1)


class IntegrationHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_h14_primary_fallback_separation(self):
        g = _spec(provider="google").fingerprint()
        e = _spec(provider="edge_tts", model="edge-neural").fingerprint()
        self.assertNotEqual(g, e)

    def test_h15_invalid_fallback_rejected(self):
        mock = MockAudioProvider(behavior=MockAudioBehavior.EMPTY)
        dest = self.tmp / "bad.wav"
        with self.assertRaises(RuntimeError):
            idempotent_edge_tts(
                self.tmp, job_id="j", scene_id=1, dialogue_text="bad",
                out_path=dest, use_mock=True, mock_provider=mock,
            )

    def test_h16_provenance(self):
        mock = MockAudioProvider()
        dest = self.tmp / "prov.wav"
        idempotent_reuse_or_synthesize_tts(
            "provenance test", dest, work_dir=self.tmp, job_id="j", scene_id=2,
            dialogue_id="d02", language_hint="en", use_mock=True, mock_provider=mock,
        )
        from pipeline.idempotency.audio_provenance import load_audio_provenance

        spec = build_audio_spec(
            job_id="j",
            scene_id=2,
            dialogue_id="d02",
            dialogue_text="provenance test",
            language_hint="en",
            provider="google",
            model=GOOGLE_TTS_MODEL,
        )
        prov = load_audio_provenance(self.tmp, spec.fingerprint())
        self.assertIsNotNone(prov)

    def test_h18_traceability(self):
        mock = MockAudioProvider()
        dest = self.tmp / "trace.wav"
        idempotent_reuse_or_synthesize_tts(
            "trace", dest, work_dir=self.tmp, job_id="job-trace", scene_id=7,
            dialogue_id="d07", language_hint="en", use_mock=True, mock_provider=mock,
        )
        from pipeline.idempotency.audio_provenance import load_audio_provenance

        spec = build_audio_spec(
            job_id="job-trace",
            scene_id=7,
            dialogue_id="d07",
            dialogue_text="trace",
            language_hint="en",
            provider="google",
            model=GOOGLE_TTS_MODEL,
        )
        prov = load_audio_provenance(self.tmp, spec.fingerprint())
        self.assertEqual(prov["scene_id"], "7")
        self.assertEqual(prov["provenance"]["metadata"]["dialogue_id"], "d07")

    def test_h19_no_direct_bypass_localization(self):
        src = (ROOT / "pipeline" / "localization.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        direct_calls = 0
        idempotent_calls = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name) and fn.id == "synthesize_narration":
                    direct_calls += 1
                    for kw in node.keywords:
                        if kw.arg == "idempotency_work_dir":
                            idempotent_calls += 1
        self.assertEqual(direct_calls, idempotent_calls)

    def test_h20_api_accounting(self):
        mock = MockAudioProvider()
        dest = self.tmp / "cost.wav"
        idempotent_reuse_or_synthesize_tts(
            "cost", dest, work_dir=self.tmp, job_id="j", scene_id=1,
            use_mock=True, mock_provider=mock,
        )
        mock.invocation_count = 0
        idempotent_reuse_or_synthesize_tts(
            "cost", dest, work_dir=self.tmp, job_id="j", scene_id=1,
            use_mock=True, mock_provider=mock,
        )
        self.assertEqual(mock.invocation_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
