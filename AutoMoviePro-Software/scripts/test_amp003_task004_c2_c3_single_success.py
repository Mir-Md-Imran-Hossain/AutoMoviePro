#!/usr/bin/env python3
"""AMP-003 T004-C2-2-C-3-2 — Single Agnes SUCCESS/REUSE return hardening tests."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.idempotency.agnes_bridge import (
    AgnesBeatOutcome,
    classify_agnes_beat_outcome,
    idempotent_generate_agnes_beat_result as _real_agnes_beat_result,
)
from pipeline.idempotency.checkpoint_store import CheckpointStore
from pipeline.idempotency.mock_visual_provider import MockBehavior, get_mock_provider, reset_mock_provider
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyStore
from pipeline.idempotency.visual_provenance import load_visual_provenance
from pipeline.scene_builder import AgnesOutcomeError, _resolve_footage, _resolve_single_agnes_beat_src


def _footage_kwargs(tmp: Path, **overrides) -> dict:
    base = dict(
        work=tmp,
        idx=3,
        product_name="TestProduct",
        visual_query="Cinematic reactor hall",
        visual_prompt="Cinematic reactor hall",
        element="feature",
        duration=5.0,
        size="1080x1920",
        pexels_api="",
        pollinations_key="",
        agnes_api="fake-key",
        agnes_api_keys=["fake-key"],
        google_api_keys=[],
        narration_hint="Single beat narration",
        require_agnes=False,
        allow_image_fallback=True,
        job_id="job-c3c32",
        dialogue_id="dlg-c3c32-uuid",
        canonical_scene_id="scene-c3c32-uuid",
        script_id="script-c3c32",
    )
    base.update(overrides)
    return base


def _single_helper_kwargs(tmp: Path, **overrides) -> dict:
    base = dict(
        work=tmp,
        job_id="job-c3c32",
        idx=3,
        attempt=1,
        product_name="TestProduct",
        element="feature",
        visual_prompt="Cinematic reactor hall",
        visual_query="Cinematic reactor hall",
        out_path=tmp / "agnes_03_feature.mp4",
        narration_hint="Single beat narration",
        size="1080x1920",
        duration_hint=5.0,
        override_prompt="Cinematic reactor hall",
        niche="tech",
        use_catalog_image=True,
        dialogue_id="dlg-c3c32-uuid",
        canonical_scene_id="scene-c3c32-uuid",
        script_id="script-c3c32",
        use_mock=True,
    )
    base.update(overrides)
    return base


def _fake_color_clip(dest: Path, duration: float, size: str) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"\x00" * 9000)
    return dest


def _mock_bridge(**kwargs):
    kwargs["use_mock"] = True
    return _real_agnes_beat_result(**kwargs)


class T004C2C32SingleSuccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        reset_mock_provider()
        self.mock = get_mock_provider()
        self.mock.reset()
        self.mock.behavior = MockBehavior.SUCCESS

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch_bridge(self):
        return mock.patch(
            "pipeline.idempotency.agnes_bridge.idempotent_generate_agnes_beat_result",
            side_effect=_mock_bridge,
        )

    # TEST-01
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback")
    def test_01_success_returns_valid_agnes_path(self, fb_mock):
        with self._patch_bridge():
            path = _resolve_footage(**_footage_kwargs(self.tmp))
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, "agnes_03_feature.mp4")
        fb_mock.assert_not_called()

    # TEST-02
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback")
    def test_02_success_image_fallback_not_called(self, fb_mock):
        with self._patch_bridge():
            _resolve_footage(**_footage_kwargs(self.tmp))
        fb_mock.assert_not_called()

    # TEST-03
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback")
    def test_03_reused_returns_valid_cached_path(self, fb_mock):
        with self._patch_bridge():
            kw = _footage_kwargs(self.tmp)
            first = _resolve_footage(**kw)
            self.mock.invocation_count = 0
            second = _resolve_footage(**kw)
        self.assertTrue(first.is_file())
        self.assertEqual(first, second)
        fb_mock.assert_not_called()

    # TEST-04
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback")
    def test_04_reused_image_fallback_not_called(self, fb_mock):
        with self._patch_bridge():
            kw = _footage_kwargs(self.tmp)
            _resolve_footage(**kw)
            fb_mock.reset_mock()
            _resolve_footage(**kw)
        fb_mock.assert_not_called()

    # TEST-05
    def test_05_reused_no_additional_provider_call(self):
        with self._patch_bridge():
            kw = _footage_kwargs(self.tmp)
            _resolve_footage(**kw)
            count = self.mock.invocation_count
            _resolve_footage(**kw)
        self.assertEqual(self.mock.invocation_count, count)

    # TEST-06
    @mock.patch("pipeline.scene_builder.make_color_clip", side_effect=_fake_color_clip)
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback")
    def test_06_success_invalid_asset_not_accepted(self, fb_mock, _color_mock):
        self.mock.behavior = MockBehavior.INVALID_ASSET
        with self._patch_bridge():
            path, result = _resolve_single_agnes_beat_src(**_single_helper_kwargs(self.tmp))
            footage_path = _resolve_footage(**_footage_kwargs(self.tmp, allow_image_fallback=False))
        self.assertIsNone(path)
        self.assertNotEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.SUCCESS)
        self.assertNotEqual(footage_path, self.tmp / "agnes_03_feature.mp4")

    # TEST-07
    def test_07_success_preserves_canonical_scene_id(self):
        with self._patch_bridge():
            _resolve_footage(**_footage_kwargs(self.tmp))
        _, result = _resolve_single_agnes_beat_src(**_single_helper_kwargs(self.tmp))
        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertIsNotNone(prov)
        self.assertEqual(
            prov["provenance"]["metadata"]["canonical_scene_id"],
            "scene-c3c32-uuid",
        )

    # TEST-08
    def test_08_success_preserves_dialogue_id(self):
        with self._patch_bridge():
            _resolve_footage(**_footage_kwargs(self.tmp))
        _, result = _resolve_single_agnes_beat_src(**_single_helper_kwargs(self.tmp))
        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["provenance"]["metadata"]["dialogue_id"], "dlg-c3c32-uuid")

    # TEST-09
    def test_09_success_preserves_job_id(self):
        with self._patch_bridge():
            _resolve_footage(**_footage_kwargs(self.tmp))
        _, result = _resolve_single_agnes_beat_src(**_single_helper_kwargs(self.tmp))
        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["provenance"]["job_id"], "job-c3c32")

    # TEST-10
    def test_10_part_index_remains_zero(self):
        calls: list[dict] = []

        def _capture(**kwargs):
            kwargs["use_mock"] = True
            calls.append(dict(kwargs))
            return _real_agnes_beat_result(**kwargs)

        with mock.patch(
            "pipeline.idempotency.agnes_bridge.idempotent_generate_agnes_beat_result",
            side_effect=_capture,
        ):
            _resolve_footage(**_footage_kwargs(self.tmp))
        self.assertTrue(calls)
        self.assertEqual(calls[-1].get("part_index"), 0)

    # TEST-11
    def test_11_provenance_available(self):
        with self._patch_bridge():
            _resolve_footage(**_footage_kwargs(self.tmp))
        _, result = _resolve_single_agnes_beat_src(**_single_helper_kwargs(self.tmp))
        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["provenance"]["input_hash"], result.fingerprint)

    # TEST-12
    def test_12_checkpoint_available(self):
        with self._patch_bridge():
            _resolve_footage(**_footage_kwargs(self.tmp))
        _, result = _resolve_single_agnes_beat_src(**_single_helper_kwargs(self.tmp))
        cps = CheckpointStore(self.tmp / "checkpoints").latest_for_job("job-c3c32")
        self.assertTrue(len(cps) >= 1)
        rec = IdempotencyStore(self.tmp / "idempotency").get(result.fingerprint)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.request_state, IdempotencyState.SUCCEEDED)

    # TEST-13
    @mock.patch("pipeline.scene_builder.make_color_clip", side_effect=_fake_color_clip)
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback")
    def test_13_failed_does_not_become_success(self, fb_mock, _color_mock):
        self.mock.behavior = MockBehavior.REJECTION
        with self._patch_bridge():
            path = _resolve_footage(**_footage_kwargs(self.tmp, allow_image_fallback=False))
        agnes_out = self.tmp / "agnes_03_feature.mp4"
        self.assertNotEqual(path, agnes_out)
        if agnes_out.exists() and path == agnes_out:
            self.fail("failed Agnes should not leave accepted success asset")

    # TEST-14
    @mock.patch("pipeline.scene_builder.make_color_clip", side_effect=_fake_color_clip)
    def test_14_unknown_does_not_become_success(self, _color_mock):
        self.mock.behavior = MockBehavior.UNKNOWN
        with self._patch_bridge():
            with self.assertRaises(AgnesOutcomeError) as ctx:
                _resolve_footage(**_footage_kwargs(self.tmp, allow_image_fallback=True))
        self.assertEqual(ctx.exception.outcome, "UNKNOWN")

    # TEST-15
    @mock.patch("pipeline.scene_builder.make_color_clip", side_effect=_fake_color_clip)
    def test_15_identity_blocked_no_provider(self, _color_mock):
        kw = _footage_kwargs(self.tmp)
        kw["canonical_scene_id"] = ""
        with self._patch_bridge():
            with self.assertRaises(AgnesOutcomeError) as ctx:
                _resolve_footage(**kw)
        self.assertEqual(ctx.exception.outcome, "IDENTITY_BLOCKED")
        self.assertEqual(self.mock.invocation_count, 0)

    # TEST-16
    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    def test_16_no_new_direct_provider_call(self, direct_mock):
        with self._patch_bridge():
            _resolve_footage(**_footage_kwargs(self.tmp))
        direct_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
