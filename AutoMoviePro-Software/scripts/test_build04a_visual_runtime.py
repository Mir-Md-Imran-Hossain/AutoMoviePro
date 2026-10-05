#!/usr/bin/env python3
"""BUILD-04A visual generation runtime tests (offline, mock provider)."""
from __future__ import annotations

import json
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

from pipeline.idempotency.mock_visual_provider import MockBehavior, MockVisualProvider, reset_mock_provider
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyRecord, IdempotencyStore
from pipeline.idempotency.visual_provenance import load_visual_provenance
from pipeline.idempotency.visual_request import GenerationMode, VisualRequestSpec, compute_visual_fingerprint
from pipeline.idempotency.visual_runtime import execute_visual_request, reconcile_visual_unknown
from pipeline.idempotency.visual_validation import validate_video_asset


def _spec(**overrides) -> VisualRequestSpec:
    base = dict(
        job_id="job-1",
        scene_id=1,
        visual_plan_id="feature",
        provider="mock",
        model="mock-v1",
        generation_mode=GenerationMode.TEXT_TO_VIDEO,
        prompt="Cinematic shot of a reactor control room",
        visual_prompt="control room",
        element="feature",
        product_name="Chernobyl",
        size="1080x1920",
        duration_sec=5.0,
        seed=42,
    )
    base.update(overrides)
    return VisualRequestSpec(**base)


class Build04AVisualTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mock = MockVisualProvider()
        self.mock.reset()
        reset_mock_provider()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, spec=None, **kw):
        spec = spec or _spec()
        out = self.tmp / "out.mp4"
        return execute_visual_request(
            self.tmp,
            spec,
            out,
            use_mock=True,
            mock_provider=self.mock,
            **kw,
        )

    # TEST-01: same request twice → provider calls = 1
    def test_01_same_request_twice(self):
        r1 = self._run()
        r2 = self._run()
        self.assertTrue(r1.success)
        self.assertEqual(r1.action, "execute")
        self.assertEqual(r2.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 1)

    # TEST-02: prompt changed → fingerprint changed
    def test_02_prompt_changed(self):
        fp1 = _spec().fingerprint()
        fp2 = _spec(prompt="Different prompt entirely").fingerprint()
        self.assertNotEqual(fp1, fp2)
        self._run()
        self._run(_spec(prompt="Different prompt entirely"))
        self.assertEqual(self.mock.invocation_count, 2)

    # TEST-03: seed changed
    def test_03_seed_changed(self):
        self.assertNotEqual(_spec(seed=1).fingerprint(), _spec(seed=2).fingerprint())

    # TEST-04: resolution changed
    def test_04_resolution_changed(self):
        self.assertNotEqual(_spec(size="1080x1920").fingerprint(), _spec(size="1280x720").fingerprint())

    # TEST-05: retry same request → fingerprint unchanged
    def test_05_retry_same_fingerprint(self):
        fp = _spec().fingerprint()
        self.assertEqual(fp, _spec().fingerprint())

    # TEST-06: concurrent duplicate
    def test_06_concurrent_duplicate(self):
        spec = _spec()
        out = self.tmp / "conc.mp4"
        provider_lock = threading.Lock()
        provider_calls = {"n": 0}
        results = []

        def guarded_gen():
            if not provider_lock.acquire(blocking=False):
                raise AssertionError("duplicate provider invocation")
            provider_calls["n"] += 1
            time.sleep(0.2)
            mock = MockVisualProvider()
            return mock.generate(out_path=out)

        def worker():
            r = execute_visual_request(self.tmp, spec, out, provider_fn=guarded_gen)
            results.append(r.action)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        self.assertEqual(provider_calls["n"], 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(len([r for r in results if r == "execute"]), 1)
        self.assertTrue(all(r in ("execute", "reuse", "duplicate_prevented") for r in results))

    # TEST-07: valid result exists → provider not called
    def test_07_valid_result_reuse(self):
        self._run()
        self.mock.invocation_count = 0
        r = self._run()
        self.assertEqual(r.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 0)

    # TEST-08: invalid existing result → rejected
    def test_08_invalid_existing_rejected(self):
        spec = _spec()
        fp = spec.fingerprint()
        bad = self.tmp / "bad.mp4"
        bad.write_bytes(b"")
        store = IdempotencyStore(self.tmp / "idempotency")
        store.put(
            IdempotencyRecord(
                fingerprint=fp,
                job_id=spec.job_id,
                stage="visual",
                entity_id=spec.entity_id,
                request_state=IdempotencyState.SUCCEEDED,
                result_reference=str(bad),
            )
        )
        r = self._run(spec)
        self.assertIn(r.action, ("execute", "failed"))
        self.assertEqual(self.mock.invocation_count, 1)

    # TEST-09: crash before provider — safe recovery
    def test_09_crash_before_provider(self):
        spec = _spec()
        fp = spec.fingerprint()
        store = IdempotencyStore(self.tmp / "idempotency")
        store.put(
            IdempotencyRecord(
                fingerprint=fp,
                job_id=spec.job_id,
                stage="visual",
                entity_id=spec.entity_id,
                request_state=IdempotencyState.IN_PROGRESS,
            )
        )
        r = self._run(spec)
        self.assertIn(r.action, ("duplicate_prevented", "execute", "reuse"))

    # TEST-10: crash after provider → UNKNOWN
    def test_10_unknown_no_blind_duplicate(self):
        spec = _spec()
        self.mock.behavior = MockBehavior.UNKNOWN
        r = self._run(spec)
        self.assertEqual(r.action, "unknown")
        count_after_first = self.mock.invocation_count
        self.assertEqual(count_after_first, 1)
        r2 = self._run(spec)
        self.assertIn(r2.action, ("unknown", "duplicate_prevented", "failed"))
        self.assertEqual(self.mock.invocation_count, count_after_first)

    # TEST-11: crash after persistence → reuse
    def test_11_crash_after_persistence(self):
        r1 = self._run()
        self.assertTrue(r1.path and r1.path.is_file())
        self.mock.invocation_count = 0
        r2 = self._run()
        self.assertEqual(r2.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 0)

    # TEST-12: bounded retry
    def test_12_bounded_retry(self):
        self.mock.behavior = MockBehavior.NETWORK
        spec = _spec()
        for _ in range(5):
            execute_visual_request(self.tmp, spec, self.tmp / "r.mp4", use_mock=True, mock_provider=self.mock)
        store = IdempotencyStore(self.tmp / "idempotency")
        rec = store.get(spec.fingerprint())
        self.assertIsNotNone(rec)
        self.assertIn(rec.request_state, (IdempotencyState.FAILED_RETRYABLE, IdempotencyState.FAILED_FINAL, IdempotencyState.UNKNOWN))

    # TEST-13: non-retryable
    def test_13_non_retryable(self):
        self.mock.behavior = MockBehavior.REJECTION
        r = self._run()
        self.assertEqual(r.action, "failed")
        count = self.mock.invocation_count
        r2 = self._run()
        self.assertIn(r2.action, ("failed", "duplicate_prevented"))
        self.assertEqual(self.mock.invocation_count, count)

    # TEST-14: fallback distinct identity
    def test_14_fallback_distinct_identity(self):
        primary = _spec(generation_mode=GenerationMode.TEXT_TO_VIDEO, provider="agnes")
        fallback = _spec(
            visual_plan_id="feature-fallback",
            generation_mode=GenerationMode.IMAGE_GENERATION,
            provider="fallback",
            model="ken_burns",
        )
        self.assertNotEqual(primary.fingerprint(), fallback.fingerprint())
        self._run(primary)
        self._run(fallback)
        self.assertEqual(self.mock.invocation_count, 2)

    # TEST-15: scene traceability
    def test_15_scene_traceability(self):
        r = self._run()
        prov = load_visual_provenance(self.tmp, r.fingerprint)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["scene_id"], "1")
        self.assertTrue(prov["file_path"])
        self.assertTrue(prov["file_hash"])
        self.assertEqual(prov["provenance"]["input_hash"], r.fingerprint)
        self.assertIn("generation_mode", prov["provenance"]["metadata"])

    def test_invalid_asset_rejected(self):
        self.mock.behavior = MockBehavior.INVALID_ASSET
        r = self._run()
        self.assertNotEqual(r.action, "reuse")
        self.assertFalse(r.success or r.action == "execute")

    def test_provider_mode_identity(self):
        t2v = _spec(generation_mode=GenerationMode.TEXT_TO_VIDEO).fingerprint()
        i2v = _spec(generation_mode=GenerationMode.IMAGE_TO_VIDEO, image_url_hash="abc").fingerprint()
        self.assertNotEqual(t2v, i2v)

    def test_provenance_no_secrets(self):
        r = self._run()
        text = json.dumps(load_visual_provenance(self.tmp, r.fingerprint))
        for secret in ("api_key", "Bearer", "password", "token"):
            self.assertNotIn(secret, text.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
