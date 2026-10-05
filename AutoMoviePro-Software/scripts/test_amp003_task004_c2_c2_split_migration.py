#!/usr/bin/env python3
"""AMP-003 T004-C2-2-C-2 — Split Agnes caller canonical result API migration tests."""
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
from pipeline.idempotency.checkpoint_store import CheckpointStore
from pipeline.idempotency.mock_visual_provider import MockBehavior, get_mock_provider, reset_mock_provider
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyStore
from pipeline.idempotency.visual_provenance import load_visual_provenance
from pipeline.scene_builder import _build_split_dialogue_clip, _resolve_split_agnes_beat_src


def _split_kwargs(tmp: Path, **overrides) -> dict:
    base = dict(
        work=tmp,
        job_id="job-c2c2-split",
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
        dialogue_id="dlg-c2c2-split-uuid",
        canonical_scene_id="scene-c2c2-split-uuid",
        script_id="script-c2c2",
        segment_id="seg-01",
        use_mock=True,
    )
    base.update(overrides)
    return base


class T004C2C2SplitMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        reset_mock_provider()
        self.mock = get_mock_provider()
        self.mock.reset()
        self.mock.behavior = MockBehavior.SUCCESS

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # TEST-01
    def test_01_canonical_result_api_called_on_split_path(self):
        with mock.patch(
            "pipeline.idempotency.agnes_bridge.idempotent_generate_agnes_beat_result",
            wraps=__import__(
                "pipeline.idempotency.agnes_bridge", fromlist=["idempotent_generate_agnes_beat_result"]
            ).idempotent_generate_agnes_beat_result,
        ) as wrapped:
            src, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
            wrapped.assert_called_once()
            self.assertIsNotNone(src)
            self.assertTrue(result.success)

    # TEST-02
    def test_02_success_split_path_continues(self):
        src, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        outcome = classify_agnes_beat_outcome(result)
        self.assertEqual(outcome, AgnesBeatOutcome.SUCCESS)
        self.assertIsNotNone(src)
        self.assertTrue(src.is_file())

    # TEST-03
    def test_03_reused_split_path_continues(self):
        kw = _split_kwargs(self.tmp)
        _resolve_split_agnes_beat_src(**kw)
        self.mock.invocation_count = 0
        src, result = _resolve_split_agnes_beat_src(**kw)
        self.assertEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.REUSED)
        self.assertIsNotNone(src)
        self.assertTrue(src.is_file())

    # TEST-04
    def test_04_reused_no_second_provider_execution(self):
        kw = _split_kwargs(self.tmp)
        _resolve_split_agnes_beat_src(**kw)
        self.mock.invocation_count = 0
        _resolve_split_agnes_beat_src(**kw)
        self.assertEqual(self.mock.invocation_count, 0)

    # TEST-05
    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    def test_05_failed_retryable_no_new_direct_provider(self, direct_mock):
        self.mock.behavior = MockBehavior.INVALID_ASSET
        src, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        self.assertIsNone(src)
        self.assertIn(
            classify_agnes_beat_outcome(result),
            (AgnesBeatOutcome.FAILED_RETRYABLE, AgnesBeatOutcome.FAILED_FINAL),
        )
        direct_mock.assert_not_called()

    # TEST-06
    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    def test_06_failed_final_controlled_non_success(self, direct_mock):
        self.mock.behavior = MockBehavior.REJECTION
        src, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        self.assertIsNone(src)
        self.assertFalse(result.success)
        self.assertNotEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.SUCCESS)
        direct_mock.assert_not_called()

    # TEST-07
    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    def test_07_unknown_no_direct_provider(self, direct_mock):
        self.mock.behavior = MockBehavior.UNKNOWN
        src, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        self.assertIsNone(src)
        self.assertEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.UNKNOWN)
        direct_mock.assert_not_called()

    # TEST-08
    def test_08_unknown_no_blind_retry(self):
        self.mock.behavior = MockBehavior.UNKNOWN
        kw = _split_kwargs(self.tmp)
        r1, res1 = _resolve_split_agnes_beat_src(**kw)
        count_after_first = self.mock.invocation_count
        src2, res2 = _resolve_split_agnes_beat_src(**kw)
        self.assertIsNone(r1)
        self.assertIsNone(src2)
        self.assertEqual(classify_agnes_beat_outcome(res1), AgnesBeatOutcome.UNKNOWN)
        self.assertEqual(classify_agnes_beat_outcome(res2), AgnesBeatOutcome.UNKNOWN)
        self.assertEqual(self.mock.invocation_count, count_after_first)

    # TEST-09
    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    def test_09_identity_blocked_no_provider(self, direct_mock):
        kw = _split_kwargs(self.tmp)
        kw["segment_id"] = ""
        kw["part_index"] = 2
        src, result = _resolve_split_agnes_beat_src(**kw)
        self.assertIsNone(src)
        self.assertEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.IDENTITY_BLOCKED)
        self.assertEqual(self.mock.invocation_count, 0)
        direct_mock.assert_not_called()

    # TEST-10
    def test_10_canonical_scene_id_preserved(self):
        _, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertIsNotNone(prov)
        meta = prov["provenance"]["metadata"]
        self.assertEqual(meta["canonical_scene_id"], "scene-c2c2-split-uuid")

    # TEST-11
    def test_11_dialogue_id_preserved(self):
        _, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertIsNotNone(prov)
        meta = prov["provenance"]["metadata"]
        self.assertEqual(meta["dialogue_id"], "dlg-c2c2-split-uuid")

    # TEST-12
    def test_12_segment_id_preserved(self):
        _, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertIsNotNone(prov)
        meta = prov["provenance"]["metadata"]
        self.assertEqual(meta["segment_id"], "seg-01")

    # TEST-13
    def test_13_job_id_preserved(self):
        _, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["provenance"]["job_id"], "job-c2c2-split")

    # TEST-14
    def test_14_revision_id_preserved_when_present(self):
        _, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertIsNotNone(prov)
        meta = prov["provenance"]["metadata"]
        self.assertIn("revision_id", meta)
        self.assertEqual(meta["revision_id"], "")

    # TEST-15
    def test_15_successful_asset_path_preserved(self):
        kw = _split_kwargs(self.tmp)
        src, result = _resolve_split_agnes_beat_src(**kw)
        self.assertEqual(src, kw["out_path"])
        self.assertEqual(result.path, kw["out_path"])

    # TEST-16
    def test_16_provenance_available(self):
        _, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        prov = load_visual_provenance(self.tmp, result.fingerprint)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["provenance"]["input_hash"], result.fingerprint)

    # TEST-17
    def test_17_checkpoint_available(self):
        _, result = _resolve_split_agnes_beat_src(**_split_kwargs(self.tmp))
        cps = CheckpointStore(self.tmp / "checkpoints").latest_for_job("job-c2c2-split")
        self.assertTrue(len(cps) >= 1)
        store = IdempotencyStore(self.tmp / "idempotency")
        rec = store.get(result.fingerprint)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.request_state, IdempotencyState.SUCCEEDED)

    # TEST-18
    def test_18_image_fallback_unchanged(self):
        src = inspect.getsource(_build_split_dialogue_clip)
        self.assertIn("Agnes miss scene", src)
        self.assertIn("_resolve_footage", src)
        self.assertIn("image fallback", src)
        self.assertIn("_resolve_split_agnes_beat_src", src)
        self.assertNotIn("generate_agnes_dialogue_clip", src)
        self.assertNotIn("build_image_video_fallback", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
