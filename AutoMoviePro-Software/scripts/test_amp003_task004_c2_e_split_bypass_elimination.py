#!/usr/bin/env python3
"""AMP-003 T004-C2-E — Split Agnes BYP-01 direct-bypass elimination tests."""
from __future__ import annotations

import inspect
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.idempotency.agnes_bridge import AgnesBeatOutcome, classify_agnes_beat_outcome
from pipeline.idempotency.mock_visual_provider import MockBehavior, get_mock_provider, reset_mock_provider
from pipeline.scene_builder import _build_split_dialogue_clip, _resolve_split_agnes_beat_src


def _split_kwargs(tmp: Path, **overrides) -> dict:
    base = dict(
        work=tmp,
        job_id="job-c2e-split",
        idx=5,
        part_index=1,
        attempt=1,
        product_name="TestProduct",
        element="feature",
        visual_prompt="Cinematic reactor hall",
        visual_query="Cinematic reactor hall",
        out_path=tmp / "agnes_split_p1.mp4",
        narration_hint="First beat narration for split path",
        size="1080x1920",
        duration_hint=5.0,
        override_prompt="Cinematic reactor hall beat 1",
        niche="tech",
        use_catalog_image=True,
        dialogue_id="dlg-c2e-split-uuid",
        canonical_scene_id="scene-c2e-split-uuid",
        script_id="script-c2e",
        segment_id="seg-01",
        use_mock=True,
    )
    base.update(overrides)
    return base


class T004C2ESplitBypassEliminationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        reset_mock_provider()
        self.mock = get_mock_provider()
        self.mock.reset()
        self.mock.behavior = MockBehavior.SUCCESS
        self.narr = self.tmp / "narr.m4a"
        self.narr.write_bytes(b"\x00" * 2000)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_byp01_removed_from_split_caller_source(self):
        src = inspect.getsource(_build_split_dialogue_clip)
        self.assertNotIn("generate_agnes_dialogue_clip", src)
        self.assertIn("_resolve_split_agnes_beat_src", src)
        self.assertIn("Split Agnes canonical path failed", src)

    def test_02_success_preserved(self):
        src, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        self.assertEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.SUCCESS)
        self.assertIsNotNone(src)
        self.assertTrue(src.is_file())

    def test_03_reused_preserved(self):
        kw = _split_kwargs(self.tmp)
        _resolve_split_agnes_beat_src(**kw)
        self.mock.invocation_count = 0
        src, result = _resolve_split_agnes_beat_src(**kw)
        self.assertEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.REUSED)
        self.assertIsNotNone(src)
        self.assertEqual(self.mock.invocation_count, 0)

    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    def test_04_failed_no_direct_provider(self, direct_mock):
        self.mock.behavior = MockBehavior.REJECTION
        src, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        self.assertIsNone(src)
        self.assertNotEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.SUCCESS)
        direct_mock.assert_not_called()

    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    def test_05_unknown_no_direct_provider(self, direct_mock):
        self.mock.behavior = MockBehavior.UNKNOWN
        src, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        self.assertIsNone(src)
        self.assertEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.UNKNOWN)
        direct_mock.assert_not_called()

    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    def test_06_identity_blocked_no_direct_provider(self, direct_mock):
        kw = _split_kwargs(self.tmp)
        kw["segment_id"] = ""
        kw["part_index"] = 2
        src, result = _resolve_split_agnes_beat_src(**kw)
        self.assertIsNone(src)
        self.assertEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.IDENTITY_BLOCKED)
        self.assertEqual(self.mock.invocation_count, 0)
        direct_mock.assert_not_called()

    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    @mock.patch(
        "pipeline.idempotency.agnes_bridge.idempotent_generate_agnes_beat_result",
        side_effect=RuntimeError("simulated bridge crash"),
    )
    def test_07_exception_no_direct_bypass(self, _bridge_mock, direct_mock):
        with self.assertRaises(RuntimeError):
            _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        direct_mock.assert_not_called()

    @mock.patch("pipeline.scene_builder.concat_av_clips")
    @mock.patch("pipeline.scene_builder._mux_scene")
    @mock.patch("pipeline.scene_builder._resolve_footage")
    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    @mock.patch("pipeline.scene_builder._resolve_split_agnes_beat_src")
    @mock.patch("pipeline.scene_builder.ffprobe_duration")
    @mock.patch("pipeline.scene_builder.plan_agnes_segments")
    @mock.patch("subprocess.run")
    def test_08_build_split_exception_uses_fallback_not_direct(
        self,
        sp_run,
        plan,
        ffprobe,
        split_src,
        direct_mock,
        footage_mock,
        mux_mock,
        concat_mock,
    ):
        ffprobe.return_value = 25.0
        plan.return_value = [{"narration_part": "Long narration text for split testing"}]
        split_src.side_effect = RuntimeError("simulated bridge crash")

        def fake_run(cmd, capture_output=True, text=True, **kw):
            out_path = Path(cmd[-1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"\x00" * 500)
            return mock.Mock(returncode=0)

        sp_run.side_effect = fake_run

        fb_video = self.tmp / "fb.mp4"
        fb_video.write_bytes(b"fake")
        footage_mock.return_value = fb_video

        def fake_mux(**kw):
            dest = kw["dest"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"mux")
            return dest

        mux_mock.side_effect = fake_mux
        final = self.tmp / "scene_05_feature.mp4"
        concat_mock.return_value = final

        with mock.patch(
            "pipeline.prompt_hardening.preflight_keyword_prompt",
            return_value={"fixed_prompt": "fixed prompt"},
        ):
            _build_split_dialogue_clip(
                work=self.tmp,
                idx=5,
                narration_audio=self.narr,
                narration="Long narration text for split testing",
                visual_query="query",
                visual_prompt="prompt",
                exact_ai_video_prompt="exact",
                element="feature",
                size="1080x1920",
                product_name="prod",
                agnes_api="fake-key",
                agnes_api_keys=["fake-key"],
                google_api_keys=[],
                keyword_triggers=[],
                niche="tech",
                max_av_retries=0,
                skip_av_critic=True,
                pexels_api="",
                pollinations_key="",
                require_agnes=False,
                job_id="job-c2e",
                dialogue_id="dlg-c2e",
                canonical_scene_id="scene-c2e",
                script_id="script-c2e",
            )

        direct_mock.assert_not_called()
        split_src.assert_called()
        footage_mock.assert_called()

    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    def test_09_no_new_direct_provider_on_success(self, direct_mock):
        _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        direct_mock.assert_not_called()
        self.assertEqual(self.mock.invocation_count, 1)

    def test_10_canonical_scene_id_propagation(self):
        _, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        self.assertTrue(result.fingerprint)
        from pipeline.idempotency.visual_provenance import load_visual_provenance

        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["provenance"]["metadata"]["canonical_scene_id"], "scene-c2e-split-uuid")

    def test_11_dialogue_id_propagation(self):
        _, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        from pipeline.idempotency.visual_provenance import load_visual_provenance

        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertEqual(prov["provenance"]["metadata"]["dialogue_id"], "dlg-c2e-split-uuid")

    def test_12_job_id_propagation(self):
        _, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        from pipeline.idempotency.visual_provenance import load_visual_provenance

        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertEqual(prov["provenance"]["job_id"], "job-c2e-split")

    @mock.patch("pipeline.scene_builder.concat_av_clips")
    @mock.patch("pipeline.scene_builder._mux_scene")
    @mock.patch("pipeline.scene_builder._resolve_footage")
    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    @mock.patch("pipeline.scene_builder._resolve_split_agnes_beat_src", side_effect=RuntimeError("crash"))
    @mock.patch("pipeline.scene_builder.ffprobe_duration", return_value=25.0)
    @mock.patch("pipeline.scene_builder.plan_agnes_segments")
    @mock.patch("subprocess.run")
    def test_13_provider_count_bounded_on_exception_path(
        self,
        sp_run,
        plan,
        ffprobe,
        split_src,
        direct_mock,
        footage_mock,
        mux_mock,
        concat_mock,
    ):
        plan.return_value = [{"narration_part": "Long narration text for split testing"}]

        def fake_run(cmd, capture_output=True, text=True, **kw):
            out_path = Path(cmd[-1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"\x00" * 500)
            return mock.Mock(returncode=0)

        sp_run.side_effect = fake_run
        fb_video = self.tmp / "fb.mp4"
        fb_video.write_bytes(b"fake")
        footage_mock.return_value = fb_video

        def fake_mux(**kw):
            dest = kw["dest"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"mux")
            return dest

        mux_mock.side_effect = fake_mux
        concat_mock.return_value = self.tmp / "scene_05_feature.mp4"

        with mock.patch(
            "pipeline.prompt_hardening.preflight_keyword_prompt",
            return_value={"fixed_prompt": "fixed prompt"},
        ):
            _build_split_dialogue_clip(
                work=self.tmp,
                idx=5,
                narration_audio=self.narr,
                narration="Long narration text for split testing",
                visual_query="q",
                visual_prompt="p",
                exact_ai_video_prompt="e",
                element="feature",
                size="1080x1920",
                product_name="prod",
                agnes_api="fake-key",
                agnes_api_keys=["fake-key"],
                google_api_keys=[],
                keyword_triggers=[],
                niche="tech",
                max_av_retries=0,
                skip_av_critic=True,
                pexels_api="",
                pollinations_key="",
                require_agnes=False,
            )

        direct_mock.assert_not_called()
        self.assertEqual(split_src.call_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
