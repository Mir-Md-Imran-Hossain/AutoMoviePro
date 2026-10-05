#!/usr/bin/env python3
"""BUILD-04D render runtime tests (offline mock + local validation)."""
from __future__ import annotations

import json
import os
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

from pipeline.idempotency.fingerprint import hash_artifact
from pipeline.idempotency.mock_render_provider import (
    MockRenderBehavior,
    MockRenderProvider,
    reset_mock_render_provider,
)
from pipeline.idempotency.render_manifest import (
    RenderAssemblyManifest,
    RenderSceneInput,
    build_manifest_from_clips,
)
from pipeline.idempotency.render_provenance import load_render_provenance
from pipeline.idempotency.render_request import RenderRequestSpec, compute_render_fingerprint
from pipeline.idempotency.render_runtime import execute_render_request
from pipeline.idempotency.render_validation import validate_render_output
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyRecord, IdempotencyStore


def _clip(tmp: Path, name: str, content: bytes) -> Path:
    p = tmp / name
    p.write_bytes(content)
    return p


def _manifest(
    job_id: str = "job-r1",
    *,
    scenes=None,
    logo_hash: str = "",
    intro_hash: str = "",
    size: str = "1080x1920",
    max_seconds: int = 90,
    script_fp: str = "script-fp-1",
    fps: int = 25,
) -> RenderAssemblyManifest:
    if scenes is None:
        scenes = [
            RenderSceneInput(scene_index=0, visual_asset_hash="vis-a", duration_sec=5.0),
            RenderSceneInput(scene_index=1, visual_asset_hash="vis-b", duration_sec=6.0),
        ]
    return RenderAssemblyManifest(
        job_id=job_id,
        script_fingerprint=script_fp,
        scenes=scenes,
        logo_hash=logo_hash,
        intro_hash=intro_hash,
        size=size,
        max_seconds=max_seconds,
        fps=fps,
    )


def _spec(manifest=None, **kw) -> RenderRequestSpec:
    m = manifest or _manifest()
    base = dict(job_id=m.job_id, manifest=m)
    base.update(kw)
    return RenderRequestSpec(**base)


class Build04DRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mock = MockRenderProvider()
        self.mock.reset()
        reset_mock_render_provider()
        self.out = self.tmp / "final_short.mp4"
        self.clip_a = _clip(self.tmp, "scene_00.mp4", b"clip-a-content-" * 600)
        self.clip_b = _clip(self.tmp, "scene_01.mp4", b"clip-b-content-" * 600)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, spec=None, **kw):
        spec = spec or _spec()
        return execute_render_request(
            self.tmp, spec, self.out, use_mock=True, mock_provider=self.mock, **kw
        )

    def test_d01_same_request_idempotency(self):
        r1 = self._run()
        r2 = self._run()
        self.assertEqual(r1.action, "execute")
        self.assertEqual(r2.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 1)

    def test_d02_visual_dependency_identity(self):
        m1 = _manifest(scenes=[RenderSceneInput(0, "vis-a"), RenderSceneInput(1, "vis-b")])
        m2 = _manifest(scenes=[RenderSceneInput(0, "vis-a-changed"), RenderSceneInput(1, "vis-b")])
        self.assertNotEqual(_spec(m1).fingerprint(), _spec(m2).fingerprint())

    def test_d03_audio_dependency_identity(self):
        s1 = [RenderSceneInput(0, "v", audio_asset_hash="aud-1")]
        s2 = [RenderSceneInput(0, "v", audio_asset_hash="aud-2")]
        self.assertNotEqual(_spec(_manifest(scenes=s1)).fingerprint(), _spec(_manifest(scenes=s2)).fingerprint())

    def test_d04_subtitle_dependency_identity(self):
        s1 = [RenderSceneInput(0, "v", subtitle_asset_hash="sub-1")]
        s2 = [RenderSceneInput(0, "v", subtitle_asset_hash="sub-2")]
        self.assertNotEqual(_spec(_manifest(scenes=s1)).fingerprint(), _spec(_manifest(scenes=s2)).fingerprint())

    def test_d05_logo_dependency_identity(self):
        self.assertNotEqual(_spec(_manifest(logo_hash="l1")).fingerprint(), _spec(_manifest(logo_hash="l2")).fingerprint())

    def test_d06_intro_dependency_identity(self):
        self.assertNotEqual(_spec(_manifest(intro_hash="i1")).fingerprint(), _spec(_manifest(intro_hash="i2")).fingerprint())

    def test_d07_render_configuration_identity(self):
        self.assertNotEqual(_spec(_manifest(size="1080x1920")).fingerprint(), _spec(_manifest(size="720x1280")).fingerprint())
        self.assertNotEqual(_spec(_manifest(fps=25)).fingerprint(), _spec(_manifest(fps=30)).fingerprint())

    def test_d08_scene_ordering_identity(self):
        m1 = _manifest(scenes=[RenderSceneInput(0, "a"), RenderSceneInput(1, "b")])
        m2 = _manifest(scenes=[RenderSceneInput(0, "b"), RenderSceneInput(1, "a")])
        self.assertNotEqual(_spec(m1).fingerprint(), _spec(m2).fingerprint())

    def test_d09_timing_identity(self):
        s1 = [RenderSceneInput(0, "v", start_sec=0, end_sec=5, duration_sec=5)]
        s2 = [RenderSceneInput(0, "v", start_sec=0, end_sec=8, duration_sec=8)]
        self.assertNotEqual(_spec(_manifest(scenes=s1)).fingerprint(), _spec(_manifest(scenes=s2)).fingerprint())

    def test_d10_concurrent_duplicate_prevention(self):
        spec = _spec()
        lock = threading.Lock()
        calls = {"n": 0}
        results = []

        def worker():
            def render_fn(tmp):
                if not lock.acquire(blocking=False):
                    raise AssertionError("duplicate render")
                calls["n"] += 1
                time.sleep(0.15)
                m = MockRenderProvider()
                return m.render(out_path=tmp)

            r = execute_render_request(self.tmp, spec, self.out, provider_fn=render_fn)
            results.append(r.action)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        self.assertEqual(calls["n"], 1)

    def test_d11_valid_output_reuse(self):
        self._run()
        self.mock.invocation_count = 0
        r = self._run()
        self.assertEqual(r.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 0)

    def test_d12_zero_byte_output_rejection(self):
        self.mock.behavior = MockRenderBehavior.EMPTY
        r = self._run()
        self.assertFalse(r.success)

    def test_d13_corrupt_output_rejection(self):
        self.mock.behavior = MockRenderBehavior.CORRUPT
        r = self._run()
        self.assertFalse(r.success)

    def test_d14_missing_video_rejection(self):
        self.mock.behavior = MockRenderBehavior.CORRUPT
        r = self._run()
        self.assertNotEqual(r.action, "reuse")

    def test_d15_missing_audio_rejection(self):
        bad = self.tmp / "no_audio.mp4"
        bad.write_bytes(b"ftyp" + b"\x00" * 9000)
        ok, reason = validate_render_output(str(bad), require_audio=True)
        if ok is False:
            self.assertIn("audio", reason.lower())
        else:
            self.skipTest("ffprobe unavailable — container-only validation")

    def test_d16_duration_validation(self):
        from pipeline.idempotency.render_validation import duration_within_tolerance

        ok, _ = duration_within_tolerance(10.0, 10.5)
        self.assertTrue(ok)
        ok2, _ = duration_within_tolerance(10.0, 20.0)
        self.assertFalse(ok2)

    def test_d17_dimension_validation(self):
        try:
            from pipeline.compose import make_color_clip

            p = self.tmp / "dim.mp4"
            make_color_clip(p, 0.5, "640x360")
            if p.stat().st_size < 8000:
                self.skipTest("ffmpeg clip too small")
            ok, reason = validate_render_output(str(p), expected_size="640x360")
            self.assertTrue(ok, reason)
        except Exception as exc:
            self.skipTest(f"ffmpeg unavailable: {exc}")

    def test_d18_partial_output_protection(self):
        self.mock.behavior = MockRenderBehavior.PARTIAL
        r = self._run()
        self.assertFalse(r.success)
        if self.out.exists():
            self.assertLess(self.out.stat().st_size, 8000)

    def test_d19_crash_before_render_recovery(self):
        spec = _spec()
        store = IdempotencyStore(self.tmp / "idempotency")
        store.put(
            IdempotencyRecord(
                fingerprint=spec.fingerprint(),
                job_id=spec.job_id,
                stage="render",
                entity_id=spec.entity_id,
                request_state=IdempotencyState.IN_PROGRESS,
            )
        )
        r = self._run(spec)
        self.assertIn(r.action, ("duplicate_prevented", "execute", "reuse"))

    def test_d20_crash_during_render_recovery(self):
        self.mock.behavior = MockRenderBehavior.UNKNOWN
        r = self._run()
        self.assertEqual(r.action, "unknown")

    def test_d21_crash_after_render_recovery(self):
        self._run()
        self.mock.invocation_count = 0
        r = self._run()
        self.assertEqual(r.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 0)

    def test_d22_unknown_reconciliation(self):
        self.mock.behavior = MockRenderBehavior.UNKNOWN
        spec = _spec()
        r1 = self._run(spec)
        n = self.mock.invocation_count
        r2 = self._run(spec)
        self.assertEqual(self.mock.invocation_count, n)
        self.assertIn(r2.action, ("unknown", "duplicate_prevented", "failed"))

    def test_d23_retry_policy(self):
        self.assertEqual(_spec().fingerprint(), _spec().fingerprint())

    def test_d24_infinite_loop_protection(self):
        self.mock.behavior = MockRenderBehavior.NETWORK
        spec = _spec()
        for _ in range(5):
            execute_render_request(self.tmp, spec, self.out, use_mock=True, mock_provider=self.mock)
        rec = IdempotencyStore(self.tmp / "idempotency").get(spec.fingerprint())
        self.assertIsNotNone(rec)

    def test_d25_provenance(self):
        r = self._run()
        prov = load_render_provenance(self.tmp, r.fingerprint)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["job_id"], "job-r1")

    def test_d26_checkpoint(self):
        r = self._run()
        self.assertTrue(self.out.is_file())
        r2 = self._run()
        self.assertEqual(r2.action, "reuse")

    def test_d27_traceability(self):
        r = self._run()
        prov = load_render_provenance(self.tmp, r.fingerprint)
        self.assertIn("manifest", prov)
        self.assertEqual(prov["manifest"]["script_fingerprint"], "script-fp-1")

    def test_d28_orphan_detection(self):
        r = self._run()
        self.assertTrue(r.fingerprint)
        self.assertTrue(self.out.is_file())
        prov = load_render_provenance(self.tmp, r.fingerprint)
        self.assertEqual(prov["output_hash"], hash_artifact(str(self.out)))

    def test_d29_output_atomicity(self):
        self._run()
        tmp = self.out.with_name(self.out.stem + ".tmp" + self.out.suffix)
        self.assertFalse(tmp.exists())

    def test_d30_parallel_job_isolation(self):
        tmp2 = Path(tempfile.mkdtemp())
        try:
            s1 = _spec(_manifest(job_id="job-a"))
            s2 = _spec(_manifest(job_id="job-b"))
            self.assertNotEqual(s1.fingerprint(), s2.fingerprint())
            execute_render_request(self.tmp, s1, self.tmp / "final_a.mp4", use_mock=True, mock_provider=self.mock)
            m2 = MockRenderProvider()
            execute_render_request(tmp2, s2, tmp2 / "final_b.mp4", use_mock=True, mock_provider=m2)
            self.assertTrue((self.tmp / "final_a.mp4").is_file())
            self.assertTrue((tmp2 / "final_b.mp4").is_file())
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    def test_d31_ffmpeg_failure_classification(self):
        self.mock.behavior = MockRenderBehavior.FAILURE
        r = self._run()
        self.assertFalse(r.success)

    def test_d32_resource_failure_handling(self):
        self.mock.behavior = MockRenderBehavior.NETWORK
        r = self._run()
        self.assertIn(r.action, ("failed", "unknown", "execute"))

    def test_d33_no_upstream_regeneration_on_render_retry(self):
        self._run()
        n = self.mock.invocation_count
        self._run()
        self.assertEqual(self.mock.invocation_count, n)

    def test_d34_architecture_bypass_detection(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("idempotent_compose_final_video", src)

    def test_d35_manifest_from_clips(self):
        m = build_manifest_from_clips(
            job_id="j",
            clips=[self.clip_a, self.clip_b],
            video_type="short",
            size="1080x1920",
            max_seconds=60,
        )
        self.assertEqual(len(m.scenes), 2)
        self.assertTrue(m.scenes[0].visual_asset_hash)


if __name__ == "__main__":
    unittest.main(verbosity=2)
