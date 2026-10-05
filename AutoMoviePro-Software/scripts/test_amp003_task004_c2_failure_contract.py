#!/usr/bin/env python3
"""AMP-003 T004-C2-2-B — Agnes failure / UNKNOWN semantics contract tests."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.idempotency.agnes_bridge import (
    AgnesBeatOutcome,
    classify_agnes_beat_outcome,
    idempotent_generate_agnes_beat,
    idempotent_generate_agnes_beat_result,
)
from pipeline.idempotency.mock_visual_provider import MockBehavior, get_mock_provider, reset_mock_provider
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyStore
from pipeline.idempotency.visual_provenance import load_visual_provenance
from pipeline.idempotency.visual_request import VisualIdentityError
from pipeline.idempotency.visual_runtime import execute_visual_request


def _prod_kwargs(tmp: Path) -> dict:
    return dict(
        work_dir=tmp,
        job_id="job-c2b",
        scene_id=3,
        part_index=0,
        attempt=1,
        product_name="TestProduct",
        element="feature",
        visual_prompt="Cinematic reactor hall",
        out_path=tmp / "agnes_out.mp4",
        dialogue_id="dlg-c2b-uuid",
        canonical_scene_id="scene-c2b-uuid",
        script_id="script-c2b",
        use_mock=True,
    )


class T004C2FailureContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        reset_mock_provider()
        self.mock = get_mock_provider()
        self.mock.reset()
        self.mock.behavior = MockBehavior.SUCCESS

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # TEST-01
    def test_01_valid_result_success(self):
        result = idempotent_generate_agnes_beat_result(**_prod_kwargs(self.tmp))
        outcome = classify_agnes_beat_outcome(result)
        self.assertEqual(outcome, AgnesBeatOutcome.SUCCESS)
        self.assertTrue(result.success)
        self.assertTrue(result.path and result.path.is_file())

    # TEST-02
    def test_02_cached_asset_reused(self):
        kw = _prod_kwargs(self.tmp)
        r1 = idempotent_generate_agnes_beat_result(**kw)
        self.mock.invocation_count = 0
        r2 = idempotent_generate_agnes_beat_result(**kw)
        self.assertEqual(classify_agnes_beat_outcome(r2), AgnesBeatOutcome.REUSED)
        self.assertEqual(r2.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 0)

    # TEST-03
    def test_03_definitive_provider_failure(self):
        self.mock.behavior = MockBehavior.REJECTION
        result = idempotent_generate_agnes_beat_result(**_prod_kwargs(self.tmp))
        outcome = classify_agnes_beat_outcome(result)
        self.assertIn(outcome, (AgnesBeatOutcome.FAILED_FINAL, AgnesBeatOutcome.FAILED_RETRYABLE))
        self.assertFalse(result.success)

    # TEST-04
    def test_04_pre_execution_identity_blocked(self):
        kw = _prod_kwargs(self.tmp)
        kw["canonical_scene_id"] = ""
        result = idempotent_generate_agnes_beat_result(**kw)
        self.assertEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.IDENTITY_BLOCKED)
        self.assertEqual(result.action, "identity_blocked")
        self.assertEqual(self.mock.invocation_count, 0)

    # TEST-05
    def test_05_provider_uncertainty_unknown(self):
        self.mock.behavior = MockBehavior.UNKNOWN
        result = idempotent_generate_agnes_beat_result(**_prod_kwargs(self.tmp))
        self.assertEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.UNKNOWN)
        self.assertEqual(result.action, "unknown")
        self.assertEqual(result.state, IdempotencyState.UNKNOWN)

    # TEST-06
    def test_06_unknown_persisted(self):
        self.mock.behavior = MockBehavior.UNKNOWN
        result = idempotent_generate_agnes_beat_result(**_prod_kwargs(self.tmp))
        store = IdempotencyStore(self.tmp / "idempotency")
        rec = store.get(result.fingerprint)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.request_state, IdempotencyState.UNKNOWN)

    # TEST-07
    def test_07_unknown_no_blind_retry(self):
        self.mock.behavior = MockBehavior.UNKNOWN
        kw = _prod_kwargs(self.tmp)
        r1 = idempotent_generate_agnes_beat_result(**kw)
        count = self.mock.invocation_count
        r2 = idempotent_generate_agnes_beat_result(**kw)
        self.assertEqual(classify_agnes_beat_outcome(r1), AgnesBeatOutcome.UNKNOWN)
        self.assertEqual(self.mock.invocation_count, count)

    # TEST-08
    def test_08_identity_error_explicit_non_success(self):
        kw = _prod_kwargs(self.tmp)
        kw["part_index"] = 2
        kw["segment_id"] = ""
        result = idempotent_generate_agnes_beat_result(**kw)
        self.assertFalse(result.success)
        self.assertEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.IDENTITY_BLOCKED)
        with self.assertRaises(VisualIdentityError):
            idempotent_generate_agnes_beat(**kw)

    # TEST-09
    def test_09_runtime_failure_explicit_non_success(self):
        self.mock.behavior = MockBehavior.INVALID_ASSET
        result = idempotent_generate_agnes_beat_result(**_prod_kwargs(self.tmp))
        self.assertFalse(result.success)
        self.assertNotEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.SUCCESS)
        self.assertIsNone(idempotent_generate_agnes_beat(**_prod_kwargs(self.tmp)))

    # TEST-10
    def test_10_fingerprint_preserved(self):
        result = idempotent_generate_agnes_beat_result(**_prod_kwargs(self.tmp))
        self.assertTrue(len(result.fingerprint) >= 32)
        r2 = idempotent_generate_agnes_beat_result(**_prod_kwargs(self.tmp))
        self.assertEqual(result.fingerprint, r2.fingerprint)

    # TEST-11
    def test_11_asset_path_on_success(self):
        result = idempotent_generate_agnes_beat_result(**_prod_kwargs(self.tmp))
        self.assertTrue(result.path)
        self.assertEqual(result.path, _prod_kwargs(self.tmp)["out_path"])

    # TEST-12
    def test_12_provenance_on_success_and_reuse(self):
        r1 = idempotent_generate_agnes_beat_result(**_prod_kwargs(self.tmp))
        prov = load_visual_provenance(self.tmp, r1.fingerprint)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["provenance"]["input_hash"], r1.fingerprint)
        idempotent_generate_agnes_beat_result(**_prod_kwargs(self.tmp))
        prov2 = load_visual_provenance(self.tmp, r1.fingerprint)
        self.assertIsNotNone(prov2)

    # TEST-13
    def test_13_none_not_success(self):
        self.mock.behavior = MockBehavior.REJECTION
        path = idempotent_generate_agnes_beat(**_prod_kwargs(self.tmp))
        self.assertIsNone(path)
        result = idempotent_generate_agnes_beat_result(**_prod_kwargs(self.tmp))
        self.assertFalse(result.success)
        self.assertNotEqual(classify_agnes_beat_outcome(result), AgnesBeatOutcome.SUCCESS)

    # TEST-14
    def test_14_none_legacy_does_not_imply_success(self):
        self.mock.behavior = MockBehavior.REJECTION
        path = idempotent_generate_agnes_beat(**_prod_kwargs(self.tmp))
        result = idempotent_generate_agnes_beat_result(**_prod_kwargs(self.tmp))
        self.assertIsNone(path)
        self.assertFalse(result.success)
        outcome = classify_agnes_beat_outcome(result)
        self.assertNotEqual(outcome, AgnesBeatOutcome.SUCCESS)
        self.assertNotEqual(outcome, AgnesBeatOutcome.REUSED)

    # TEST-15
    def test_15_same_request_same_reuse(self):
        kw = _prod_kwargs(self.tmp)
        o1 = classify_agnes_beat_outcome(idempotent_generate_agnes_beat_result(**kw))
        o2 = classify_agnes_beat_outcome(idempotent_generate_agnes_beat_result(**kw))
        self.assertEqual(o1, AgnesBeatOutcome.SUCCESS)
        self.assertEqual(o2, AgnesBeatOutcome.REUSED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
