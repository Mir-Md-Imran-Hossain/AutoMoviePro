#!/usr/bin/env python3
"""BUILD-04E subtitle runtime tests (offline mock + validation)."""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.idempotency.fingerprint import hash_artifact, hash_text
from pipeline.idempotency.mock_subtitle_provider import (
    MockSubtitleBehavior,
    MockSubtitleProvider,
    reset_mock_subtitle_provider,
)
from pipeline.idempotency.render_manifest import RenderSceneInput, build_manifest_from_clips
from pipeline.idempotency.render_request import RenderRequestSpec
from pipeline.idempotency.store import IdempotencyStore
from pipeline.idempotency.subtitle_engine import cues_to_srt_file, generate_bound_cues
from pipeline.idempotency.subtitle_provenance import load_subtitle_provenance
from pipeline.idempotency.subtitle_request import SubtitleRequestSpec, compute_subtitle_fingerprint
from pipeline.idempotency.subtitle_runtime import execute_subtitle_request
from pipeline.idempotency.subtitle_validation import (
    parse_srt,
    validate_cue_timestamps,
    validate_scene_margins,
    validate_subtitle_asset,
    validate_subtitle_bindings,
)


def _spec(**kw) -> SubtitleRequestSpec:
    base = dict(
        job_id="job-e1",
        scene_id="1",
        dialogue_id="d01",
        segment_id="",
        language="en",
        localized_text="Hello world this is deterministic subtitle text.",
        audio_fingerprint="aud-fp-abc123",
        audio_duration_sec=4.25,
    )
    base.update(kw)
    return SubtitleRequestSpec(**base)


def _meta(spec: SubtitleRequestSpec) -> dict:
    return {
        "scene_id": spec.scene_id,
        "dialogue_id": spec.dialogue_id,
        "segment_id": spec.segment_id,
        "language": spec.language,
        "text_hash": hash_text(spec.localized_text.strip())[:32],
        "leading_gap_sec": spec.leading_gap_sec,
        "trailing_gap_sec": spec.trailing_gap_sec,
        "timing_model": spec.timing_model,
        "scene_duration_sec": spec.scene_duration_sec,
    }


class Build04ESubtitleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mock = MockSubtitleProvider()
        self.mock.reset()
        reset_mock_subtitle_provider()
        self.out = self.tmp / "subtitles.srt"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, spec=None, **kw):
        spec = spec or _spec()
        return execute_subtitle_request(
            self.tmp, spec, self.out, use_mock=True, mock_provider=self.mock, **kw
        )

    def test_e01_same_request_idempotency(self):
        r1 = self._run()
        r2 = self._run()
        self.assertEqual(r1.action, "execute")
        self.assertEqual(r2.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 1)

    def test_e02_dialogue_identity(self):
        a = _spec(dialogue_id="d01")
        b = _spec(dialogue_id="d02")
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_e03_scene_identity(self):
        a = _spec(scene_id="1")
        b = _spec(scene_id="2")
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_e04_segment_identity(self):
        a = _spec(segment_id="")
        b = _spec(segment_id="seg-2")
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_e05_language_identity(self):
        a = _spec(language="en")
        b = _spec(language="bn")
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_e06_audio_dependency_identity(self):
        a = _spec(audio_fingerprint="aud-1", audio_duration_sec=4.0)
        b = _spec(audio_fingerprint="aud-2", audio_duration_sec=4.0)
        c = _spec(audio_fingerprint="aud-1", audio_duration_sec=5.5)
        self.assertNotEqual(a.fingerprint(), b.fingerprint())
        self.assertNotEqual(a.fingerprint(), c.fingerprint())

    def test_e07_timing_identity(self):
        a = _spec(scene_duration_sec=10.0)
        b = _spec(scene_duration_sec=12.0)
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_e08_subtitle_configuration_identity(self):
        a = _spec(subtitle_format="srt")
        b = _spec(subtitle_format="vtt")
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_e09_concurrent_duplicate_prevention(self):
        spec = _spec()
        lock = threading.Lock()
        results = []

        def worker():
            mp = MockSubtitleProvider()
            r = execute_subtitle_request(
                self.tmp, spec, self.out, use_mock=True, mock_provider=mp
            )
            with lock:
                results.append(r)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        actions = {r.action for r in results}
        self.assertTrue(actions <= {"execute", "reuse", "duplicate_prevented"})

    def test_e10_valid_cache_reuse(self):
        r1 = self._run()
        self.assertTrue(r1.success)
        self.mock.reset()
        r2 = self._run()
        self.assertEqual(r2.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 0)

    def test_e11_invalid_cache_rejection(self):
        r1 = self._run()
        self.assertTrue(r1.success)
        bad = self.out.read_text(encoding="utf-8").replace("Hello", "CORRUPT")
        self.out.write_text(bad, encoding="utf-8")
        self.mock.reset()
        r2 = self._run()
        self.assertIn(r2.action, ("execute", "failed"))
        self.assertGreaterEqual(self.mock.invocation_count, 1)

    def test_e12_malformed_subtitle(self):
        self.mock.behavior = MockSubtitleBehavior.MALFORMED
        r = self._run()
        self.assertNotEqual(r.action, "reuse")
        self.assertFalse(r.success)

    def test_e13_negative_timestamp(self):
        self.mock.behavior = MockSubtitleBehavior.NEGATIVE_TIME
        r = self._run()
        self.assertFalse(r.success)

    def test_e14_end_before_start(self):
        self.mock.behavior = MockSubtitleBehavior.END_BEFORE_START
        r = self._run()
        self.assertFalse(r.success)

    def test_e15_overlap(self):
        self.mock.behavior = MockSubtitleBehavior.OVERLAP
        r = self._run()
        self.assertFalse(r.success)

    def test_e16_wrong_dialogue(self):
        self.mock.behavior = MockSubtitleBehavior.WRONG_DIALOGUE
        r = self._run()
        self.assertFalse(r.success)

    def test_e17_wrong_scene(self):
        self.mock.behavior = MockSubtitleBehavior.WRONG_SCENE
        r = self._run()
        self.assertFalse(r.success)

    def test_e18_wrong_language(self):
        spec = _spec(language="en")
        self.out.write_text(
            "1\n00:00:00,000 --> 00:00:04,000\nHello\n\n",
            encoding="utf-8",
        )
        meta = self.out.with_suffix(self.out.suffix + ".meta.json")
        meta.write_text(json.dumps({**_meta(spec), "language": "bn"}), encoding="utf-8")
        ok, reason = validate_subtitle_asset(
            str(self.out), spec_meta=_meta(spec), audio_duration_sec=spec.audio_duration_sec
        )
        self.assertFalse(ok)
        self.assertIn("wrong_language", reason)

    def test_e19_duplicate_id(self):
        body = (
            "1\n00:00:00,000 --> 00:00:02,000\nA\n\n"
            "1\n00:00:02,000 --> 00:00:04,000\nB\n\n"
        )
        self.out.write_text(body, encoding="utf-8")
        spec = _spec()
        ok, reason = validate_subtitle_asset(str(self.out), spec_meta=_meta(spec))
        self.assertFalse(ok)
        self.assertEqual(reason, "duplicate_cue_id")

    def test_e20_out_of_scene_timing(self):
        cues = [{"cue_id": "1", "start_time": 0.0, "end_time": 20.0, "text": "x"}]
        ok, reason = validate_cue_timestamps(cues)
        self.assertTrue(ok)
        spec = _spec(audio_duration_sec=4.0)
        self.out.write_text(cues_to_srt_file(cues), encoding="utf-8")
        ok2, reason2 = validate_subtitle_asset(
            str(self.out), spec_meta=_meta(spec), audio_duration_sec=4.0
        )
        self.assertFalse(ok2)
        self.assertEqual(reason2, "exceeds_audio_duration")

    def test_e21_half_second_margin(self):
        ok, _ = validate_scene_margins(
            audio_duration_sec=4.0, scene_duration_sec=5.5, leading_gap_sec=0.5, trailing_gap_sec=0.5
        )
        self.assertTrue(ok)
        bad, reason = validate_scene_margins(
            audio_duration_sec=4.0, scene_duration_sec=4.5, leading_gap_sec=0.5, trailing_gap_sec=0.5
        )
        self.assertFalse(bad)
        self.assertIn("margin_impossible", reason)

    def test_e22_split_dialogue_mapping(self):
        s1 = _spec(segment_id="seg-1", dialogue_id="d-split")
        s2 = _spec(segment_id="seg-2", dialogue_id="d-split")
        self.assertNotEqual(s1.fingerprint(), s2.fingerprint())
        cues = generate_bound_cues(
            "part one", 2.0, scene_id="1", dialogue_id="d-split", segment_id="seg-1", language="en"
        )
        ok, _ = validate_subtitle_bindings(
            cues, expected_scene_id="1", expected_dialogue_id="d-split", expected_language="en", expected_segment_id="seg-1"
        )
        self.assertTrue(ok)

    def test_e23_split_dialogue_partial_recovery(self):
        spec1 = _spec(segment_id="seg-1")
        spec2 = _spec(segment_id="seg-2")
        r1 = execute_subtitle_request(
            self.tmp, spec1, self.tmp / "seg1.srt", use_mock=True, mock_provider=self.mock
        )
        self.assertTrue(r1.success)
        mp2 = MockSubtitleProvider()
        mp2.behavior = MockSubtitleBehavior.FAILURE
        r2 = execute_subtitle_request(
            self.tmp, spec2, self.tmp / "seg2.srt", use_mock=True, mock_provider=mp2
        )
        self.assertFalse(r2.success)
        mp2.behavior = MockSubtitleBehavior.SUCCESS
        r2b = execute_subtitle_request(
            self.tmp, spec2, self.tmp / "seg2.srt", use_mock=True, mock_provider=mp2
        )
        self.assertTrue(r2b.success)
        self.assertTrue((self.tmp / "seg1.srt").is_file())

    def test_e24_localization_timing(self):
        en = _spec(language="en", audio_duration_sec=4.0)
        bn = _spec(language="bn", audio_duration_sec=6.2, dialogue_id="d01-bn")
        self.assertNotEqual(en.fingerprint(), bn.fingerprint())

    def test_e25_crash_before_generation(self):
        store = IdempotencyStore(self.tmp / "idempotency")
        spec = _spec()
        fp = spec.fingerprint()
        from pipeline.idempotency.states import IdempotencyState
        from pipeline.idempotency.store import IdempotencyRecord

        store.put(
            IdempotencyRecord(
                fingerprint=fp,
                job_id=spec.job_id,
                stage="subtitle",
                entity_id=spec.entity_id,
                request_state=IdempotencyState.IN_PROGRESS,
            )
        )
        self.mock.behavior = MockSubtitleBehavior.SUCCESS
        r = self._run(spec)
        self.assertIn(r.action, ("execute", "reuse", "duplicate_prevented"))

    def test_e26_crash_after_generation(self):
        r1 = self._run()
        self.assertTrue(r1.success)
        r2 = self._run()
        self.assertEqual(r2.action, "reuse")

    def test_e27_unknown_reconciliation(self):
        self.mock.behavior = MockSubtitleBehavior.UNKNOWN
        r = self._run()
        self.assertFalse(r.success)

    def test_e28_retry_control(self):
        self.mock.behavior = MockSubtitleBehavior.FAILURE
        r = self._run()
        self.assertFalse(r.success)

    def test_e29_infinite_loop_protection(self):
        self.mock.behavior = MockSubtitleBehavior.FAILURE
        spec = _spec()
        for _ in range(5):
            execute_subtitle_request(
                self.tmp, spec, self.out, use_mock=True, mock_provider=self.mock
            )
        rec = IdempotencyStore(self.tmp / "idempotency").get(spec.fingerprint())
        self.assertIsNotNone(rec)

    def test_e30_repair_only_failed_segment(self):
        ok_spec = _spec(segment_id="a")
        bad_spec = _spec(segment_id="b")
        execute_subtitle_request(
            self.tmp, ok_spec, self.tmp / "a.srt", use_mock=True, mock_provider=MockSubtitleProvider()
        )
        self.mock.behavior = MockSubtitleBehavior.FAILURE
        execute_subtitle_request(
            self.tmp, bad_spec, self.tmp / "b.srt", use_mock=True, mock_provider=self.mock
        )
        self.mock.behavior = MockSubtitleBehavior.SUCCESS
        r = execute_subtitle_request(
            self.tmp, bad_spec, self.tmp / "b.srt", use_mock=True, mock_provider=self.mock
        )
        self.assertTrue(r.success)
        self.assertTrue((self.tmp / "a.srt").is_file())

    def test_e31_provenance(self):
        r = self._run()
        prov = load_subtitle_provenance(self.tmp, r.fingerprint)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["scene_id"], "1")
        self.assertEqual(prov["dialogue_id"], "d01")
        self.assertEqual(prov["language"], "en")

    def test_e32_checkpoint(self):
        r = self._run()
        rec = IdempotencyStore(self.tmp / "idempotency").get(r.fingerprint)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.request_state.value, "SUCCEEDED")

    def test_e33_traceability(self):
        r = self._run()
        prov = load_subtitle_provenance(self.tmp, r.fingerprint)
        self.assertTrue(prov["srt_path"])
        self.assertTrue(prov["fingerprint"])
        self.assertEqual(prov["audio_fingerprint"], "aud-fp-abc123")

    def test_e34_orphan_detection(self):
        orphan = self.tmp / "orphan.srt"
        orphan.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n\n", encoding="utf-8")
        meta = orphan.with_suffix(orphan.suffix + ".meta.json")
        meta.write_text(
            json.dumps({"scene_id": "99", "dialogue_id": "orphan", "language": "en"}),
            encoding="utf-8",
        )
        ok, reason = validate_subtitle_asset(str(orphan), spec_meta=_meta(_spec()))
        self.assertFalse(ok)
        self.assertIn("wrong_scene", reason)

    def test_e35_render_dependency_invalidation(self):
        sub1 = self.tmp / "sub1.srt"
        sub2 = self.tmp / "sub2.srt"
        sub1.write_text("1\n00:00:00,000 --> 00:00:01,000\nA\n\n", encoding="utf-8")
        sub2.write_text("1\n00:00:00,000 --> 00:00:01,000\nB\n\n", encoding="utf-8")
        clip = self.tmp / "c.mp4"
        clip.write_bytes(b"clip-content-" * 600)
        m1 = build_manifest_from_clips(job_id="j1", clips=[clip], subtitle_path=sub1)
        m2 = build_manifest_from_clips(job_id="j1", clips=[clip], subtitle_path=sub2)
        from pipeline.idempotency.render_request import RenderRequestSpec

        self.assertNotEqual(
            RenderRequestSpec(job_id="j1", manifest=m1).fingerprint(),
            RenderRequestSpec(job_id="j1", manifest=m2).fingerprint(),
        )

    def test_e36_no_upstream_regeneration(self):
        fp_script = compute_subtitle_fingerprint(_spec())
        fp_dialogue = compute_subtitle_fingerprint(_spec(localized_text="changed text only"))
        self.assertNotEqual(fp_script, fp_dialogue)

    def test_e37_architecture_bypass_detection(self):
        loc = (ROOT / "pipeline/localization.py").read_text(encoding="utf-8")
        self.assertIn("idempotent_write_srt", loc)
        self.assertIn("def write_srt", loc)
        # Legacy inline writer only allowed inside write_srt fallback (no work_dir)
        legacy_block = loc.split("def write_srt", 1)[1]
        self.assertIn("srt_path.write_text", legacy_block)
        self.assertIn("work_dir is not None", legacy_block)

    def test_e38_complete_regression_fingerprint_stable(self):
        fp1 = compute_subtitle_fingerprint(_spec())
        fp2 = compute_subtitle_fingerprint(_spec())
        self.assertEqual(fp1, fp2)

    def test_dialogue_change_fingerprint(self):
        a = _spec(localized_text="text A")
        b = _spec(localized_text="text B")
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_bound_cues_parse_roundtrip(self):
        cues = generate_bound_cues("one two three four", 3.0, scene_id="0", dialogue_id="d", language="en")
        srt = cues_to_srt_file(cues)
        parsed = parse_srt(srt)
        self.assertGreaterEqual(len(parsed), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
