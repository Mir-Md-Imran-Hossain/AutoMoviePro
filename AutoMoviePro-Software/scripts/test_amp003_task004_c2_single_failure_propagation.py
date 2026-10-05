#!/usr/bin/env python3
"""AMP-003 T004-C2-C3-FP — Single Agnes failure propagation hardening tests."""
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
    idempotent_generate_agnes_beat,
    idempotent_generate_agnes_beat_result as _real_agnes_beat_result,
)
from pipeline.idempotency.mock_visual_provider import MockBehavior, get_mock_provider, reset_mock_provider
from pipeline.scene_builder import AgnesOutcomeError, _resolve_footage, _resolve_single_agnes_beat_src


def _footage_kwargs(tmp: Path, **overrides) -> dict:
    base = dict(
        work=tmp,
        idx=7,
        product_name="TestProduct",
        visual_query="Cinematic hall",
        visual_prompt="Cinematic hall",
        element="feature",
        duration=5.0,
        size="1080x1920",
        pexels_api="",
        pollinations_key="",
        agnes_api="fake-key",
        agnes_api_keys=["fake-key"],
        google_api_keys=[],
        narration_hint="Narration",
        require_agnes=False,
        allow_image_fallback=True,
        job_id="job-fp",
        dialogue_id="dlg-fp-uuid",
        canonical_scene_id="scene-fp-uuid",
        script_id="script-fp",
    )
    base.update(overrides)
    return base


def _helper_kwargs(tmp: Path, **overrides) -> dict:
    base = dict(
        work=tmp,
        job_id="job-fp",
        idx=7,
        attempt=1,
        product_name="TestProduct",
        element="feature",
        visual_prompt="Cinematic hall",
        visual_query="Cinematic hall",
        out_path=tmp / "agnes_07_feature.mp4",
        narration_hint="Narration",
        size="1080x1920",
        duration_hint=5.0,
        override_prompt="Cinematic hall",
        niche="tech",
        use_catalog_image=True,
        dialogue_id="dlg-fp-uuid",
        canonical_scene_id="scene-fp-uuid",
        script_id="script-fp",
        use_mock=True,
    )
    base.update(overrides)
    return base


def _mock_bridge(**kwargs):
    kwargs["use_mock"] = True
    return _real_agnes_beat_result(**kwargs)


def _fake_color_clip(dest: Path, duration: float, size: str) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"\x00" * 9000)
    return dest


def _fake_image_fallback(**kwargs):
    out = Path(kwargs["out_path"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 9000)
    return out


class T004C2SingleFailurePropagationTests(unittest.TestCase):
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

    # 1 SUCCESS
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback")
    def test_01_success(self, fb_mock):
        with self._patch_bridge():
            path = _resolve_footage(**_footage_kwargs(self.tmp))
        self.assertEqual(path.name, "agnes_07_feature.mp4")
        fb_mock.assert_not_called()

    # 2 REUSED
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback")
    def test_02_reused(self, fb_mock):
        with self._patch_bridge():
            kw = _footage_kwargs(self.tmp)
            _resolve_footage(**kw)
            self.mock.invocation_count = 0
            path = _resolve_footage(**kw)
        self.assertTrue(path.is_file())
        self.assertEqual(self.mock.invocation_count, 0)
        fb_mock.assert_not_called()

    # 3 FAILED_RETRYABLE
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback", side_effect=_fake_image_fallback)
    def test_03_failed_retryable_explicit_fallback(self, fb_mock):
        self.mock.behavior = MockBehavior.INVALID_ASSET
        with self._patch_bridge():
            path = _resolve_footage(**_footage_kwargs(self.tmp))
        self.assertNotEqual(path.name, "agnes_07_feature.mp4")
        fb_mock.assert_called_once()

    # 4 FAILED_FINAL
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback", side_effect=_fake_image_fallback)
    def test_04_failed_final_explicit_fallback(self, fb_mock):
        self.mock.behavior = MockBehavior.REJECTION
        with self._patch_bridge():
            path = _resolve_footage(**_footage_kwargs(self.tmp))
        self.assertNotEqual(path.name, "agnes_07_feature.mp4")
        fb_mock.assert_called_once()

    # 5 UNKNOWN
    def test_05_unknown_blocked(self):
        self.mock.behavior = MockBehavior.UNKNOWN
        with self._patch_bridge():
            with self.assertRaises(AgnesOutcomeError) as ctx:
                _resolve_footage(**_footage_kwargs(self.tmp))
        self.assertEqual(ctx.exception.outcome, "UNKNOWN")

    # 6 IDENTITY_BLOCKED
    def test_06_identity_blocked_fail_closed(self):
        kw = _footage_kwargs(self.tmp)
        kw["dialogue_id"] = "dlg-only"
        kw["canonical_scene_id"] = ""
        with self._patch_bridge():
            with self.assertRaises(AgnesOutcomeError) as ctx:
                _resolve_footage(**kw)
        self.assertEqual(ctx.exception.outcome, "IDENTITY_BLOCKED")
        self.assertEqual(self.mock.invocation_count, 0)

    # 7 unexpected Exception
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback", side_effect=_fake_image_fallback)
    def test_07_exception_no_direct_bypass(self, fb_mock):
        with self._patch_bridge():
            with mock.patch(
                "pipeline.scene_builder._resolve_single_agnes_beat_src",
                side_effect=RuntimeError("simulated bridge crash"),
            ):
                with mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip") as direct:
                    path = _resolve_footage(**_footage_kwargs(self.tmp))
        direct.assert_not_called()
        fb_mock.assert_called_once()
        self.assertTrue(path.is_file())

    # 8 invalid SUCCESS asset
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback", side_effect=_fake_image_fallback)
    def test_08_invalid_success_asset(self, fb_mock):
        self.mock.behavior = MockBehavior.INVALID_ASSET
        with self._patch_bridge():
            path, result = _resolve_single_agnes_beat_src(**_helper_kwargs(self.tmp))
        self.assertIsNone(path)
        self.assertNotEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.SUCCESS)

    # 9 no false SUCCESS
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback", side_effect=_fake_image_fallback)
    def test_09_no_false_success_on_failed(self, fb_mock):
        self.mock.behavior = MockBehavior.REJECTION
        with self._patch_bridge():
            path = _resolve_footage(**_footage_kwargs(self.tmp))
        self.assertNotEqual(path.name, "agnes_07_feature.mp4")

    # 10 no blind retry
    def test_10_unknown_no_blind_retry(self):
        self.mock.behavior = MockBehavior.UNKNOWN
        with self._patch_bridge():
            kw = _footage_kwargs(self.tmp)
            with self.assertRaises(AgnesOutcomeError):
                _resolve_footage(**kw)
            count = self.mock.invocation_count
            with self.assertRaises(AgnesOutcomeError):
                _resolve_footage(**kw)
        self.assertEqual(self.mock.invocation_count, count)

    # 11 provider invocation count on reuse
    def test_11_provider_count_reuse(self):
        with self._patch_bridge():
            kw = _footage_kwargs(self.tmp)
            _resolve_footage(**kw)
            self.mock.invocation_count = 0
            _resolve_footage(**kw)
        self.assertEqual(self.mock.invocation_count, 0)

    # 12 canonical_scene_id
    def test_12_canonical_scene_id(self):
        with self._patch_bridge():
            _resolve_footage(**_footage_kwargs(self.tmp))
        _, result = _resolve_single_agnes_beat_src(**_helper_kwargs(self.tmp))
        from pipeline.idempotency.visual_provenance import load_visual_provenance

        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertEqual(prov["provenance"]["metadata"]["canonical_scene_id"], "scene-fp-uuid")

    # 13 dialogue_id
    def test_13_dialogue_id(self):
        with self._patch_bridge():
            _resolve_footage(**_footage_kwargs(self.tmp))
        _, result = _resolve_single_agnes_beat_src(**_helper_kwargs(self.tmp))
        from pipeline.idempotency.visual_provenance import load_visual_provenance

        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertEqual(prov["provenance"]["metadata"]["dialogue_id"], "dlg-fp-uuid")

    # 14 job_id
    def test_14_job_id(self):
        with self._patch_bridge():
            _resolve_footage(**_footage_kwargs(self.tmp))
        _, result = _resolve_single_agnes_beat_src(**_helper_kwargs(self.tmp))
        from pipeline.idempotency.visual_provenance import load_visual_provenance

        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertEqual(prov["provenance"]["job_id"], "job-fp")

    # 15 legacy API
    def test_15_legacy_adapter(self):
        with self._patch_bridge():
            path = idempotent_generate_agnes_beat(
                work_dir=self.tmp,
                job_id="job-fp",
                scene_id=7,
                part_index=0,
                attempt=1,
                product_name="TestProduct",
                element="feature",
                visual_prompt="Cinematic hall",
                out_path=self.tmp / "legacy.mp4",
                dialogue_id="dlg-fp-uuid",
                canonical_scene_id="scene-fp-uuid",
                script_id="script-fp",
                use_mock=True,
            )
        self.assertIsNotNone(path)

    # 16 image fallback explicitness
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback", side_effect=_fake_image_fallback)
    def test_16_image_fallback_not_agnes_path(self, fb_mock):
        self.mock.behavior = MockBehavior.REJECTION
        with self._patch_bridge():
            path = _resolve_footage(**_footage_kwargs(self.tmp))
        self.assertTrue(str(path).endswith("_i2v_a1.mp4"))

    # 17 BYP-02 removed — behavioral: exception path does not call direct provider
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback", side_effect=_fake_image_fallback)
    def test_17_byp02_removed_exception_uses_fallback_not_direct(self, fb_mock):
        with self._patch_bridge():
            with mock.patch(
                "pipeline.scene_builder._resolve_single_agnes_beat_src",
                side_effect=ValueError("unexpected"),
            ):
                with mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip") as direct:
                    _resolve_footage(**_footage_kwargs(self.tmp))
        direct.assert_not_called()
        fb_mock.assert_called_once()

    # 18 no NEW direct provider
    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    def test_18_no_direct_provider_on_success(self, direct_mock):
        with self._patch_bridge():
            _resolve_footage(**_footage_kwargs(self.tmp))
        direct_mock.assert_not_called()

    # 19 C2-2-C-3-2 preserved
    @mock.patch("pipeline.fallback_image_video.build_image_video_fallback")
    def test_19_c3c2_success_preserved(self, fb_mock):
        with self._patch_bridge():
            path = _resolve_footage(**_footage_kwargs(self.tmp))
        self.assertEqual(path, self.tmp / "agnes_07_feature.mp4")
        fb_mock.assert_not_called()

    # 20 split path regression import
    def test_20_split_helper_still_available(self):
        from pipeline.scene_builder import _resolve_split_agnes_beat_src

        self.assertTrue(callable(_resolve_split_agnes_beat_src))


if __name__ == "__main__":
    unittest.main(verbosity=2)
